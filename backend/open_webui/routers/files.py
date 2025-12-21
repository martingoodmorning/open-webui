import logging
import os
import uuid
import json
import time
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote
import asyncio
import subprocess
import tempfile

from fastapi import (
    BackgroundTasks,
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
    Query,
)

from fastapi.responses import FileResponse, StreamingResponse

from open_webui.constants import ERROR_MESSAGES
from open_webui.env import SRC_LOG_LEVELS
from open_webui.retrieval.vector.factory import VECTOR_DB_CLIENT

from open_webui.models.users import Users
from open_webui.models.files import (
    FileForm,
    FileModel,
    FileModelResponse,
    Files,
)
from open_webui.models.knowledge import Knowledges
from open_webui.models.groups import Groups


from open_webui.routers.knowledge import get_knowledge, get_knowledge_list
from open_webui.routers.retrieval import ProcessFileForm, process_file
from open_webui.routers.audio import transcribe

from open_webui.storage.provider import Storage


from open_webui.utils.auth import get_admin_user, get_verified_user
from open_webui.utils.access_control import has_access
from open_webui.utils.excel_utils import get_excel_structure, build_excel_chart

from pydantic import BaseModel

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MODELS"])

router = APIRouter()


############################
# Check if the current user has access to a file through any knowledge bases the user may be in.
############################


# TODO: Optimize this function to use the knowledge_file table for faster lookups.
def has_access_to_file(
    file_id: Optional[str], access_type: str, user=Depends(get_verified_user)
) -> bool:
    file = Files.get_file_by_id(file_id)
    log.debug(f"Checking if user has {access_type} access to file")
    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    # 检查共享文件访问权限
    if file.space_type == "shared":
        return has_shared_file_access(file, user)

    # 检查个人文件：文件所有者可以访问
    if file.user_id == user.id:
        return True

    # 检查知识库文件访问权限
    knowledge_bases = Knowledges.get_knowledges_by_file_id(file_id)
    user_group_ids = {group.id for group in Groups.get_groups_by_member_id(user.id)}

    for knowledge_base in knowledge_bases:
        if knowledge_base.user_id == user.id or has_access(
            user.id, access_type, knowledge_base.access_control, user_group_ids
        ):
            return True

    knowledge_base_id = file.meta.get("collection_name") if file.meta else None
    if knowledge_base_id:
        knowledge_bases = Knowledges.get_knowledge_bases_by_user_id(
            user.id, access_type
        )
        for knowledge_base in knowledge_bases:
            if knowledge_base.id == knowledge_base_id:
                return True

    return False


############################
# Shared Files - Permission Check
############################


def has_shared_file_access(file: FileModel, user) -> bool:
    """
    检查用户是否有权限访问共享文件
    - 全局共享文件（space_id='global'）：所有用户可访问
    - 分组文件：用户必须属于该分组
    - 管理员：可以访问所有文件
    """
    if not file or file.space_type != "shared":
        return False

    # 管理员可以访问所有文件
    if user.role == "admin":
        return True

    # 全局共享文件，所有用户可访问
    if file.space_id == "global":
        return True

    # 分组文件，检查用户是否属于该分组
    if file.space_id:
        user_groups = Groups.get_groups_by_member_id(user.id)
        user_group_ids = {g.id for g in user_groups}
        return file.space_id in user_group_ids

    return False


def get_user_accessible_group_ids(user) -> Optional[set[str]]:
    """获取用户可访问的分组ID列表（包括全局共享）"""
    if user.role == "admin":
        # 管理员可以访问所有分组，返回 None 表示不过滤
        return None

    user_groups = Groups.get_groups_by_member_id(user.id)
    user_group_ids = {g.id for g in user_groups}
    # 添加 'global' 表示全局共享
    user_group_ids.add("global")
    return user_group_ids


############################
# Shared Files - List
############################


