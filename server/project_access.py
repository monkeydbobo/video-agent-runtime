"""项目归属守卫。

项目文件仍可扁平或用户命名空间存放，归属关系记录在 DB ``projects`` 表。
本模块提供 FastAPI 依赖与内联校验两种形态：

- 路由 path/query 带 ``project_name`` / ``name`` 的端点，声明对应依赖即可；
- 项目名在 request body 中的端点，在解析 body 后调用 :func:`ensure_project_access`。

规则：
- ``role == "admin"`` 可跨用户运维（显式管理员能力）；
- 普通用户必须 ``owner == user.id``；
- ``default`` 仅表示管理员所有者，**不再**对全体用户共享。

对不可见项目返回 404（复用 ``project_not_found`` 文案），避免通过状态码探测他人项目名。

作者: wanghaobo
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from fastapi import HTTPException

from lib.db import async_session_factory
from lib.db.base import DEFAULT_USER_ID
from lib.db.repositories.project_repo import ProjectRepository
from lib.i18n import Translator
from server.auth import CurrentUser, CurrentUserFlexible, CurrentUserInfo

ADMIN_ROLE = "admin"


def is_admin(user: CurrentUserInfo) -> bool:
    return user.role == ADMIN_ROLE


async def get_project_owner(name: str) -> str | None:
    """查询项目归属 user_id；无记录返回 None。"""
    async with async_session_factory() as session:
        return await ProjectRepository(session).get_owner(name)


async def get_ownership_map() -> dict[str, str]:
    """返回 {项目名: user_id} 全量映射。"""
    async with async_session_factory() as session:
        return await ProjectRepository(session).ownership_map()


async def accessible_project_names(names: Iterable[str], user: CurrentUserInfo) -> list[str]:
    """从 names 中筛出当前用户可见的项目名（admin 全量；普通用户仅属主）。"""
    names = list(names)
    if is_admin(user):
        return names
    ownership = await get_ownership_map()
    return [n for n in names if ownership.get(n) == user.id]


async def register_project_owner(name: str, user: CurrentUserInfo) -> None:
    """项目创建/导入成功后登记归属（已存在记录则保持原归属不变）。"""
    async with async_session_factory() as session:
        async with session.begin():
            await ProjectRepository(session).ensure(name, user.id)


async def unregister_project(name: str, user_id: str | None = None) -> None:
    """项目删除后清理归属记录；``user_id`` 限定仅删除该属主的登记。"""
    async with async_session_factory() as session:
        async with session.begin():
            await ProjectRepository(session).delete(name, user_id=user_id)


async def reconcile_project_ownership(disk_names: Iterable[str]) -> int:
    """启动对账：把磁盘存在但 DB 无归属记录的存量项目登记给 default 管理员。

    default 仅表示管理员所有者，不再对全体用户共享。
    返回新登记的数量。幂等，可重复执行。
    """
    disk_names = list(disk_names)
    async with async_session_factory() as session:
        async with session.begin():
            repo = ProjectRepository(session)
            known = set(await repo.list_names())
            missing = [n for n in disk_names if n not in known]
            for name in missing:
                await repo.create(name, DEFAULT_USER_ID)
    return len(missing)


async def ensure_project_access(name: str, user: CurrentUserInfo, _t: Callable[..., str]) -> None:
    """校验当前用户可操作项目，无权限时抛 404。

    ``_t`` 为路由注入的 Translator 可调用对象。
    """
    if is_admin(user):
        return
    owner = await get_project_owner(name)
    if owner is not None and owner == user.id:
        return
    raise HTTPException(status_code=404, detail=_t("project_not_found", name=name))


async def require_project_access(project_name: str, user: CurrentUser, _t: Translator) -> None:
    """依赖形态：path/query 参数名为 ``project_name`` 的端点。"""
    await ensure_project_access(project_name, user, _t)


async def require_project_access_by_name(name: str, user: CurrentUser, _t: Translator) -> None:
    """依赖形态：path 参数名为 ``name`` 的端点（projects.py 风格）。"""
    await ensure_project_access(name, user, _t)


async def require_project_access_flexible(project_name: str, user: CurrentUserFlexible, _t: Translator) -> None:
    """依赖形态：SSE 端点（支持 ``?token=`` 认证）。"""
    await ensure_project_access(project_name, user, _t)
