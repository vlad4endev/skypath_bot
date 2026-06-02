"""
Подключение к PostgreSQL
"""
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from database.models import Base
import os

DATABASE_URL = os.getenv("DB_URL", "postgresql+asyncpg://vpnbot:password@localhost:5432/skypath")

engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
    echo=False,
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """Создать таблицы при старте"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    """Получить сессию (для DI)"""
    async with async_session() as session:
        yield session