@router.get("/shared", response_model=dict)
async def list_shared_files(
    user=Depends(get_verified_user),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    group_id: Optional[str] = Query(None, description="分组ID，不传则返回所有有权限的文件"),
    order_by: str = Query("updated_at", description="排序字段"),
    order: str = Query("desc", description="排序方向：asc 或 desc"),
    search: Optional[str] = Query(None, description="搜索关键词（文件名模糊匹配）"),
    file_type: Optional[str] = Query(None, description="文件类型过滤：pdf, image, office, text"),
    start_date: Optional[int] = Query(None, description="开始时间戳（Unix timestamp）"),
    end_date: Optional[int] = Query(None, description="结束时间戳（Unix timestamp）"),
):
    """
    获取共享文件列表
    - 只返回用户有权限访问的文件
    - 支持按分组过滤
    - 支持分页和排序
    - 支持搜索（文件名模糊匹配）
    - 支持文件类型过滤
    - 支持时间范围过滤
    """
    # 获取用户可访问的分组ID
    accessible_group_ids = get_user_accessible_group_ids(user)

    # 如果指定了 group_id，验证权限
    if group_id:
        # 全局共享不需要验证分组存在性
        if group_id == "global":
            space_id = group_id
        else:
            # 验证分组是否存在
            group = Groups.get_group_by_id(group_id)
            if not group:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Group not found",
                )
            
            # 检查用户是否有权限访问该分组
            if accessible_group_ids is not None and group_id not in accessible_group_ids:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have access to this group",
                )
            space_id = group_id
    else:
        space_id = None

    # 查询共享文件
    files, total = Files.get_shared_files(
        space_id=space_id,
        page=page,
        page_size=page_size,
        order_by=order_by,
        order=order,
        search=search,
        file_type=file_type,
        start_date=start_date,
        end_date=end_date,
    )

    # 过滤掉用户无权限的文件（双重检查）
    accessible_files = []
    for file in files:
        if has_shared_file_access(file, user):
            accessible_files.append(file)

    return {
        "items": accessible_files,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


############################
# Shared Files - Excel Preview
############################


class ExcelColumn(BaseModel):
    name: str
    type: str  # number | category | datetime


class ExcelSheetPreview(BaseModel):
    name: str
    columns: list[ExcelColumn]
    sample_rows: list[list]
    total_rows: int
    truncated: bool


class ExcelFilePreviewResponse(BaseModel):
    sheets: list[ExcelSheetPreview]


@router.get("/shared/{file_id}/excel/preview", response_model=ExcelFilePreviewResponse)
async def preview_shared_excel_file(
    file_id: str,
    user=Depends(get_verified_user),
    max_rows: int = Query(100, ge=1, le=1000, description="每个工作表返回的最大行数"),
):
    """获取共享 Excel/CSV 文件的结构预览信息。

    - 仅支持 space_type == "shared" 的文件；
    - 返回 sheet 列表、列信息、样例数据、总行数等；
    - 不返回完整数据，用于前端配置图表时的结构展示。
    """

    file = Files.get_file_by_id(file_id)

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if file.space_type != "shared":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This is not a shared file",
        )

    if not has_shared_file_access(file, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to access this file",
        )

    try:
        from open_webui.config import UPLOAD_DIR

        # 解析物理路径
        if file.path is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File path is empty",
            )

        if os.path.isabs(file.path):
            file_path = Path(file.path)
        else:
            file_path = Path(UPLOAD_DIR) / file.path

        if not file_path.is_file():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found on disk",
            )

        # 调用工具函数获取结构
        structure = get_excel_structure(file_path, max_rows=max_rows)

        # 将 dict 转为响应模型
        sheets = [
            ExcelSheetPreview(
                name=sheet["name"],
                columns=[
                    ExcelColumn(name=col["name"], type=col["type"])
                    for col in sheet.get("columns", [])
                ],
                sample_rows=sheet.get("sample_rows", []),
                total_rows=sheet.get("total_rows", 0),
                truncated=sheet.get("truncated", False),
            )
            for sheet in structure.get("sheets", [])
        ]

        return ExcelFilePreviewResponse(sheets=sheets)

    except HTTPException:
        raise
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found on disk",
        )
    except ValueError as e:
        # 不支持的文件类型或解析错误
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        log.exception(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ERROR_MESSAGES.DEFAULT(f"Error previewing excel file: {str(e)}"),
        )


class ExcelChartTemplate(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    chart_type: str = "bar"  # bar | line | pie
    default_agg: str = "sum"  # sum | count | avg
    preferred_sheet: Optional[str] = None
    default_x: Optional[str] = None
    default_y: Optional[str] = None
    default_series: Optional[str] = None


_BUILTIN_EXCEL_TEMPLATES: List[ExcelChartTemplate] = [
    ExcelChartTemplate(
        id="out_person_status_overview",
        name="在外人员状态统计",
        description="按状态统计在外人员数量（柱状图 / 计数）",
        chart_type="bar",
        default_agg="count",
        preferred_sheet="在外人员统计",
        default_x="状态",
        default_y=None,
        default_series=None,
    ),
    ExcelChartTemplate(
        id="device_type_count",
        name="设备类型数量统计",
        description="按设备类型统计设备数量（柱状图 / 求和）",
        chart_type="bar",
        default_agg="sum",
        preferred_sheet="设备数量统计",
        default_x="设备类型",
        default_y="数量",
        default_series=None,
    ),
    ExcelChartTemplate(
        id="out_person_trend",
        name="在外人数趋势",
        description="按日期统计在外人数变化（折线图 / 计数）",
        chart_type="line",
        default_agg="count",
        preferred_sheet="在外人员统计",
        default_x="日期",
        default_y=None,
        default_series=None,
    ),
]


@router.get("/shared/excel/templates", response_model=List[ExcelChartTemplate])
async def list_excel_chart_templates(user=Depends(get_verified_user)):
    """获取内置的 Excel 图表模版列表。

    目前仅返回后端内置模版，前端可根据当前文件 / sheet 过滤或应用。
    """

    return _BUILTIN_EXCEL_TEMPLATES


class ExcelFilter(BaseModel):
    field: str
    op: str  # eq | in | neq | gte | lte
    value: Optional[Any] = None
    values: Optional[List[Any]] = None


class ExcelChartRequest(BaseModel):
    sheet_name: Optional[str] = None
    chart_type: str = "bar"  # bar | line | pie
    x_field: str
    y_fields: List[str] = []
    series_field: Optional[str] = None
    agg: str = "sum"  # sum | count | avg
    filters: List[ExcelFilter] = []
    template_id: Optional[str] = None


class ExcelChartSeries(BaseModel):
    name: str
    data: List[Dict[str, Any]]


class ExcelChartResponse(BaseModel):
    chart_type: str
    x_field: str
    y_fields: List[str]
    series: List[ExcelChartSeries]
    vega_spec: Optional[Dict[str, Any]] = None


class ExcelViewConfig(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    sheet_name: str
    chart_type: str
    agg: str
    x_field: str
    y_fields: List[str] = []
    series_field: Optional[str] = None
    filters: List[ExcelFilter] = []
    template_id: Optional[str] = None
    created_at: int
    updated_at: int


@router.post("/shared/{file_id}/excel/chart", response_model=ExcelChartResponse)
async def build_shared_excel_chart(
    file_id: str,
    config: ExcelChartRequest,
    user=Depends(get_verified_user),
):
    """根据配置构建共享 Excel/CSV 文件的图表数据。

    - 仅支持 space_type == "shared" 的文件；
    - 根据 sheet/x/y/聚合 等配置使用 pandas 聚合；
    - 返回统一结构和 Vega-Lite spec，供前端渲染。
    """

    file = Files.get_file_by_id(file_id)

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if file.space_type != "shared":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This is not a shared file",
        )

    if not has_shared_file_access(file, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to access this file",
        )

    try:
        from open_webui.config import UPLOAD_DIR

        if file.path is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File path is empty",
            )

        if os.path.isabs(file.path):
            file_path = Path(file.path)
        else:
            file_path = Path(UPLOAD_DIR) / file.path

        if not file_path.is_file():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found on disk",
            )

        chart_dict = build_excel_chart(file_path, config.model_dump())

        series_models = [
            ExcelChartSeries(name=s["name"], data=s.get("data", []))
            for s in chart_dict.get("series", [])
        ]

        return ExcelChartResponse(
            chart_type=chart_dict.get("chart_type", config.chart_type),
            x_field=chart_dict.get("x_field", config.x_field),
            y_fields=chart_dict.get("y_fields", config.y_fields),
            series=series_models,
            vega_spec=chart_dict.get("vega_spec"),
        )

    except HTTPException:
        raise
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found on disk",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        log.exception(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ERROR_MESSAGES.DEFAULT(f"Error building excel chart: {str(e)}"),
        )


