"""
认证核心模块

提供密码生成、JWT token 创建/验证、凭据校验等功能。
同时支持 API Key 认证（`arc-` 前缀的 Bearer token）。
"""

import hashlib
import logging
import os
import secrets
import string
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable
from datetime import UTC
from pathlib import Path
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Query
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from lib import PROJECT_ROOT
from lib.i18n import Translator
from lib.i18n import _ as i18n_translate

logger = logging.getLogger(__name__)


class CurrentUserInfo(BaseModel):
    """Current authenticated user info."""

    id: str
    sub: str
    role: str = "admin"
    # "jwt" | "apikey" | "anonymous" — used to reject elevated/self-management via API keys
    via: str = "jwt"

    model_config = ConfigDict(frozen=True)


# JWT 签名密钥缓存
_cached_token_secret: str | None = None

# Token 有效期：7 天
TOKEN_EXPIRY_SECONDS = 7 * 24 * 3600

# 关闭认证时返回的匿名用户标识
_ANONYMOUS_USER_SUB = "local"

# 视为"关闭认证"的 env 取值。空串不在内 —— .env 误写 `AUTH_ENABLED=` 应回退到默认（开启），
# 避免静默 fail-open。
_AUTH_DISABLED_VALUES = frozenset({"false", "0", "no", "off"})


def is_auth_enabled() -> bool:
    """``AUTH_ENABLED`` env 解析。默认 ``true``，保持现有部署行为；空值也按默认。

    ``false`` / ``0`` / ``no`` / ``off`` 一律视为关闭（不区分大小写）。
    """
    return os.environ.get("AUTH_ENABLED", "true").strip().lower() not in _AUTH_DISABLED_VALUES


def is_registration_enabled() -> bool:
    """Whether visitors may create database-backed accounts.

    Registration is only meaningful while authentication is enabled. Deployments
    that are intentionally single-user can set ``AUTH_REGISTRATION_ENABLED=false``.
    """
    return (
        is_auth_enabled()
        and os.environ.get("AUTH_REGISTRATION_ENABLED", "true").strip().lower() not in _AUTH_DISABLED_VALUES
    )


def _anonymous_user() -> "CurrentUserInfo":
    """关闭认证时返回的固定匿名用户。"""
    from lib.db.base import DEFAULT_USER_ID

    return CurrentUserInfo(id=DEFAULT_USER_ID, sub=_ANONYMOUS_USER_SUB, role="admin", via="anonymous")


# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)

# 密码哈希
_password_hash = PasswordHash.recommended()
_cached_password_hash: str | None = None

# AUTH_PASSWORD 未配置时使用的默认登录密码（开发/单机部署）
DEFAULT_AUTH_PASSWORD = "cybercut2026"


def generate_password(length: int = 16) -> str:
    """生成随机字母数字密码"""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def get_token_secret() -> str:
    """获取 JWT 签名密钥

    优先使用 AUTH_TOKEN_SECRET 环境变量，否则自动生成并缓存。
    """
    global _cached_token_secret

    env_secret = os.environ.get("AUTH_TOKEN_SECRET")
    if env_secret:
        return env_secret

    if _cached_token_secret is not None:
        return _cached_token_secret

    _cached_token_secret = secrets.token_hex(32)
    logger.info("已自动生成 JWT 签名密钥")
    return _cached_token_secret


def create_token(username: str, *, user_id: str | None = None, role: str = "admin") -> str:
    """创建 JWT token

    Args:
        username: 用户名

    Returns:
        JWT token 字符串
    """
    now = time.time()
    payload = {
        "sub": username,
        "uid": user_id or "default",
        "role": role,
        "iat": now,
        "exp": now + TOKEN_EXPIRY_SECONDS,
    }
    return jwt.encode(payload, get_token_secret(), algorithm="HS256")


