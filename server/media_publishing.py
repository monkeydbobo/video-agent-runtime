"""生成执行层对项目对象存储的异步适配。"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from lib.object_storage import PublishedProjectFile, get_project_object_storage

logger = logging.getLogger(__name__)


async def publish_project_file(
    file_path: Path,
    *,
    project_path: Path,
    project_name: str,
    user_id: str,
    required: bool = False,
) -> PublishedProjectFile | None:
    """配置对象存储时上传；未配置时保持 Volume-only 兼容。

    供应商生成已计费后不因镜像上传失败而重跑，故默认 best-effort；可安全重跑的最终合成
    使用 ``required=True``，保证工具不会把未持久化的产物报告为完整成功。
    """
    store = get_project_object_storage()
    if store is None:
        return None
    try:
        return await asyncio.to_thread(
            store.publish_project_file,
            file_path,
            project_path=project_path,
            project_name=project_name,
            user_id=user_id,
        )
    except Exception:
        logger.exception(
            "项目媒体上传对象存储失败 project=%s file=%s",
            project_name,
            file_path.name,
        )
        if required:
            raise
        return None