@router.get("/shared/{file_id}/excel/views", response_model=List[ExcelViewConfig])
async def list_shared_excel_views(
    file_id: str,
    user=Depends(get_verified_user),
):
    """获取某个共享文件下保存的 Excel 视图列表。"""

    file = Files.get_file_by_id(file_id)

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if file.space_type != "shared":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This is not a shared file",
        )

    if not has_shared_file_access(file, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to access this file",
        )

    meta = file.meta or {}
    views_raw = meta.get("excel_views") or []
    views: List[ExcelViewConfig] = []

    for v in views_raw:
        try:
            views.append(ExcelViewConfig(**v))
        except Exception:
            # 如果某个视图数据有问题，则跳过
            continue

    return views


class ExcelViewSaveRequest(BaseModel):
    id: Optional[str] = None  # 不传则创建新视图
    name: str
    description: Optional[str] = None
    sheet_name: str
    chart_type: str
    agg: str
    x_field: str
    y_fields: List[str] = []
    series_field: Optional[str] = None
    filters: List[ExcelFilter] = []
    template_id: Optional[str] = None


@router.post("/shared/{file_id}/excel/views", response_model=ExcelViewConfig)
async def save_shared_excel_view(
    file_id: str,
    view: ExcelViewSaveRequest,
    user=Depends(get_verified_user),
):
    """保存或更新某个共享文件下的 Excel 视图配置。"""

    file = Files.get_file_by_id(file_id)

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if file.space_type != "shared":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This is not a shared file",
        )

    if not has_shared_file_access(file, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to access this file",
        )

    meta = dict(file.meta or {})
    views_raw = list(meta.get("excel_views") or [])

    now_ts = int(time.time())

    if view.id:
        # 更新已有视图
        updated = None
        for idx, v in enumerate(views_raw):
            if v.get("id") == view.id:
                merged = {
                    **v,
                    **view.model_dump(exclude_unset=True),
                    "updated_at": now_ts,
                }
                views_raw[idx] = merged
                updated = merged
                break

        if not updated:
            # 如果传入的 id 在列表中不存在，则按新视图处理
            view_id = view.id
            updated = {
                "id": view_id,
                **view.model_dump(exclude={"id"}),
                "created_at": now_ts,
                "updated_at": now_ts,
            }
            views_raw.append(updated)
    else:
        # 创建新视图
        view_id = str(uuid.uuid4())
        updated = {
            "id": view_id,
            **view.model_dump(exclude={"id"}),
            "created_at": now_ts,
            "updated_at": now_ts,
        }
        views_raw.append(updated)

    meta["excel_views"] = views_raw
    saved_file = Files.update_file_meta(file_id, meta)
    if not saved_file:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save excel view",
        )

    return ExcelViewConfig(**updated)


@router.delete("/shared/{file_id}/excel/views/{view_id}", response_model=dict)
async def delete_shared_excel_view(
    file_id: str,
    view_id: str,
    user=Depends(get_verified_user),
):
    """删除某个共享文件下的 Excel 视图配置。"""

    file = Files.get_file_by_id(file_id)

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if file.space_type != "shared":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This is not a shared file",
        )

    if not has_shared_file_access(file, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to access this file",
        )

    meta = dict(file.meta or {})
    views_raw = list(meta.get("excel_views") or [])

    new_views = [v for v in views_raw if v.get("id") != view_id]
    if len(new_views) == len(views_raw):
        # 没找到要删除的视图，直接返回成功
        return {"status": "ok"}

    meta["excel_views"] = new_views
    saved_file = Files.update_file_meta(file_id, meta)
    if not saved_file:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete excel view",
        )

    return {"status": "ok"}


############################
# Shared Files - Download
############################