def verify_token(token: str) -> dict | None:
    """验证 JWT token

    Args:
        token: JWT token 字符串

    Returns:
        成功返回 payload dict，失败返回 None
    """
    try:
        payload = jwt.decode(token, get_token_secret(), algorithms=["HS256"])
        return payload
    except (jwt.InvalidTokenError, jwt.ExpiredSignatureError):
        return None


DOWNLOAD_TOKEN_EXPIRY_SECONDS = 300  # 5 分钟
MEDIA_TOKEN_EXPIRY_SECONDS = 300  # 5 分钟 — 禁止复用 7 天 JWT 作媒体 query token


def create_media_token(
    user_id: str,
    *,
    project_name: str | None = None,
    asset_path: str | None = None,
    purpose: str = "media",
    expires: int = MEDIA_TOKEN_EXPIRY_SECONDS,
) -> str:
    """签发短时效媒体访问 token（独立于长期登录 JWT）。"""
    if purpose != "media":
        raise ValueError("media token purpose 必须为 'media'")
    if not project_name and not asset_path:
        raise ValueError("project_name 与 asset_path 至少指定一项")
    now = time.time()
    payload: dict[str, str | int | float] = {
        "uid": user_id,
        "purpose": purpose,
        "iat": now,
        "exp": now + expires,
    }
    if project_name:
        payload["project"] = project_name
    if asset_path:
        payload["asset_path"] = asset_path
    return jwt.encode(payload, get_token_secret(), algorithm="HS256")


def verify_media_token(
    token: str,
    *,
    user_id: str | None = None,
    project_name: str | None = None,
    asset_path: str | None = None,
) -> dict:
    """验证媒体 token 的 uid / purpose / 资源范围。"""
    if not is_auth_enabled():
        out: dict[str, str] = {"purpose": "media"}
        if user_id:
            out["uid"] = user_id
        if project_name:
            out["project"] = project_name
        if asset_path:
            out["asset_path"] = asset_path
        return out

    payload = jwt.decode(token, get_token_secret(), algorithms=["HS256"])
    if payload.get("purpose") != "media":
        raise ValueError("token purpose 不匹配")
    token_uid = payload.get("uid")
    if user_id is not None and token_uid != user_id:
        raise ValueError("token uid 不匹配")
    if project_name is not None and payload.get("project") != project_name:
        raise ValueError("token project 不匹配")
    if asset_path is not None and payload.get("asset_path") != asset_path:
        raise ValueError("token asset_path 不匹配")
    return payload


def create_download_token(user_id: str, project_name: str, *, username: str | None = None) -> str:
    """签发短时效下载 token，用于浏览器原生下载认证。

    ``uid`` 绑定项目属主，导出端点须与 DB 归属交叉校验。
    """
    now = time.time()
    payload = {
        "uid": user_id,
        "sub": username or user_id,
        "project": project_name,
        "purpose": "download",
        "iat": now,
        "exp": now + DOWNLOAD_TOKEN_EXPIRY_SECONDS,
    }
    return jwt.encode(payload, get_token_secret(), algorithm="HS256")


def verify_download_token(token: str, project_name: str, *, user_id: str | None = None) -> dict:
    """验证下载 token

    Returns:
        成功返回 payload dict

    Raises:
        jwt.ExpiredSignatureError: token 已过期
        jwt.InvalidTokenError: token 无效
        ValueError: purpose / project / uid 不匹配
    """
    if not is_auth_enabled():
        out: dict[str, str] = {
            "sub": _ANONYMOUS_USER_SUB,
            "project": project_name,
            "purpose": "download",
        }
        if user_id:
            out["uid"] = user_id
        return out
    payload = jwt.decode(token, get_token_secret(), algorithms=["HS256"])
    if payload.get("purpose") != "download":
        raise ValueError("token purpose 不匹配")
    if payload.get("project") != project_name:
        raise ValueError("token project 不匹配")
    token_uid = payload.get("uid")
    if user_id is not None and token_uid != user_id:
        raise ValueError("token uid 不匹配")
    return payload


