"""
SentinelTwin — Async Database Engine
SQLAlchemy + asyncpg + TimescaleDB
Connection pooling, health checking, migration support
"""

import logging
from typing import Dict, Optional

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import AsyncAdaptedQueuePool
from sqlalchemy import text
from sqlalchemy.orm import declarative_base

from core.config import settings

log = logging.getLogger("sentineltwin.database")

Base = declarative_base()

# Production async engine
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DB_ECHO,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_pre_ping=True,
    pool_recycle=3600,
    connect_args={
        "command_timeout": 30,
        "server_settings": {
            "application_name": "sentineltwin",
            "search_path": "public",
        },
    },
)

# Session factory
AsyncSessionFactory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db():
    """Dependency injection for FastAPI routes"""
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_db_health() -> Dict:
    """Check database connectivity and TimescaleDB extension"""
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT version()"))
            pg_version = result.scalar()
            try:
                ts_result = await conn.execute(
                    text("SELECT extversion FROM pg_extension WHERE extname = 'timescaledb'")
                )
                ts_version = ts_result.scalar() or "not installed"
            except Exception:
                ts_version = "not installed"
        return {
            "status": "healthy",
            "postgresql": pg_version[:50] if pg_version else "unknown",
            "timescaledb": ts_version,
        }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