@router.get("/shared/{file_id}/download")
async def download_shared_file(
    file_id: str,
    user=Depends(get_verified_user),
    attachment: bool = Query(True, description="是否作为附件下载"),
):
    """
    下载共享文件
    - 检查用户是否有权限访问该文件
    - 支持作为附件下载或内联显示
    """
    file = Files.get_file_by_id(file_id)

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    # 检查是否是共享文件
    if file.space_type != "shared":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This is not a shared file",
        )

    # 检查用户是否有权限访问
    if not has_shared_file_access(file, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to access this file",
        )

    try:
        # 获取文件路径（共享文件路径是相对路径，需要加上 UPLOAD_DIR）
        from open_webui.config import UPLOAD_DIR
        
        # 如果路径已经是绝对路径，直接使用；否则拼接 UPLOAD_DIR
        if os.path.isabs(file.path):
            file_path = file.path
        else:
            file_path = os.path.join(UPLOAD_DIR, file.path)
        
        file_path = Path(file_path)

        # 检查文件是否存在
        if not file_path.is_file():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found on disk",
            )

        # 处理文件名和内容类型（优先使用原文件名）
        # 原文件名存储在 file.meta["name"] 或 file.filename 中
        if file.meta and "name" in file.meta:
            filename = file.meta["name"]  # 优先使用 meta 中的原文件名
            log.debug(f"Using filename from meta.name: {filename}")
        else:
            filename = file.filename  # 如果没有 meta.name，使用 filename
            log.debug(f"Using filename from file.filename: {filename}")
        
        # 确保文件名不为空
        if not filename:
            # 从文件路径中提取原文件名（去除 UUID 前缀）
            path_name = file_path.name
            # 如果文件名格式是 {uuid}_{original_name}，提取原文件名
            if '_' in path_name:
                parts = path_name.split('_', 1)
                if len(parts) == 2 and len(parts[0]) == 36:  # UUID 长度为 36
                    filename = parts[1]  # 使用原文件名部分
                    log.debug(f"Extracted filename from path: {filename}")
                else:
                    filename = path_name
            else:
                filename = path_name
            log.debug(f"Using filename from path: {filename}")
        
        encoded_filename = quote(filename)  # RFC5987 encoding
        log.debug(f"Final filename for download: {filename}, encoded: {encoded_filename}")
        content_type = file.meta.get("content_type") if file.meta else None

        headers = {}

        if attachment:
            headers["Content-Disposition"] = (
                f"attachment; filename*=UTF-8''{encoded_filename}"
            )
        else:
            # 对于 PDF，内联显示
            if content_type == "application/pdf" or filename.lower().endswith(".pdf"):
                headers["Content-Disposition"] = (
                    f"inline; filename*=UTF-8''{encoded_filename}"
                )
                content_type = "application/pdf"
            else:
                headers["Content-Disposition"] = (
                    f"attachment; filename*=UTF-8''{encoded_filename}"
                )

        return FileResponse(
            file_path,
            headers=headers,
            media_type=content_type,
            filename=filename,
        )

    except HTTPException:
        raise
    except Exception as e:
        log.exception(e)
        log.error(f"Error downloading shared file: {file_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ERROR_MESSAGES.DEFAULT(f"Error downloading file: {str(e)}"),
        )


############################
# Shared Files - Preview (Convert Office to PDF)
############################


def _is_office_document(filename: str, content_type: str) -> bool:
    """检查是否是 Office 文档"""
    filename_lower = filename.lower()
    content_type_lower = content_type.lower()
    return (
        filename_lower.endswith(('.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx')) or
        content_type_lower in (
            'application/msword',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/vnd.ms-excel',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'application/vnd.ms-powerpoint',
            'application/vnd.openxmlformats-officedocument.presentationml.presentation'
        )
    )


def convert_office_to_pdf(file_path: Path) -> Optional[Path]:
    """
    将 Office 文档转换为 PDF
    支持: .doc, .docx, .xls, .xlsx, .ppt, .pptx
    需要系统安装 LibreOffice
    使用优化的转换工具，支持中文字体和 Excel 单页显示
    """
    from open_webui.utils.office_converter import convert_office_to_pdf as convert_with_utils
    
    return convert_with_utils(file_path)


@router.get("/shared/{file_id}/preview")
async def preview_shared_file(
    file_id: str,
    user=Depends(get_verified_user),
    force: bool = Query(False, description="强制重新生成预览"),
):
    """
    预览共享文件（Office 文档转换为 PDF）
    - 如果是 Office 文档，转换为 PDF 后返回
    - 如果是 PDF，直接返回
    - 其他格式返回错误
    """
    file = Files.get_file_by_id(file_id)

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    # 检查是否是共享文件
    if file.space_type != "shared":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This is not a shared file",
        )

    # 检查用户是否有权限访问
    if not has_shared_file_access(file, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to access this file",
        )

    try:
        from open_webui.config import UPLOAD_DIR
        
        # 获取文件路径
        if os.path.isabs(file.path):
            file_path = Path(file.path)
        else:
            file_path = Path(UPLOAD_DIR) / file.path

        if not file_path.is_file():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found on disk",
            )

        filename = file.filename or file_path.name
        content_type = file.meta.get('content_type', '')
        is_office = _is_office_document(filename, content_type)
        is_pdf = filename.lower().endswith('.pdf') or content_type.lower() == 'application/pdf'

        # 如果是 PDF，直接返回
        if is_pdf:
            return FileResponse(
                file_path,
                headers={
                    "Content-Type": "application/pdf",
                    "Content-Disposition": f'inline; filename*=UTF-8''{quote(filename)}'
                }
            )

        # 如果是 Office 文档，转换为 PDF
        if is_office:
            pdf_path = file_path.parent / f"{file_path.stem}_preview.pdf"
            
            # 优先使用缓存：仅在 PDF 不存在、过期或损坏时重新转换
            if pdf_path.exists():
                # 检查 PDF 是否有效（文件大小 > 0 且比原文件新）
                if pdf_path.stat().st_size > 0 and pdf_path.stat().st_mtime >= file_path.stat().st_mtime:
                    # 缓存有效，直接返回
                    return FileResponse(
                        pdf_path,
                        headers={
                            "Content-Type": "application/pdf",
                            "Content-Disposition": f'inline; filename*=UTF-8''{quote(file_path.stem + ".pdf")}'
                        }
                    )
                # PDF 无效，删除旧缓存
                try:
                    pdf_path.unlink()
                    log.info(f"Removed invalid preview cache: {pdf_path}")
                except Exception as e:
                    log.warning(f"Failed to remove invalid preview cache: {e}")
            
            # PDF 不存在或无效，尝试转换（如果后台转换还在进行中，会返回 503）
            try:
                converted_pdf = convert_office_to_pdf(file_path)
                if converted_pdf and converted_pdf.exists():
                    pdf_path = converted_pdf
                else:
                    # 转换失败或后台转换还在进行中
                    log.warning(f"PDF preview not available for file: {file_id}, may still be generating")
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="PDF preview is being generated, please try again in a few seconds."
                    )
            except HTTPException:
                raise
            except Exception as e:
                log.exception(e)
                log.error(f"Error converting Office document to PDF: {file_id}, error: {str(e)}")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="PDF preview is being generated, please try again in a few seconds."
                )

            return FileResponse(
                pdf_path,
                headers={
                    "Content-Type": "application/pdf",
                    "Content-Disposition": f'inline; filename*=UTF-8''{quote(file_path.stem + ".pdf")}'
                }
            )

        # 其他格式不支持预览
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This file type cannot be previewed. Only Office documents and PDFs are supported."
        )

    except HTTPException:
        raise
    except Exception as e:
        log.exception(e)
        log.error(f"Error previewing shared file: {file_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ERROR_MESSAGES.DEFAULT(f"Error previewing file: {str(e)}"),
        )


