"""集中维护 provider / AUTH 相关的环境变量 key 清单。

唯一真相源 — 凡是涉及 os.environ 名单的代码都从这里 import。
"""

from __future__ import annotations

# —— SDK 子进程需要的 Anthropic env keys（通过 options.env 注入）——
ANTHROPIC_ENV_KEYS: tuple[str, ...] = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "CLAUDE_CODE_SUBAGENT_MODEL",
)

# —— 其他 provider env keys（options.env 用空值覆盖兜底）——
# 营销视频 Agent 仅保留 Ark（文本/视频/图片）+ OpenAI（图片）。
OTHER_PROVIDER_ENV_KEYS: tuple[str, ...] = (
    "ARK_API_KEY",
    "OPENAI_API_KEY",
    "FILE_SERVICE_BASE_URL",
    "DEFAULT_VIDEO_PROVIDER",
)

# —— 启动断言：真密钥子集，命中即 fail-fast ——
PROVIDER_SECRET_KEYS: frozenset[str] = frozenset(
    {
        "ANTHROPIC_API_KEY",
        "ARK_API_KEY",
        "OPENAI_API_KEY",
    }
)


def is_provider_env_key(name: str) -> bool:
    """判断给定 env key 是否属于 provider 相关。"""
    return name in ANTHROPIC_ENV_KEYS or name in OTHER_PROVIDER_ENV_KEYS
