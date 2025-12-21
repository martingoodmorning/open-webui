import logging
import time
from typing import Optional

from open_webui.internal.db import Base, JSONField, get_db
from open_webui.env import SRC_LOG_LEVELS
from pydantic import BaseModel, ConfigDict
from sqlalchemy import BigInteger, Column, String, Text, JSON, or_

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MODELS"])

####################
# Files DB Schema
####################


class File(Base):
    __tablename__ = "file"
    id = Column(String, primary_key=True, unique=True)
    user_id = Column(String)
    hash = Column(Text, nullable=True)

    filename = Column(Text)
    path = Column(Text, nullable=True)

    data = Column(JSON, nullable=True)
    meta = Column(JSON, nullable=True)

    access_control = Column(JSON, nullable=True)

    # 共享文件空间字段
    space_type = Column(String(20), default="personal")  # 'personal' | 'shared'
    space_id = Column(String(255), nullable=True)  # 个人文件为user_id，共享文件为'global'或group_id

    created_at = Column(BigInteger)
    updated_at = Column(BigInteger)


class FileModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    hash: Optional[str] = None

    filename: str
    path: Optional[str] = None

    data: Optional[dict] = None
    meta: Optional[dict] = None

    access_control: Optional[dict] = None

    # 共享文件空间字段
    space_type: Optional[str] = "personal"  # 'personal' | 'shared'
    space_id: Optional[str] = None  # 个人文件为user_id，共享文件为'global'或group_id

    created_at: Optional[int]  # timestamp in epoch
    updated_at: Optional[int]  # timestamp in epoch


####################
# Forms
####################


class FileMeta(BaseModel):
    name: Optional[str] = None
    content_type: Optional[str] = None
    size: Optional[int] = None

    model_config = ConfigDict(extra="allow")


class FileModelResponse(BaseModel):
    id: str
    user_id: str
    hash: Optional[str] = None

    filename: str
    data: Optional[dict] = None
    meta: FileMeta

    created_at: int  # timestamp in epoch
    updated_at: int  # timestamp in epoch

    model_config = ConfigDict(extra="allow")


class FileMetadataResponse(BaseModel):
    id: str
    hash: Optional[str] = None
    meta: dict
    created_at: int  # timestamp in epoch
    updated_at: int  # timestamp in epoch


class FileForm(BaseModel):
    id: str
    hash: Optional[str] = None
    filename: str
    path: str
    data: dict = {}
    meta: dict = {}
    access_control: Optional[dict] = None
    space_type: Optional[str] = "personal"  # 'personal' | 'shared'
    space_id: Optional[str] = None  # 个人文件为user_id，共享文件为'global'或group_id


class FileUpdateForm(BaseModel):
    hash: Optional[str] = None
    data: Optional[dict] = None
    meta: Optional[dict] = None