############################
# Shared Files - Delete
############################


@router.delete("/shared/{file_id}")
async def delete_shared_file(
    file_id: str,
    user=Depends(get_verified_user),
):
    """
    删除共享文件
    - 检查用户是否有权限删除（上传者、分组管理员或系统管理员）
    - 删除物理文件
    - 清理向量索引（如果存在）
    - 清理知识库关联（如果存在）
    """
    file = Files.get_file_by_id(file_id)

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    # 检查是否是共享文件
    if file.space_type != "shared":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This is not a shared file",
        )

    # 检查删除权限
    # 1. 文件上传者可以删除
    # 2. 系统管理员可以删除
    # 3. 分组管理员可以删除（如果文件属于某个分组）
    is_file_owner = file.user_id == user.id
    is_admin = user.role == "admin"
    is_group_admin = False

    # 检查是否是分组管理员
    if file.space_id and file.space_id != "global":
        group = Groups.get_group_by_id(file.space_id)
        if group and group.user_id == user.id:
            is_group_admin = True

    if not (is_file_owner or is_admin or is_group_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to delete this file",
        )

    try:
        # 1. 删除物理文件
        from open_webui.config import UPLOAD_DIR
        
        if file.path:
            # 构建完整文件路径
            if os.path.isabs(file.path):
                file_path = file.path
            else:
                file_path = os.path.join(UPLOAD_DIR, file.path)
            
            if os.path.exists(file_path):
                os.remove(file_path)
                log.info(f"Deleted physical file: {file_path}")

        # 2. 清理向量索引（如果存在）
        try:
            VECTOR_DB_CLIENT.delete(collection_name=f"file-{file_id}")
            log.debug(f"Cleaned vector index for file: {file_id}")
        except Exception as e:
            log.warning(f"Failed to clean vector index: {e}")

        # 3. 清理知识库关联（如果存在）
        # 知识库关联会在删除文件记录时自动处理（如果数据库有外键约束）
        # 这里可以添加额外的清理逻辑
        log.debug(f"Cleaning knowledge base associations for file: {file_id}")

        # 4. 删除数据库记录
        success = Files.delete_file_by_id(file_id)
        
        if success:
            return {
                "status": True,
                "message": "File deleted successfully",
                "file_id": file_id,
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete file record from database",
            )

    except HTTPException:
        raise
    except Exception as e:
        log.exception(e)
        log.error(f"Error deleting shared file: {file_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ERROR_MESSAGES.DEFAULT(f"Error deleting file: {str(e)}"),
        )


############################
# Shared Files - Upload
############################


