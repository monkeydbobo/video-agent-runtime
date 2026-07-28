"""
API 调用统计路由

提供调用记录查询和统计摘要接口。
非 admin 用户的可见范围限定在自己拥有的项目内。
"""

from collections.abc import Callable
from datetime import datetime

from fastapi import APIRouter, Query

from lib.db import async_session_factory
from lib.db.repositories.usage_repo import UsageRepository
from lib.i18n import Translator
from lib.project_manager import get_project_manager
from lib.providers import CallType
from server.auth import CurrentUser, CurrentUserInfo
from server.project_access import accessible_project_names, ensure_project_access, is_admin

router = APIRouter()


async def _resolve_usage_scope(
    user: CurrentUserInfo,
    project_name: str | None,
    _t: Callable[..., str],
) -> tuple[str | None, list[str] | None]:
    """解析用量视图的过滤参数 (project_name, project_names)。

    指定 project_name 时校验归属后按单项目过滤；未指定时 admin 全量，
    普通用户限定在自己拥有的项目集合内。
    """
    if project_name:
        await ensure_project_access(project_name, user, _t)
        return project_name, None
    if is_admin(user):
        return None, None
    owned = await accessible_project_names(get_project_manager().list_projects(), user)
    return None, owned


@router.get("/usage/stats")
async def get_stats(
    _user: CurrentUser,
    _t: Translator,
    project_name: str | None = Query(None, description="项目名称（可选）"),
    provider: str | None = Query(None, description="按供应商筛选"),
    start_date: str | None = Query(None, description="开始日期 (YYYY-MM-DD)"),
    end_date: str | None = Query(None, description="结束日期 (YYYY-MM-DD)"),
    group_by: str | None = Query(None, description="分组方式: provider"),
):
    start = datetime.fromisoformat(start_date) if start_date else None
    end = datetime.fromisoformat(end_date) if end_date else None
    scoped_name, scoped_names = await _resolve_usage_scope(_user, project_name, _t)

    async with async_session_factory() as session:
        repo = UsageRepository(session)
        if group_by == "provider":
            stats = await repo.get_stats_grouped_by_provider(
                project_name=scoped_name,
                project_names=scoped_names,
                provider=provider,
                start_date=start,
                end_date=end,
            )
        else:
            stats = await repo.get_stats(
                project_name=scoped_name,
                project_names=scoped_names,
                provider=provider,
                start_date=start,
                end_date=end,
            )
    return stats


@router.get("/usage/calls")
async def get_calls(
    _user: CurrentUser,
    _t: Translator,
    project_name: str | None = Query(None, description="项目名称"),
    call_type: CallType | None = Query(None, description="调用类型 (image/video/text)"),
    status: str | None = Query(None, description="状态 (success/failed)"),
    start_date: str | None = Query(None, description="开始日期 (YYYY-MM-DD)"),
    end_date: str | None = Query(None, description="结束日期 (YYYY-MM-DD)"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页记录数"),
):
    start = datetime.fromisoformat(start_date) if start_date else None
    end = datetime.fromisoformat(end_date) if end_date else None
    scoped_name, scoped_names = await _resolve_usage_scope(_user, project_name, _t)

    async with async_session_factory() as session:
        result = await UsageRepository(session).get_calls(
            project_name=scoped_name,
            project_names=scoped_names,
            call_type=call_type,
            status=status,
            start_date=start,
            end_date=end,
            page=page,
            page_size=page_size,
        )
    return result


@router.get("/usage/projects")
async def get_projects_list(_user: CurrentUser, _t: Translator):
    scoped_names: list[str] | None = None
    if not is_admin(_user):
        scoped_names = await accessible_project_names(get_project_manager().list_projects(), _user)
    async with async_session_factory() as session:
        projects = await UsageRepository(session).get_projects_list(project_names=scoped_names)
    return {"projects": projects}
