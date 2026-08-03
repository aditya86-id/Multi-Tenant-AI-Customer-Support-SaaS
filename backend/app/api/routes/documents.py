import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import CurrentUser, get_current_user, require_role
from app.db.session import get_db
from app.models.document import Document
from app.schemas.document import DocumentResponse
from app.worker.tasks import ingest_document

router = APIRouter(prefix="/documents", tags=["documents"])
settings = get_settings()

ALLOWED_EXTENSIONS = {".txt", ".md", ".pdf"}


@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Document]:
    result = await db.execute(
        select(Document)
        .where(Document.tenant_id == current_user.tenant_id)
        .order_by(Document.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Document:
    result = await db.execute(
        select(Document).where(
            Document.id == document_id, Document.tenant_id == current_user.tenant_id
        )
    )
    document = result.scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile,
    current_user: CurrentUser = Depends(require_role("admin", "agent")),
    db: AsyncSession = Depends(get_db),
) -> Document:
    """
    Accepts a knowledge-base file, stores it, and queues async ingestion
    (chunk + embed) scoped to the uploader's tenant. The Celery task is
    handed tenant_id explicitly so ingestion can never drift onto another
    tenant's data even if a document_id collided.
    """
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No filename provided")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{suffix}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    contents = await file.read()
    if len(contents) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {settings.max_upload_size_bytes // (1024 * 1024)} MB limit",
        )
    if not contents:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty")

    document = Document(
        tenant_id=current_user.tenant_id,
        uploaded_by=current_user.id,
        filename=file.filename,
        source_type="upload",
        status="pending",
    )
    db.add(document)
    await db.flush()  # assigns document.id before we build the storage path

    tenant_dir = Path(settings.upload_dir) / str(current_user.tenant_id)
    tenant_dir.mkdir(parents=True, exist_ok=True)
    storage_path = tenant_dir / f"{document.id}{suffix}"

    try:
        storage_path.write_bytes(contents)
    except OSError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not save uploaded file: {exc}",
        )

    document.storage_path = str(storage_path)
    await db.commit()
    await db.refresh(document)

    ingest_document.delay(str(document.id), str(current_user.tenant_id))

    return document