@router.post("/shared", response_model=FileModelResponse)
def upload_shared_file(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    group_id: Optional[str] = Form(None, description="分组ID，不传则上传到全局共享"),
    metadata: Optional[dict | str] = Form(None),
    process: bool = Query(True),
    process_in_background: bool = Query(True),
    user=Depends(get_verified_user),
):
    """
    上传文件到共享空间
    - group_id: 分组ID，不传或传 'global' 表示全局共享
    - 验证用户是否有权限上传到指定分组
    """
    # 确定 space_id
    if not group_id or group_id == "global":
        space_id = "global"
    else:
        # 验证分组是否存在
        group = Groups.get_group_by_id(group_id)
        if not group:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Group not found",
            )
        
        # 验证用户是否有权限上传到该分组
        accessible_group_ids = get_user_accessible_group_ids(user)
        if accessible_group_ids is not None and group_id not in accessible_group_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to upload to this group",
            )
        space_id = group_id

    # 解析 metadata
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.DEFAULT("Invalid metadata format"),
            )
    file_metadata = metadata if metadata else {}

    try:
        # 文件名安全处理
        unsanitized_filename = file.filename
        filename = os.path.basename(unsanitized_filename)
        # 移除路径分隔符，防止路径遍历攻击
        filename = filename.replace("/", "_").replace("\\", "_")

        file_extension = os.path.splitext(filename)[1]
        file_extension = file_extension[1:] if file_extension else ""

        # 文件类型验证（复用现有配置）
        if process and request.app.state.config.ALLOWED_FILE_EXTENSIONS:
            request.app.state.config.ALLOWED_FILE_EXTENSIONS = [
                ext for ext in request.app.state.config.ALLOWED_FILE_EXTENSIONS if ext
            ]
            if file_extension not in request.app.state.config.ALLOWED_FILE_EXTENSIONS:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ERROR_MESSAGES.DEFAULT(
                        f"File type {file_extension} is not allowed"
                    ),
                )

        # 生成文件ID和路径
        id = str(uuid.uuid4())
        name = filename
        filename = f"{id}_{filename}"

        # 确定存储路径（共享文件存储到 shared/ 目录）
        if space_id == "global":
            storage_subpath = "shared/global"
        else:
            storage_subpath = f"shared/groups/{space_id}"

        # 读取文件内容
        contents = file.file.read()
        if not contents:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.DEFAULT("File is empty"),
            )

        # 手动构建共享文件的存储路径
        from open_webui.config import UPLOAD_DIR
        
        # 创建子目录（如果不存在）
        shared_dir = os.path.join(UPLOAD_DIR, storage_subpath)
        os.makedirs(shared_dir, exist_ok=True)
        
        # 保存文件（绝对路径，保持与 Storage.upload_file 返回格式一致）
        file_path = os.path.join(shared_dir, filename)
        with open(file_path, "wb") as f:
            f.write(contents)

        # 创建文件记录（设置为共享文件）
        # 使用相对路径存储（与现有文件存储格式一致）
        file_item = Files.insert_new_file(
            user.id,
            FileForm(
                **{
                    "id": id,
                    "filename": name,
                    # 这里直接保存绝对路径，便于后续 content extraction / RAG 复用 Storage.get_file 逻辑
                    "path": file_path,
                    "space_type": "shared",  # 标记为共享文件
                    "space_id": space_id,    # 设置分组ID或'global'
                    "data": {
                        **({"status": "pending"} if process else {}),
                    },
                    "meta": {
                        "name": name,
                        "content_type": file.content_type,
                        "size": len(contents),
                        "data": file_metadata,
                    },
                }
            ),
        )

        # 检查是否是 Office 文档，如果是则添加后台转换任务（生成预览PDF缓存）
        # 注意：PDF只是预览缓存，不影响原文件
        is_office = _is_office_document(name, file.content_type or '')
        
        # 如果是 Office 文档，添加后台转换任务（上传后自动转换PDF预览，用户点击预览时无需等待）
        if is_office and background_tasks:
            def convert_office_preview():
                """后台转换 Office 文档为 PDF 预览（仅用于预览，不影响原文件）"""
                try:
                    file_path_obj = Path(file_path)
                    log.info(f"Starting background conversion for Office file: {file_path_obj.name}")
                    converted_pdf = convert_office_to_pdf(file_path_obj)
                    if converted_pdf:
                        log.info(f"Successfully converted Office file to PDF preview: {converted_pdf}")
                    else:
                        log.warning(f"Failed to convert Office file to PDF: {file_path_obj.name}")
                except Exception as e:
                    log.exception(f"Error in background Office conversion: {e}")
            
            # 添加后台转换任务（不阻塞上传响应）
            background_tasks.add_task(convert_office_preview)
            log.info(f"Added background conversion task for Office file: {name} (PDF preview will be ready for viewing)")

        if process:
            if background_tasks and process_in_background:
                background_tasks.add_task(
                    process_uploaded_file,
                    request,
                    file,
                    file_path,
                    file_item,
                    file_metadata,
                    user,
                )
                return {"status": True, **file_item.model_dump()}
            else:
                process_uploaded_file(
                    request,
                    file,
                    file_path,
                    file_item,
                    file_metadata,
                    user,
                )
                return {"status": True, **file_item.model_dump()}
        else:
            if file_item:
                return file_item
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ERROR_MESSAGES.DEFAULT("Error uploading file"),
                )

    except HTTPException:
        raise
    except Exception as e:
        log.exception(e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT(f"Error uploading shared file: {str(e)}"),
        )


############################
# Upload File
############################


def process_uploaded_file(request, file, file_path, file_item, file_metadata, user):
    try:
        if file.content_type:
            stt_supported_content_types = getattr(
                request.app.state.config, "STT_SUPPORTED_CONTENT_TYPES", []
            )

            if any(
                fnmatch(file.content_type, content_type)
                for content_type in (
                    stt_supported_content_types
                    if stt_supported_content_types
                    and any(t.strip() for t in stt_supported_content_types)
                    else ["audio/*", "video/webm"]
                )
            ):
                file_path = Storage.get_file(file_path)
                result = transcribe(request, file_path, file_metadata, user)

                process_file(
                    request,
                    ProcessFileForm(
                        file_id=file_item.id, content=result.get("text", "")
                    ),
                    user=user,
                )
            elif (not file.content_type.startswith(("image/", "video/"))) or (
                request.app.state.config.CONTENT_EXTRACTION_ENGINE == "external"
            ):
                process_file(request, ProcessFileForm(file_id=file_item.id), user=user)
            else:
                raise Exception(
                    f"File type {file.content_type} is not supported for processing"
                )
        else:
            log.info(
                f"File type {file.content_type} is not provided, but trying to process anyway"
            )
            process_file(request, ProcessFileForm(file_id=file_item.id), user=user)
    except Exception as e:
        log.error(f"Error processing file: {file_item.id}")
        Files.update_file_data_by_id(
            file_item.id,
            {
                "status": "failed",
                "error": str(e.detail) if hasattr(e, "detail") else str(e),
            },
        )


@router.post("/", response_model=FileModelResponse)
def upload_file(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    metadata: Optional[dict | str] = Form(None),
    process: bool = Query(True),
    process_in_background: bool = Query(True),
    user=Depends(get_verified_user),
):
    return upload_file_handler(
        request,
        file=file,
        metadata=metadata,
        process=process,
        process_in_background=process_in_background,
        user=user,
        background_tasks=background_tasks,
    )