def _get_password_hash() -> str:
    """获取当前密码的哈希值（缓存）"""
    global _cached_password_hash
    if _cached_password_hash is None:
        raw = os.environ.get("AUTH_PASSWORD", "")
        _cached_password_hash = _password_hash.hash(raw)
    return _cached_password_hash


def check_credentials(username: str, password: str) -> bool:
    """校验用户名密码（使用哈希比对）

    从 AUTH_USERNAME（默认 admin）和 AUTH_PASSWORD 环境变量读取。
    即使用户名不匹配也执行哈希验证，防止时序攻击。

    ``AUTH_ENABLED=false`` 时无条件返回 True。
    """
    if not is_auth_enabled():
        return True
    expected_username = os.environ.get("AUTH_USERNAME", "admin")
    pw_hash = _get_password_hash()
    username_ok = secrets.compare_digest(username, expected_username)
    password_ok = _password_hash.verify(password, pw_hash)
    return username_ok and password_ok


async def authenticate_credentials(username: str, password: str) -> CurrentUserInfo | None:
    """Authenticate either the legacy environment administrator or a registered user."""
    if not is_auth_enabled():
        return _anonymous_user()

    if check_credentials(username, password):
        from lib.db.base import DEFAULT_USER_ID

        return CurrentUserInfo(id=DEFAULT_USER_ID, sub=username, role="admin")

    from lib.db import async_session_factory
    from lib.db.models.user import User

    async with async_session_factory() as session:
        user = (await session.execute(select(User).where(User.username == username))).scalar_one_or_none()

    # Always run a password verification, including unknown users and legacy
    # rows without a password hash, to avoid making account existence observable
    # through timing.
    password_hash = user.password_hash if user is not None else _password_hash.hash("invalid-password")
    password_ok = _password_hash.verify(password, password_hash) if password_hash else False
    if user is None or not user.is_active or not password_ok:
        return None
    return CurrentUserInfo(id=user.id, sub=user.username, role=user.role)


async def create_registered_user(username: str, password: str) -> CurrentUserInfo | None:
    """Create a regular user, returning ``None`` when the username already exists."""
    from sqlalchemy.exc import IntegrityError

    from lib.db import async_session_factory
    from lib.db.models.user import User

    user = User(id=str(uuid.uuid4()), username=username, password_hash=_password_hash.hash(password), role="user")
    try:
        async with async_session_factory() as session:
            session.add(user)
            await session.commit()
    except IntegrityError:
        return None
    return CurrentUserInfo(id=user.id, sub=user.username, role=user.role)


def get_google_client_id() -> str | None:
    """Return configured Google OAuth Web Client ID, or ``None`` when unset."""
    value = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    return value or None


def is_google_login_enabled() -> bool:
    """Google GIS login is enabled when a Client ID is configured and auth is on."""
    return is_auth_enabled() and get_google_client_id() is not None


class GoogleIdTokenError(Exception):
    """Raised when a Google ID token fails verification or is missing required claims."""


class GoogleRegistrationClosedError(Exception):
    """Raised when a new Google user cannot be created because registration is disabled."""


def verify_google_id_token(id_token: str) -> dict:
    """Verify a Google GIS ID token and return the claims dict.

    Requires ``GOOGLE_CLIENT_ID``. Validates audience, issuer, and that email is
    present and marked verified.
    """
    client_id = get_google_client_id()
    if not client_id:
        raise GoogleIdTokenError("google_login_disabled")

    try:
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token as google_id_token
    except ImportError as exc:  # pragma: no cover - google-auth is a declared dependency
        raise GoogleIdTokenError("google_token_invalid") from exc

    try:
        claims = google_id_token.verify_oauth2_token(
            id_token,
            google_requests.Request(),
            audience=client_id,
        )
    except Exception as exc:
        logger.warning("Google ID token 校验失败: %s", exc)
        raise GoogleIdTokenError("google_token_invalid") from exc

    if not isinstance(claims, dict):
        raise GoogleIdTokenError("google_token_invalid")

    iss = str(claims.get("iss") or "")
    if iss not in {"accounts.google.com", "https://accounts.google.com"}:
        raise GoogleIdTokenError("google_token_invalid")

    sub = str(claims.get("sub") or "").strip()
    email = str(claims.get("email") or "").strip().lower()
    email_verified = claims.get("email_verified")
    if not sub or not email:
        raise GoogleIdTokenError("google_token_invalid")
    if email_verified is not True and str(email_verified).lower() != "true":
        raise GoogleIdTokenError("google_email_unverified")

    return {"sub": sub, "email": email, "name": str(claims.get("name") or "").strip()}