class FilesTable:
    def insert_new_file(self, user_id: str, form_data: FileForm) -> Optional[FileModel]:
        with get_db() as db:
            file = FileModel(
                **{
                    **form_data.model_dump(),
                    "user_id": user_id,
                    "created_at": int(time.time()),
                    "updated_at": int(time.time()),
                }
            )

            try:
                result = File(**file.model_dump())
                db.add(result)
                db.commit()
                db.refresh(result)
                if result:
                    return FileModel.model_validate(result)
                else:
                    return None
            except Exception as e:
                log.exception(f"Error inserting a new file: {e}")
                return None

    def get_file_by_id(self, id: str) -> Optional[FileModel]:
        with get_db() as db:
            try:
                file = db.get(File, id)
                return FileModel.model_validate(file)
            except Exception:
                return None

    def get_file_by_id_and_user_id(self, id: str, user_id: str) -> Optional[FileModel]:
        with get_db() as db:
            try:
                file = db.query(File).filter_by(id=id, user_id=user_id).first()
                if file:
                    return FileModel.model_validate(file)
                else:
                    return None
            except Exception:
                return None

    def get_file_metadata_by_id(self, id: str) -> Optional[FileMetadataResponse]:
        with get_db() as db:
            try:
                file = db.get(File, id)
                return FileMetadataResponse(
                    id=file.id,
                    hash=file.hash,
                    meta=file.meta,
                    created_at=file.created_at,
                    updated_at=file.updated_at,
                )
            except Exception:
                return None

    def get_files(self) -> list[FileModel]:
        with get_db() as db:
            return [FileModel.model_validate(file) for file in db.query(File).all()]

    def check_access_by_user_id(self, id, user_id, permission="write") -> bool:
        file = self.get_file_by_id(id)
        if not file:
            return False
        if file.user_id == user_id:
            return True
        # Implement additional access control logic here as needed
        return False

    def get_files_by_ids(self, ids: list[str]) -> list[FileModel]:
        with get_db() as db:
            return [
                FileModel.model_validate(file)
                for file in db.query(File)
                .filter(File.id.in_(ids))
                .order_by(File.updated_at.desc())
                .all()
            ]

    def get_file_metadatas_by_ids(self, ids: list[str]) -> list[FileMetadataResponse]:
        with get_db() as db:
            return [
                FileMetadataResponse(
                    id=file.id,
                    hash=file.hash,
                    meta=file.meta,
                    created_at=file.created_at,
                    updated_at=file.updated_at,
                )
                for file in db.query(
                    File.id, File.hash, File.meta, File.created_at, File.updated_at
                )
                .filter(File.id.in_(ids))
                .order_by(File.updated_at.desc())
                .all()
            ]

    def get_files_by_user_id(self, user_id: str) -> list[FileModel]:
        with get_db() as db:
            return [
                FileModel.model_validate(file)
                for file in db.query(File).filter_by(user_id=user_id).all()
            ]

    def get_shared_files(
        self,
        space_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        order_by: str = "updated_at",
        order: str = "desc",
        search: Optional[str] = None,
        file_type: Optional[str] = None,
        start_date: Optional[int] = None,
        end_date: Optional[int] = None,
    ) -> tuple[list[FileModel], int]:
        """
        获取共享文件列表
        Args:
            space_id: 空间ID（'global' 或 group_id），None 表示所有共享文件
            page: 页码
            page_size: 每页数量
            order_by: 排序字段
            order: 排序方向（'asc' | 'desc'）
            search: 搜索关键词（文件名模糊匹配）
            file_type: 文件类型过滤（如 'pdf', 'image', 'office'）
            start_date: 开始时间戳（Unix timestamp）
            end_date: 结束时间戳（Unix timestamp）
        Returns:
            (文件列表, 总数)
        """
        with get_db() as db:
            query = db.query(File).filter_by(space_type="shared")

            # 如果指定了 space_id，则过滤
            if space_id:
                query = query.filter_by(space_id=space_id)

            # 搜索关键词（文件名模糊匹配）
            if search:
                search_pattern = f"%{search}%"
                query = query.filter(File.filename.ilike(search_pattern))

            # 文件类型过滤
            if file_type:
                if file_type == "pdf":
                    query = query.filter(
                        or_(
                            File.filename.ilike("%.pdf"),
                            File.meta["content_type"].astext == "application/pdf"
                        )
                    )
                elif file_type == "image":
                    query = query.filter(
                        or_(
                            File.filename.ilike("%.jpg"),
                            File.filename.ilike("%.jpeg"),
                            File.filename.ilike("%.png"),
                            File.filename.ilike("%.gif"),
                            File.filename.ilike("%.webp"),
                            File.filename.ilike("%.svg"),
                            File.meta["content_type"].astext.like("image/%")
                        )
                    )
                elif file_type == "office":
                    query = query.filter(
                        or_(
                            File.filename.ilike("%.doc%"),
                            File.filename.ilike("%.xls%"),
                            File.filename.ilike("%.ppt%"),
                            File.meta["content_type"].astext.like("application/msword%"),
                            File.meta["content_type"].astext.like("application/vnd.openxmlformats%"),
                            File.meta["content_type"].astext.like("application/vnd.ms-%")
                        )
                    )
                elif file_type == "text":
                    query = query.filter(
                        or_(
                            File.filename.ilike("%.txt"),
                            File.filename.ilike("%.md"),
                            File.filename.ilike("%.json"),
                            File.filename.ilike("%.xml"),
                            File.filename.ilike("%.csv"),
                            File.meta["content_type"].astext.like("text/%")
                        )
                    )

            # 时间范围过滤
            if start_date:
                query = query.filter(File.created_at >= start_date)
            if end_date:
                query = query.filter(File.created_at <= end_date)

            # 获取总数
            total = query.count()

            # 排序
            order_column = getattr(File, order_by, File.updated_at)
            if order == "desc":
                query = query.order_by(order_column.desc())
            else:
                query = query.order_by(order_column.asc())

            # 分页
            offset = (page - 1) * page_size
            files = query.offset(offset).limit(page_size).all()

            return [FileModel.model_validate(file) for file in files], total

    def update_file_by_id(
        self, id: str, form_data: FileUpdateForm
    ) -> Optional[FileModel]:
        with get_db() as db:
            try:
                file = db.query(File).filter_by(id=id).first()

                if form_data.hash is not None:
                    file.hash = form_data.hash

                if form_data.data is not None:
                    file.data = {**(file.data if file.data else {}), **form_data.data}

                if form_data.meta is not None:
                    file.meta = {**(file.meta if file.meta else {}), **form_data.meta}

                file.updated_at = int(time.time())
                db.commit()
                return FileModel.model_validate(file)
            except Exception as e:
                log.exception(f"Error updating file completely by id: {e}")
                return None

    def update_file_hash_by_id(self, id: str, hash: str) -> Optional[FileModel]:
        with get_db() as db:
            try:
                file = db.query(File).filter_by(id=id).first()
                file.hash = hash
                db.commit()

                return FileModel.model_validate(file)
            except Exception:
                return None

    def update_file_data_by_id(self, id: str, data: dict) -> Optional[FileModel]:
        with get_db() as db:
            try:
                file = db.query(File).filter_by(id=id).first()
                file.data = {**(file.data if file.data else {}), **data}
                db.commit()
                return FileModel.model_validate(file)
            except Exception as e:

                return None

    def update_file_metadata_by_id(self, id: str, meta: dict) -> Optional[FileModel]:
        with get_db() as db:
            try:
                file = db.query(File).filter_by(id=id).first()
                file.meta = {**(file.meta if file.meta else {}), **meta}
                db.commit()
                return FileModel.model_validate(file)
            except Exception:
                return None

    def delete_file_by_id(self, id: str) -> bool:
        with get_db() as db:
            try:
                db.query(File).filter_by(id=id).delete()
                db.commit()

                return True
            except Exception:
                return False

    def delete_all_files(self) -> bool:
        with get_db() as db:
            try:
                db.query(File).delete()
                db.commit()

                return True
            except Exception:
                return False


Files = FilesTable()