def upload_file_handler(
    request: Request,
    file: UploadFile = File(...),
    metadata: Optional[dict | str] = Form(None),
    process: bool = Query(True),
    process_in_background: bool = Query(True),
    user=Depends(get_verified_user),
    background_tasks: Optional[BackgroundTasks] = None,
):
    log.info(f"file.content_type: {file.content_type}")

    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.DEFAULT("Invalid metadata format"),
            )
    file_metadata = metadata if metadata else {}

    try:
        unsanitized_filename = file.filename
        filename = os.path.basename(unsanitized_filename)

        file_extension = os.path.splitext(filename)[1]
        # Remove the leading dot from the file extension
        file_extension = file_extension[1:] if file_extension else ""

        if process and request.app.state.config.ALLOWED_FILE_EXTENSIONS:
            request.app.state.config.ALLOWED_FILE_EXTENSIONS = [
                ext for ext in request.app.state.config.ALLOWED_FILE_EXTENSIONS if ext
            ]

            if file_extension not in request.app.state.config.ALLOWED_FILE_EXTENSIONS:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ERROR_MESSAGES.DEFAULT(
                        f"File type {file_extension} is not allowed"
                    ),
                )

        # replace filename with uuid
        id = str(uuid.uuid4())
        name = filename
        filename = f"{id}_{filename}"
        contents, file_path = Storage.upload_file(
            file.file,
            filename,
            {
                "OpenWebUI-User-Email": user.email,
                "OpenWebUI-User-Id": user.id,
                "OpenWebUI-User-Name": user.name,
                "OpenWebUI-File-Id": id,
            },
        )

        file_item = Files.insert_new_file(
            user.id,
            FileForm(
                **{
                    "id": id,
                    "filename": name,
                    "path": file_path,
                    "data": {
                        **({"status": "pending"} if process else {}),
                    },
                    "meta": {
                        "name": name,
                        "content_type": file.content_type,
                        "size": len(contents),
                        "data": file_metadata,
                    },
                }
            ),
        )

        if process:
            if background_tasks and process_in_background:
                background_tasks.add_task(
                    process_uploaded_file,
                    request,
                    file,
                    file_path,
                    file_item,
                    file_metadata,
                    user,
                )
                return {"status": True, **file_item.model_dump()}
            else:
                process_uploaded_file(
                    request,
                    file,
                    file_path,
                    file_item,
                    file_metadata,
                    user,
                )
                return {"status": True, **file_item.model_dump()}
        else:
            if file_item:
                return file_item
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ERROR_MESSAGES.DEFAULT("Error uploading file"),
                )

    except Exception as e:
        log.exception(e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT("Error uploading file"),
        )


############################
# List Files
############################


@router.get("/", response_model=list[FileModelResponse])
async def list_files(user=Depends(get_verified_user), content: bool = Query(True)):
    if user.role == "admin":
        files = Files.get_files()
    else:
        files = Files.get_files_by_user_id(user.id)

    if not content:
        for file in files:
            if "content" in file.data:
                del file.data["content"]

    return files


############################
# Search Files
############################


@router.get("/search", response_model=list[FileModelResponse])
async def search_files(
    filename: str = Query(
        ...,
        description="Filename pattern to search for. Supports wildcards such as '*.txt'",
    ),
    content: bool = Query(True),
    user=Depends(get_verified_user),
):
    """
    Search for files by filename with support for wildcard patterns.
    """
    # Get files according to user role
    if user.role == "admin":
        files = Files.get_files()
    else:
        files = Files.get_files_by_user_id(user.id)

    # Get matching files
    matching_files = [
        file for file in files if fnmatch(file.filename.lower(), filename.lower())
    ]

    if not matching_files:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No files found matching the pattern.",
        )

    if not content:
        for file in matching_files:
            if "content" in file.data:
                del file.data["content"]

    return matching_files


############################
# Delete All Files
############################


@router.delete("/all")
async def delete_all_files(user=Depends(get_admin_user)):
    result = Files.delete_all_files()
    if result:
        try:
            Storage.delete_all_files()
            VECTOR_DB_CLIENT.reset()
        except Exception as e:
            log.exception(e)
            log.error("Error deleting files")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.DEFAULT("Error deleting files"),
            )
        return {"message": "All files deleted successfully"}
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT("Error deleting files"),
        )


############################
# Get File By Id
############################


@router.get("/{id}", response_model=Optional[FileModel])
async def get_file_by_id(id: str, user=Depends(get_verified_user)):
    file = Files.get_file_by_id(id)

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if (
        file.user_id == user.id
        or user.role == "admin"
        or has_access_to_file(id, "read", user)
    ):
        return file
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


@router.get("/{id}/process/status")
async def get_file_process_status(
    id: str, stream: bool = Query(False), user=Depends(get_verified_user)
):
    file = Files.get_file_by_id(id)

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if (
        file.user_id == user.id
        or user.role == "admin"
        or has_access_to_file(id, "read", user)
    ):
        if stream:
            MAX_FILE_PROCESSING_DURATION = 3600 * 2

            async def event_stream(file_item):
                if file_item:
                    for _ in range(MAX_FILE_PROCESSING_DURATION):
                        file_item = Files.get_file_by_id(file_item.id)
                        if file_item:
                            data = file_item.model_dump().get("data", {})
                            status = data.get("status")

                            if status:
                                event = {"status": status}
                                if status == "failed":
                                    event["error"] = data.get("error")

                                yield f"data: {json.dumps(event)}\n\n"
                                if status in ("completed", "failed"):
                                    break
                            else:
                                # Legacy
                                break

                        await asyncio.sleep(0.5)
                else:
                    yield f"data: {json.dumps({'status': 'not_found'})}\n\n"

            return StreamingResponse(
                event_stream(file),
                media_type="text/event-stream",
            )
        else:
            return {"status": file.data.get("status", "pending")}
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


