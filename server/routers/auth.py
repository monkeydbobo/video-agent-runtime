"""
认证 API 路由

提供 OAuth2 登录、Google GIS 联合登录和 token 验证接口。

作者: wanghaobo
"""

import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field

from lib.i18n import Translator
from server.auth import (
    CurrentUser,
    authenticate_credentials,
    authenticate_or_create_google_user,
    create_registered_user,
    create_token,
    get_google_client_id,
    is_auth_enabled,
    is_google_login_enabled,
    is_registration_enabled,
    verify_google_id_token,
)
from server.services.registration_notifications import notify_new_registration

logger = logging.getLogger(__name__)

router = APIRouter()


# ==================== 响应模型 ====================


class TokenResponse(BaseModel):
    access_token: str
    token_type: str


class VerifyResponse(BaseModel):
    valid: bool
    username: str


class AuthStatusResponse(BaseModel):
    enabled: bool
    registration_enabled: bool
    google_enabled: bool = False
    google_client_id: str | None = None


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    password: str = Field(min_length=8, max_length=128)


class GoogleLoginRequest(BaseModel):
    id_token: str = Field(min_length=20, max_length=8192)


# ==================== 路由 ====================


@router.get("/auth/status", response_model=AuthStatusResponse)
async def auth_status():
    """暴露 ``AUTH_ENABLED`` 状态供前端 bootstrap 判断是否需要登录拦截。

    前端 ``auth-store.initialize()`` 在 localStorage 无 token 时调用本接口：
    ``enabled=false`` 时跳过登录页直接进主界面；``enabled=true`` 时保留原
    登录链路。本接口本身**不要求认证**——一个 boolean 比 401 探针更直观，
    且实际"是否需要登录"通过 401/200 也能从外部观察到，因此不增量泄露。

    ``google_client_id`` 为 OAuth Web Client ID，本就可公开给 GIS 前端脚本。
    """
    client_id = get_google_client_id() if is_google_login_enabled() else None
    return AuthStatusResponse(
        enabled=is_auth_enabled(),
        registration_enabled=is_registration_enabled(),
        google_enabled=is_google_login_enabled(),
        google_client_id=client_id,
    )


@router.post("/auth/token", response_model=TokenResponse)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    _t: Translator,
):
    """用户登录

    使用 OAuth2 标准表单格式验证凭据，成功返回 access_token。
    ``AUTH_ENABLED=false`` 时跳过凭据校验，直接签发 token，让前端
    LoginPage 即便被打开也能正常跳转主界面。
    """
    user = await authenticate_credentials(form_data.username, form_data.password)
    if user is None:
        logger.warning("登录失败: 用户名或密码错误 (用户: %s)", form_data.username)
        raise HTTPException(
            status_code=401,
            detail=_t("unauthorized"),
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_token(user.sub, user_id=user.id, role=user.role)
    logger.info("用户登录成功: %s", form_data.username)
    return TokenResponse(access_token=token, token_type="bearer")


@router.post("/auth/register", response_model=TokenResponse, status_code=201)
async def register(req: RegisterRequest, background_tasks: BackgroundTasks, _t: Translator):
    """Register a user and sign them in immediately."""
    if not is_registration_enabled():
        raise HTTPException(status_code=403, detail=_t("registration_disabled"))

    user = await create_registered_user(req.username, req.password)
    if user is None:
        raise HTTPException(status_code=409, detail=_t("username_taken"))

    logger.info("用户注册成功: %s", user.sub)
    background_tasks.add_task(notify_new_registration, user.sub)
    return TokenResponse(access_token=create_token(user.sub, user_id=user.id, role=user.role), token_type="bearer")


@router.post("/auth/google", response_model=TokenResponse)
async def login_with_google(req: GoogleLoginRequest, background_tasks: BackgroundTasks, _t: Translator):
    """Exchange a Google GIS ID token for an ArcReel JWT.

    Existing ``(google, sub)`` identities sign in; new identities create a user
    when registration is enabled. Auth-disabled deployments still get a token
    (anonymous admin), matching ``/auth/token``.
    """
    if not is_auth_enabled():
        from server.auth import _anonymous_user

        user = _anonymous_user()
        return TokenResponse(
            access_token=create_token(user.sub, user_id=user.id, role=user.role),
            token_type="bearer",
        )

    if not is_google_login_enabled():
        raise HTTPException(status_code=503, detail=_t("google_not_configured"))

    try:
        claims = verify_google_id_token(req.id_token)
    except ValueError as exc:
        reason = str(exc)
        if reason == "google_email_unverified":
            raise HTTPException(status_code=401, detail=_t("google_email_unverified")) from exc
        raise HTTPException(status_code=401, detail=_t("google_token_invalid")) from exc

    allow_create = is_registration_enabled()
    try:
        result = await authenticate_or_create_google_user(
            subject=claims["sub"],
            email=claims["email"],
            allow_create=allow_create,
        )
    except ValueError as exc:
        reason = str(exc)
        if reason == "google_account_disabled":
            raise HTTPException(status_code=403, detail=_t("google_account_disabled")) from exc
        if reason == "google_email_conflict":
            raise HTTPException(status_code=409, detail=_t("google_email_conflict")) from exc
        logger.exception("Google 用户创建失败: %s", reason)
        raise HTTPException(status_code=500, detail=_t("google_login_failed")) from exc

    if result is None:
        raise HTTPException(status_code=403, detail=_t("registration_disabled"))

    user, created = result
    if created:
        background_tasks.add_task(notify_new_registration, user.sub)
    logger.info("Google 登录成功: %s (%s)%s", user.sub, claims["email"], " [new]" if created else "")
    return TokenResponse(access_token=create_token(user.sub, user_id=user.id, role=user.role), token_type="bearer")


@router.get("/auth/verify", response_model=VerifyResponse)
async def verify(
    current_user: CurrentUser,
):
    """验证 token 有效性

    使用 OAuth2 Bearer token 依赖自动提取和验证 token。
    """
    return VerifyResponse(valid=True, username=current_user.sub)
