from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

# Celery tasks run synchronously in worker processes, so this is a
# deliberately separate *sync* engine from app.db.session's async one --
# mixing an asyncio event loop into a Celery worker is more trouble than
# it's worth. Same Postgres, different driver (psycopg2 instead of asyncpg).
_sync_database_url = settings.database_url.replace(
    "postgresql+asyncpg://", "postgresql+psycopg2://"
)

sync_engine = create_engine(_sync_database_url, pool_pre_ping=True)

WorkerSessionLocal = sessionmaker(bind=sync_engine, autoflush=False, expire_on_commit=False)


def get_worker_session() -> Session:
    return WorkerSessionLocal()