############################
# Get File Data Content By Id
############################


@router.get("/{id}/data/content")
async def get_file_data_content_by_id(id: str, user=Depends(get_verified_user)):
    file = Files.get_file_by_id(id)

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if (
        file.user_id == user.id
        or user.role == "admin"
        or has_access_to_file(id, "read", user)
    ):
        return {"content": file.data.get("content", "")}
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


############################
# Update File Data Content By Id
############################


class ContentForm(BaseModel):
    content: str


@router.post("/{id}/data/content/update")
async def update_file_data_content_by_id(
    request: Request, id: str, form_data: ContentForm, user=Depends(get_verified_user)
):
    file = Files.get_file_by_id(id)

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if (
        file.user_id == user.id
        or user.role == "admin"
        or has_access_to_file(id, "write", user)
    ):
        try:
            process_file(
                request,
                ProcessFileForm(file_id=id, content=form_data.content),
                user=user,
            )
            file = Files.get_file_by_id(id=id)
        except Exception as e:
            log.exception(e)
            log.error(f"Error processing file: {file.id}")

        return {"content": file.data.get("content", "")}
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


############################
# Get File Content By Id
############################


@router.get("/{id}/content")
async def get_file_content_by_id(
    id: str, user=Depends(get_verified_user), attachment: bool = Query(False)
):
    file = Files.get_file_by_id(id)

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if (
        file.user_id == user.id
        or user.role == "admin"
        or has_access_to_file(id, "read", user)
    ):
        try:
            file_path = Storage.get_file(file.path)
            file_path = Path(file_path)

            # Check if the file already exists in the cache
            if file_path.is_file():
                # Handle Unicode filenames
                filename = file.meta.get("name", file.filename)
                encoded_filename = quote(filename)  # RFC5987 encoding

                content_type = file.meta.get("content_type")
                filename = file.meta.get("name", file.filename)
                encoded_filename = quote(filename)
                headers = {}

                if attachment:
                    headers["Content-Disposition"] = (
                        f"attachment; filename*=UTF-8''{encoded_filename}"
                    )
                else:
                    if content_type == "application/pdf" or filename.lower().endswith(
                        ".pdf"
                    ):
                        headers["Content-Disposition"] = (
                            f"inline; filename*=UTF-8''{encoded_filename}"
                        )
                        content_type = "application/pdf"
                    elif content_type != "text/plain":
                        headers["Content-Disposition"] = (
                            f"attachment; filename*=UTF-8''{encoded_filename}"
                        )

                return FileResponse(file_path, headers=headers, media_type=content_type)

            else:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=ERROR_MESSAGES.NOT_FOUND,
                )
        except Exception as e:
            log.exception(e)
            log.error("Error getting file content")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.DEFAULT("Error getting file content"),
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


@router.get("/{id}/content/html")
async def get_html_file_content_by_id(id: str, user=Depends(get_verified_user)):
    file = Files.get_file_by_id(id)

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    file_user = Users.get_user_by_id(file.user_id)
    if not file_user.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if (
        file.user_id == user.id
        or user.role == "admin"
        or has_access_to_file(id, "read", user)
    ):
        try:
            file_path = Storage.get_file(file.path)
            file_path = Path(file_path)

            # Check if the file already exists in the cache
            if file_path.is_file():
                log.info(f"file_path: {file_path}")
                return FileResponse(file_path)
            else:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=ERROR_MESSAGES.NOT_FOUND,
                )
        except Exception as e:
            log.exception(e)
            log.error("Error getting file content")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.DEFAULT("Error getting file content"),
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


@router.get("/{id}/content/{file_name}")
async def get_file_content_by_id(id: str, user=Depends(get_verified_user)):
    file = Files.get_file_by_id(id)

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if (
        file.user_id == user.id
        or user.role == "admin"
        or has_access_to_file(id, "read", user)
    ):
        file_path = file.path

        # Handle Unicode filenames
        filename = file.meta.get("name", file.filename)
        encoded_filename = quote(filename)  # RFC5987 encoding
        headers = {
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
        }

        if file_path:
            file_path = Storage.get_file(file_path)
            file_path = Path(file_path)

            # Check if the file already exists in the cache
            if file_path.is_file():
                return FileResponse(file_path, headers=headers)
            else:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=ERROR_MESSAGES.NOT_FOUND,
                )
        else:
            # File path doesn’t exist, return the content as .txt if possible
            file_content = file.content.get("content", "")
            file_name = file.filename

            # Create a generator that encodes the file content
            def generator():
                yield file_content.encode("utf-8")

            return StreamingResponse(
                generator(),
                media_type="text/plain",
                headers=headers,
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


############################
# Delete File By Id
############################


@router.delete("/{id}")
async def delete_file_by_id(id: str, user=Depends(get_verified_user)):
    file = Files.get_file_by_id(id)

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if (
        file.user_id == user.id
        or user.role == "admin"
        or has_access_to_file(id, "write", user)
    ):

        result = Files.delete_file_by_id(id)
        if result:
            try:
                Storage.delete_file(file.path)
                VECTOR_DB_CLIENT.delete(collection_name=f"file-{id}")
            except Exception as e:
                log.exception(e)
                log.error("Error deleting files")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ERROR_MESSAGES.DEFAULT("Error deleting files"),
                )
            return {"message": "File deleted successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.DEFAULT("Error deleting file"),
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )
