import logging
import uuid

from celery.exceptions import MaxRetriesExceededError
from sqlalchemy import select

from app.core.config import get_settings
from app.models.chunk import Chunk
from app.models.document import Document
from app.services.chunking import chunk_text
from app.services.embeddings import EmbeddingError, embed_documents
from app.services.text_extraction import UnsupportedFileTypeError, extract_text
from app.worker.celery_app import celery_app
from app.worker.db import get_worker_session

logger = logging.getLogger("support_saas.worker")
settings = get_settings()

# Embed in batches rather than one giant call -- keeps individual API
# requests reasonably sized and bounds memory for very large documents.
EMBED_BATCH_SIZE = 50


@celery_app.task(bind=True, max_retries=3, default_retry_delay=30)
def ingest_document(self, document_id: str, tenant_id: str) -> None:
    """
    Chunks and embeds a single document, scoped to its tenant.

    tenant_id is taken as an explicit argument (not looked up from the
    document alone) so a queued job can never silently drift onto another
    tenant's data even if document_id were somehow reused or guessed --
    every DB query in this task filters by both id and tenant_id.
    """
    session = get_worker_session()
    try:
        document = session.execute(
            select(Document).where(
                Document.id == uuid.UUID(document_id),
                Document.tenant_id == uuid.UUID(tenant_id),
            )
        ).scalar_one_or_none()

        if document is None:
            logger.error(
                "ingest_document: no document %s for tenant %s -- skipping",
                document_id,
                tenant_id,
            )
            return

        document.status = "processing"
        document.error_message = None
        session.commit()

        try:
            raw_text = extract_text(document.storage_path, document.filename)
        except (UnsupportedFileTypeError, FileNotFoundError) as exc:
            # Permanent failure -- retrying won't help a bad file type or a
            # missing file, so fail immediately instead of burning retries.
            document.status = "failed"
            document.error_message = str(exc)[:500]
            session.commit()
            logger.warning("ingest_document: permanent failure for %s: %s", document_id, exc)
            return

        chunks = chunk_text(
            raw_text,
            chunk_size_chars=settings.chunk_size_chars,
            overlap_chars=settings.chunk_overlap_chars,
        )

        if not chunks:
            document.status = "failed"
            document.error_message = "No extractable text content found in document"
            session.commit()
            return

        # Remove any chunks from a previous failed/partial attempt before
        # re-ingesting, so retries don't duplicate rows.
        session.query(Chunk).filter(
            Chunk.document_id == document.id, Chunk.tenant_id == document.tenant_id
        ).delete()
        session.commit()

        for batch_start in range(0, len(chunks), EMBED_BATCH_SIZE):
            batch = chunks[batch_start : batch_start + EMBED_BATCH_SIZE]
            embeddings = embed_documents(batch)  # raises EmbeddingError on failure

            for offset, (content, embedding) in enumerate(zip(batch, embeddings)):
                session.add(
                    Chunk(
                        tenant_id=document.tenant_id,
                        document_id=document.id,
                        chunk_index=batch_start + offset,
                        content=content,
                        embedding=embedding,
                        token_count=len(content) // 4,  # rough estimate, not exact
                    )
                )
            session.commit()

        document.status = "ready"
        session.commit()
        logger.info(
            "ingest_document: tenant=%s document=%s ingested %d chunks",
            tenant_id,
            document_id,
            len(chunks),
        )

    except EmbeddingError as exc:
        session.rollback()
        logger.warning(
            "ingest_document: embedding error for %s (attempt %d/%d): %s",
            document_id,
            self.request.retries + 1,
            self.max_retries + 1,
            exc,
        )
        try:
            raise self.retry(exc=exc)
        except MaxRetriesExceededError:
            document = session.execute(
                select(Document).where(Document.id == uuid.UUID(document_id))
            ).scalar_one_or_none()
            if document is not None:
                document.status = "failed"
                document.error_message = f"Embedding failed after retries: {exc}"[:500]
                session.commit()

    except Exception as exc:  # noqa: BLE001 -- last-resort guard, never leave a document stuck
        session.rollback()
        logger.exception("ingest_document: unexpected error for %s", document_id)
        document = session.execute(
            select(Document).where(Document.id == uuid.UUID(document_id))
        ).scalar_one_or_none()
        if document is not None:
            document.status = "failed"
            document.error_message = f"Unexpected error: {exc}"[:500]
            session.commit()

    finally:
        session.close()