def _username_from_google_email(email: str) -> str:
    """Derive a username that satisfies RegisterRequest's pattern from an email local-part."""
    import re

    local = email.split("@", 1)[0].lower()
    cleaned = re.sub(r"[^a-z0-9_.-]", "", local)
    cleaned = cleaned.lstrip("._-")
    if not cleaned or not cleaned[0].isalnum():
        cleaned = f"user{cleaned}"
    if not cleaned[0].isalnum():
        cleaned = "user"
    return cleaned[:64]


async def login_or_register_google_user(claims: dict) -> tuple[CurrentUserInfo, bool]:
    """Find or create a user for a verified Google identity.

    Matching key is ``(provider=google, subject)``. New users are only created
    when registration is enabled; otherwise raises ``GoogleRegistrationClosedError``.

    Returns ``(user, is_new)``.
    """
    from sqlalchemy.exc import IntegrityError

    from lib.db import async_session_factory
    from lib.db.models.oauth_identity import OAuthIdentity
    from lib.db.models.user import User

    subject = str(claims["sub"])
    email = str(claims["email"])

    async with async_session_factory() as session:
        identity = (
            await session.execute(
                select(OAuthIdentity).where(
                    OAuthIdentity.provider == "google",
                    OAuthIdentity.subject == subject,
                )
            )
        ).scalar_one_or_none()

        if identity is not None:
            user = (await session.execute(select(User).where(User.id == identity.user_id))).scalar_one_or_none()
            if user is None or not user.is_active:
                raise GoogleIdTokenError("google_token_invalid")
            if identity.email != email:
                identity.email = email
            if user.email != email:
                email_owner = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
                if email_owner is not None and email_owner.id != user.id:
                    raise GoogleIdTokenError("google_email_taken")
                user.email = email
            try:
                await session.commit()
            except IntegrityError as exc:
                # Another request may have claimed the email between the check and the commit.
                await session.rollback()
                raise GoogleIdTokenError("google_email_taken") from exc
            return CurrentUserInfo(id=user.id, sub=user.username, role=user.role), False

        if not is_registration_enabled():
            raise GoogleRegistrationClosedError("registration_disabled")

        # Do not auto-link to an existing password account that already owns this email.
        email_owner = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if email_owner is not None:
            raise GoogleIdTokenError("google_email_taken")

        base_username = _username_from_google_email(email)
        for attempt in range(8):
            suffix = "" if attempt == 0 else f"-{secrets.token_hex(2)}"
            username = f"{base_username[: max(1, 64 - len(suffix))]}{suffix}"
            user = User(
                id=str(uuid.uuid4()),
                username=username,
                email=email,
                password_hash=None,
                role="user",
            )
            identity = OAuthIdentity(
                id=str(uuid.uuid4()),
                user_id=user.id,
                provider="google",
                subject=subject,
                email=email,
            )
            session.add(user)
            session.add(identity)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                # Username conflict or race — retry with a new suffix.
                # If the same Google subject raced another request, re-check identity.
                existing = (
                    await session.execute(
                        select(OAuthIdentity).where(
                            OAuthIdentity.provider == "google",
                            OAuthIdentity.subject == subject,
                        )
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    user = (await session.execute(select(User).where(User.id == existing.user_id))).scalar_one_or_none()
                    if user is None or not user.is_active:
                        raise GoogleIdTokenError("google_token_invalid")
                    return CurrentUserInfo(id=user.id, sub=user.username, role=user.role), False
                email_owner = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
                if email_owner is not None:
                    raise GoogleIdTokenError("google_email_taken")
                continue
            return CurrentUserInfo(id=user.id, sub=user.username, role=user.role), True

        raise GoogleIdTokenError("google_token_invalid")


def ensure_auth_password(env_path: str | None = None) -> str:
    """确保 AUTH_PASSWORD 已设置

    如果 AUTH_PASSWORD 环境变量为空，使用 DEFAULT_AUTH_PASSWORD，写入环境变量，
    回写到 .env 文件，并用 logger.warning 输出到控制台。

    ``AUTH_ENABLED=false`` 时整个步骤跳过（不生成、不回写）。

    Args:
        env_path: .env 文件路径，默认为项目根目录的 .env

    Returns:
        当前的 AUTH_PASSWORD 值；关闭认证时返回空串。
    """
    if not is_auth_enabled():
        return ""
    password = os.environ.get("AUTH_PASSWORD")
    if password:
        return password

    password = DEFAULT_AUTH_PASSWORD
    os.environ["AUTH_PASSWORD"] = password

    # 回写到 .env 文件
    if env_path is None:
        env_path = str(PROJECT_ROOT / ".env")

    env_file = Path(env_path)
    try:
        if env_file.exists():
            try:
                lines = env_file.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                # 历史 .env 可能用 cp936 / ANSI 等本地编码（早期 Windows 用户写过中文注释/值）；
                # 不强制覆写以免丢失用户内容，仅 log 并跳过自动回写。
                # 进程内 password 已 set 到 os.environ，本次启动仍可用，只是不持久化。
                logger.warning(
                    "无法以 UTF-8 解码 %s，跳过 AUTH_PASSWORD 自动回写；"
                    "请将该文件转存为 UTF-8 后重启以持久化生成的密码",
                    env_path,
                )
                return password
            new_lines = []
            found = False
            for line in lines:
                if not found and line.strip().startswith("AUTH_PASSWORD="):
                    new_lines.append(f"AUTH_PASSWORD={password}")
                    found = True
                else:
                    new_lines.append(line)
            if not found:
                new_lines.append(f"AUTH_PASSWORD={password}")
            new_content = "\n".join(new_lines) + "\n"
            # 使用原地写入（truncate + write）保留 inode，兼容 Docker bind mount
            with open(env_file, "r+", encoding="utf-8") as f:
                f.seek(0)
                f.write(new_content)
                f.truncate()
        else:
            env_file.write_text(f"AUTH_PASSWORD={password}\n", encoding="utf-8")
    except OSError:
        logger.warning("无法写入 .env 文件: %s", env_path)

    logger.warning(
        "AUTH_PASSWORD 未配置，已使用默认密码并回写到 .env（AUTH_PASSWORD=%s）",
        DEFAULT_AUTH_PASSWORD,
    )
    return password


# ---------------------------------------------------------------------------
# API Key 认证支持
# ---------------------------------------------------------------------------

API_KEY_PREFIX = "arc-"
API_KEY_CACHE_TTL = 300  # 5 分钟

# LRU 缓存：key_hash → (payload_dict | None, expires_at_timestamp)
# payload 为 None 表示 key 不存在或已过期（负缓存）
# 使用 OrderedDict 实现 LRU：命中时 move_to_end，淘汰时 popitem(last=False)
_api_key_cache: OrderedDict[str, tuple[dict | None, float]] = OrderedDict()
_API_KEY_CACHE_MAX = 512


def _hash_api_key(key: str) -> str:
    """计算 API Key 的 SHA-256 哈希。"""
    return hashlib.sha256(key.encode()).hexdigest()


def invalidate_api_key_cache(key_hash: str) -> None:
    """立即清除指定 key_hash 的缓存条目（key 删除时调用）。"""
    _api_key_cache.pop(key_hash, None)


def _get_cached_api_key_payload(key_hash: str) -> tuple[bool, dict | None]:
    """从缓存中查找。返回 (命中, payload 或 None)。命中时将条目移至末尾（LRU）。"""
    entry = _api_key_cache.get(key_hash)
    if entry is None:
        return False, None
    payload, expiry = entry
    if time.monotonic() > expiry:
        _api_key_cache.pop(key_hash, None)
        return False, None
    _api_key_cache.move_to_end(key_hash)
    return True, payload


def _set_api_key_cache(key_hash: str, payload: dict | None, expires_at_ts: float | None = None) -> None:
    """写入缓存（含 LRU 淘汰）。

    正向缓存（payload 非 None）TTL 以 key 实际过期时间为上界，
    避免 key 过期后仍在缓存中通过验证的安全问题。
    """
    if len(_api_key_cache) >= _API_KEY_CACHE_MAX:
        # 淘汰最久未使用的条目（LRU：OrderedDict 头部）
        _api_key_cache.popitem(last=False)
    ttl = API_KEY_CACHE_TTL
    if payload is not None and expires_at_ts is not None:
        time_to_expiry = expires_at_ts - time.monotonic()
        if time_to_expiry <= 0:
            # key 已过期，写入负缓存
            _api_key_cache[key_hash] = (None, time.monotonic() + API_KEY_CACHE_TTL)
            return
        ttl = min(ttl, time_to_expiry)
    _api_key_cache[key_hash] = (payload, time.monotonic() + ttl)


async def _verify_api_key(token: str) -> dict | None:
    """验证 API Key token，返回 payload dict 或 None（失败/过期/不存在）。

    内部先查缓存，缓存未命中再查数据库。
    查库成功后更新 last_used_at（后台异步，不阻塞响应）。
    """
    key_hash = _hash_api_key(token)

    # 缓存查询
    hit, cached_payload = _get_cached_api_key_payload(key_hash)
    if hit:
        return cached_payload

    # 数据库查询
    from lib.db import async_session_factory
    from lib.db.repositories.api_key_repository import ApiKeyRepository

    async with async_session_factory() as session:
        async with session.begin():
            repo = ApiKeyRepository(session)
            row = await repo.get_by_hash(key_hash)

    if row is None:
        _set_api_key_cache(key_hash, None)
        return None

    # 检查过期
    expires_at = row.get("expires_at")
    expires_at_monotonic: float | None = None
    if expires_at:
        from datetime import datetime

        try:
            exp_dt = expires_at
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=UTC)
            if datetime.now(UTC) >= exp_dt:
                _set_api_key_cache(key_hash, None)
                return None
            # 将过期时刻转换为 monotonic 时间戳，供缓存 TTL 上界计算
            remaining_secs = (exp_dt - datetime.now(UTC)).total_seconds()
            expires_at_monotonic = time.monotonic() + remaining_secs
        except (ValueError, TypeError):
            logger.warning("API Key expires_at 值格式无法解析，忽略过期检查: %r", expires_at)

    # Resolve owner identity from users table; never default to admin.
    from lib.db.base import DEFAULT_USER_ID
    from lib.db.models.user import User

    owner_id = str(row.get("user_id") or DEFAULT_USER_ID)
    role = "user"
    username = f"apikey:{row['name']}"
    async with async_session_factory() as session:
        user = (await session.execute(select(User).where(User.id == owner_id))).scalar_one_or_none()
        if user is not None:
            if not user.is_active:
                _set_api_key_cache(key_hash, None)
                return None
            role = user.role or "user"
            username = user.username

    payload = {
        "sub": username,
        "uid": owner_id,
        "role": role,
        "via": "apikey",
        "apikey_name": row["name"],
    }
    _set_api_key_cache(key_hash, payload, expires_at_ts=expires_at_monotonic)

    # 异步更新 last_used_at（不阻塞，保存引用防止 GC）
    import asyncio

    async def _touch():
        try:
            async with async_session_factory() as s:
                async with s.begin():
                    await ApiKeyRepository(s).touch_last_used(key_hash)
        except Exception:
            logger.exception("更新 API Key last_used_at 失败（非致命）")

    _touch_task = asyncio.create_task(_touch())
    _touch_task.add_done_callback(lambda _: None)  # suppress "never retrieved" warning

    return payload


def _verify_and_get_payload(token: str) -> dict:
    """同步验证 JWT token 并在失败时抛出 401 异常。（仅用于 JWT 路径）"""
    payload = verify_token(token)
    if payload is None:
        raise HTTPException(
            status_code=401,
            detail="token 无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


def _auth_message(key: str, translate: Callable[..., str] | None = None) -> str:
    return translate(key) if translate is not None else i18n_translate(key)


async def _verify_and_get_payload_async(
    token: str,
    translate: Callable[..., str] | None = None,
) -> dict:
    """异步验证 token，支持 API Key（arc- 前缀）和 JWT 两种模式。"""
    if token.startswith(API_KEY_PREFIX):
        payload = await _verify_api_key(token)
        if payload is None:
            raise HTTPException(
                status_code=401,
                detail=_auth_message("api_key_invalid", translate),
                headers={"WWW-Authenticate": "Bearer"},
            )
        return payload
    # JWT 路径
    return _verify_and_get_payload(token)


def _payload_to_user(
    payload: dict,
    translate: Callable[..., str] | None = None,
) -> CurrentUserInfo:
    """Convert a verified JWT/API-key payload to CurrentUserInfo.

    API Key payloads must carry explicit ``uid``/``role``; missing fields no longer
    silently elevate to admin/default.
    """
    from lib.db.base import DEFAULT_USER_ID

    sub = payload.get("sub", "")
    via = str(payload.get("via") or "jwt")
    if via == "apikey":
        user_id = payload.get("uid")
        role = payload.get("role")
        if not user_id or not role:
            raise HTTPException(
                status_code=401,
                detail=_auth_message("api_key_identity_incomplete", translate),
                headers={"WWW-Authenticate": "Bearer"},
            )
        return CurrentUserInfo(id=str(user_id), sub=sub, role=str(role), via="apikey")

    user_id = payload.get("uid", DEFAULT_USER_ID)
    role = payload.get("role", "admin")
    return CurrentUserInfo(id=str(user_id), sub=sub, role=str(role), via="jwt")


async def get_current_user(
    _t: Translator,
    token: Annotated[str | None, Depends(oauth2_scheme_optional)] = None,
) -> CurrentUserInfo:
    """标准认证依赖 — 支持 JWT 和 API Key Bearer token。

    ``AUTH_ENABLED=false`` 时无视 token，直接返回匿名 admin。
    启用时缺 token 抛 401（与旧 oauth2_scheme auto_error 行为等价）。
    """
    if not is_auth_enabled():
        return _anonymous_user()
    if not token:
        raise HTTPException(
            status_code=401,
            detail=_t("auth_required"),
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = await _verify_and_get_payload_async(token, _t)
    return _payload_to_user(payload, _t)


async def get_current_user_flexible(
    _t: Translator,
    token: Annotated[str | None, Depends(oauth2_scheme_optional)] = None,
    query_token: str | None = Query(None, alias="token"),
) -> CurrentUserInfo:
    """SSE 认证依赖 — 同时支持 Authorization header 和 ?token= query param。

    ``AUTH_ENABLED=false`` 时无视 token，直接返回匿名 admin。
    """
    if not is_auth_enabled():
        return _anonymous_user()
    raw = token or query_token
    if not raw:
        raise HTTPException(
            status_code=401,
            detail=_t("auth_token_required"),
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = await _verify_and_get_payload_async(raw, _t)
    return _payload_to_user(payload, _t)


# Type aliases for FastAPI dependency injection
CurrentUser = Annotated[CurrentUserInfo, Depends(get_current_user)]
CurrentUserFlexible = Annotated[CurrentUserInfo, Depends(get_current_user_flexible)]
