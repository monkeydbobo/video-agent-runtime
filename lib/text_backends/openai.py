"""OpenAITextBackend — OpenAI 文本生成后端。"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterable
from typing import Any

from openai import AsyncOpenAI, BadRequestError
from openai.types import CompletionUsage

from lib.config.url_utils import is_official_openai_base_url
from lib.logging_utils import format_kwargs_for_log
from lib.openai_shared import OPENAI_RETRYABLE_ERRORS, create_openai_client
from lib.providers import PROVIDER_OPENAI
from lib.retry import with_retry_async
from lib.text_backends.base import (
    TextCapability,
    TextGenerationRequest,
    TextGenerationResult,
    TokenParam,
    check_truncation,
    resolve_schema,
    structured_fallback_reason,
)

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-5.4-mini"


class OpenAITextBackend:
    """OpenAI 文本生成后端，支持 Chat Completions API。"""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        provider_name: str = PROVIDER_OPENAI,
    ):
        # 禁用 SDK 内置重试，由本层 generate() 统一管理重试策略
        self._client = create_openai_client(api_key=api_key, base_url=base_url, max_retries=0)
        self._model = model or DEFAULT_MODEL
        # 复用 OpenAI 兼容协议的 provider（如 dashscope）须用真实 provider 记账，
        # 否则计费查表会命中 OpenAI 的 USD 费率而非自身定价。
        self._provider_name = provider_name
        # 官方端点已弃用 max_tokens（推理模型直接拒绝），用 max_completion_tokens；
        # 第三方兼容端点（自定义供应商、dashscope 等）不保证支持新参数，保守沿用 max_tokens
        self._max_tokens_param: TokenParam = (
            "max_completion_tokens" if is_official_openai_base_url(base_url) else "max_tokens"
        )
        self._capabilities: set[TextCapability] = {
            TextCapability.TEXT_GENERATION,
            TextCapability.STRUCTURED_OUTPUT,
            TextCapability.VISION,
        }

    @property
    def name(self) -> str:
        return self._provider_name

    @property
    def model(self) -> str:
        return self._model

    @property
    def capabilities(self) -> set[TextCapability]:
        return self._capabilities

    async def generate(self, request: TextGenerationRequest) -> TextGenerationResult:
        """生成文本回复。

        本方法不带重试装饰器：瞬态错误重试分别在 :meth:`_generate_native` 与
        :func:`_instructor_fallback` 层完成。若把复验/降级也包进重试范围，降级尝试的
        失败会连带重放已成功的原生调用（重试叠乘），且降级异常消息含模型侧动态文本，
        可能误中重试判定的字符串模式。
        """
        messages = _build_messages(request)
        native = await self._generate_native(request, messages)
        if native is None:
            # 原生 response_format 通道不兼容（schema 错误），结构化输出整体降级
            return await _instructor_fallback(
                self._client,
                self._model,
                request,
                messages,
                provider=self._provider_name,
                token_param=self._max_tokens_param,
            )

        if request.response_schema:
            fallback_reason = structured_fallback_reason(native.text, request.response_schema)
            if fallback_reason:
                logger.warning(
                    "原生 response_format %s，降级到带校验的 Instructor 路径",
                    fallback_reason,
                )
                result = await _instructor_fallback(
                    self._client,
                    self._model,
                    request,
                    messages,
                    provider=self._provider_name,
                    token_param=self._max_tokens_param,
                )
                # 这次原生 200 调用已被代理计费，把它的 token 并入降级结果，否则
                # 记账层会系统性漏记。仅在至少一侧有计量时相加；两侧皆 None
                # （未追踪）保持 None，不塌成字面 0 token。
                if result.input_tokens is not None or native.input_tokens is not None:
                    result.input_tokens = (result.input_tokens or 0) + (native.input_tokens or 0)
                if result.output_tokens is not None or native.output_tokens is not None:
                    result.output_tokens = (result.output_tokens or 0) + (native.output_tokens or 0)
                return result

        return native

    @with_retry_async(max_attempts=4, backoff_seconds=(2, 4, 8), retryable_errors=OPENAI_RETRYABLE_ERRORS)
    async def _generate_native(
        self, request: TextGenerationRequest, messages: list[dict]
    ) -> TextGenerationResult | None:
        """单次原生调用：构造 kwargs、发流式请求、聚合与截断告警，瞬态错误重试。

        schema 不兼容时返回 ``None``（降级信号）而不抛异常：代理可能把上游 schema 错误
        包装成 429 等状态码，若以异常形式穿过重试装饰器，会被字符串模式误判为瞬态错误
        白白重试。
        """
        kwargs: dict = {"model": self._model, "messages": messages}
        if request.max_output_tokens is not None:
            kwargs[self._max_tokens_param] = request.max_output_tokens

        # 流式是刚性要求而非优化：中转网关（tengine/nginx 类）普遍配 60s 量级的
        # proxy_read_timeout，该超时按「两次成功读之间的空闲间隔」计而非总时长。非流式下
        # 整轮生成期间网关无数据可读，长输出（分集规划、剧本生成）会被掐断并返回网关自带的
        # HTML 错误页；流式让每个 chunk 都重置该计时器，长响应才能走完。
        kwargs["stream"] = True
        # 流式默认不回 usage，须显式索取，否则 token 无从记账（CostCalculator 在
        # input_tokens 为 None 时直接返回 0 成本，会把文本调用静默记成免费）。
        kwargs["stream_options"] = {"include_usage": True}

        if request.response_schema:
            schema = resolve_schema(request.response_schema)
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "response",
                    "strict": True,
                    "schema": schema,
                },
            }

        logger.info("调用 %s 文本 SDK kwargs=%s", self.name, format_kwargs_for_log(kwargs))
        try:
            stream = await self._client.chat.completions.create(**kwargs)
            # 流的消费一并纳入本 try：200 后再于流中段抛出的错误同样要过 schema 降级判定，
            # 且整段都在 @with_retry_async 覆盖内，断流属可重试的连接类错误。
            text, finish_reason, usage = await _consume_stream(stream)
        except Exception as exc:
            if request.response_schema and _is_schema_error(exc):
                logger.warning(
                    "原生 response_format 失败 (%s)，降级到 Instructor 路径",
                    exc,
                )
                return None
            raise

        if usage is None:
            logger.warning(
                "%s/%s 流式响应未返回 usage（供应商可能不支持 stream_options.include_usage），本次调用 token 无从记账",
                self._provider_name,
                self._model,
            )
        output_tokens = usage.completion_tokens if usage else None

        check_truncation(
            finish_reason,
            provider=self._provider_name,
            model=self._model,
            output_tokens=output_tokens,
            structured=bool(request.response_schema),
        )
        return TextGenerationResult(
            text=text,
            provider=self._provider_name,
            model=self._model,
            input_tokens=usage.prompt_tokens if usage else None,
            output_tokens=output_tokens,
        )


async def _consume_stream(stream: AsyncIterable[Any]) -> tuple[str, str | None, CompletionUsage | None]:
    """把 Chat Completions 流聚合成 ``(text, finish_reason, usage)``。

    只收 ``delta.content``，不收推理模型的 ``delta.reasoning_content``——与非流式只读
    ``message.content`` 的口径一致，思维链不属于可交付输出。

    ``usage`` 的落点各家不一：官方规范放在末尾一个 ``choices`` 为空的独立 chunk，部分中转
    把它挂在带 ``finish_reason`` 的收尾 chunk 上。故不认位置、见到即取，并对空 ``choices``
    与缺失 ``delta`` 做防御——中转返回的 chunk 常缺字段，SDK 不会替我们补齐。
    """
    parts: list[str] = []
    finish_reason: str | None = None
    usage: CompletionUsage | None = None

    async for chunk in stream:
        if getattr(chunk, "usage", None) is not None:
            usage = chunk.usage
        choices = getattr(chunk, "choices", None)
        if not choices:
            continue
        choice = choices[0]
        delta = getattr(choice, "delta", None)
        if delta is not None and getattr(delta, "content", None):
            parts.append(delta.content)
        # 末 chunk 才带 finish_reason；不 break，后面可能还有独立的 usage chunk。
        if getattr(choice, "finish_reason", None):
            finish_reason = choice.finish_reason

    return "".join(parts), finish_reason, usage


def _build_messages(request: TextGenerationRequest) -> list[dict]:
    """将 TextGenerationRequest 转为 OpenAI messages 格式。"""
    messages: list[dict] = []

    if request.system_prompt:
        messages.append({"role": "system", "content": request.system_prompt})

    # 构建 user message
    if request.images:
        from lib.image_backends.base import image_to_base64_data_uri

        content: list[dict] = []
        for img in request.images:
            if img.path:
                data_uri = image_to_base64_data_uri(img.path)
                content.append({"type": "image_url", "image_url": {"url": data_uri}})
            elif img.url:
                content.append({"type": "image_url", "image_url": {"url": img.url}})
        content.append({"type": "text", "text": request.prompt})
        messages.append({"role": "user", "content": content})
    else:
        messages.append({"role": "user", "content": request.prompt})

    return messages


_SCHEMA_ERROR_KEYWORDS = (
    "response_schema",
    "json_schema",
    "Unknown name",
    "Cannot find field",
    "Invalid JSON payload",
)


def _is_schema_error(exc: BaseException) -> bool:
    """判断异常是否为 JSON Schema 不兼容导致的错误。

    除了标准的 400 BadRequestError，一些 OpenAI 兼容代理（如 Gemini
    兼容端点）会将上游 schema 错误包装成其他状态码（如 429），
    因此也检查错误信息中是否包含 schema 相关关键字。
    """
    if isinstance(exc, BadRequestError):
        return True
    # 代理可能把上游 schema 错误包装成非 400 状态码
    error_str = str(exc)
    return any(kw in error_str for kw in _SCHEMA_ERROR_KEYWORDS)


@with_retry_async(max_attempts=4, backoff_seconds=(2, 4, 8), retryable_errors=OPENAI_RETRYABLE_ERRORS)
async def _instructor_fallback(
    client: AsyncOpenAI,
    model: str,
    request: TextGenerationRequest,
    messages: list[dict],
    *,
    provider: str = PROVIDER_OPENAI,
    token_param: TokenParam = "max_tokens",
) -> TextGenerationResult:
    """Instructor 降级：当原生 response_format 不可用时的备选路径。

    instructor_fallback_async 自身不做瞬态重试，这里补一层与原生调用同配置的重试；
    范围仅覆盖降级自身，失败不会重放已成功的原生调用。
    """
    from lib.text_backends.instructor_support import instructor_fallback_async

    return await instructor_fallback_async(
        client=client,
        model=model,
        messages=messages,
        response_schema=request.response_schema,
        provider=provider,
        max_tokens=request.max_output_tokens,
        token_param=token_param,
    )
