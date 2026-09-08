"""Bridge between Celery's synchronous workers and the app's async services.

Split out of `app.tasks.scheduled` so that other task modules (webhook
delivery, customer-success scoring) can use `run_async` without importing
`scheduled` itself — that module imports several domain services which, in
turn, import back into the tasks package, and pulling in the whole scheduled-
jobs module just for this one helper closed the loop unnecessarily.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

T = TypeVar("T")


def run_async(coro_factory: Callable[[AsyncSession], Awaitable[T]]) -> T:
    """Run one async unit of work against a fresh engine and session.

    A per-task engine avoids sharing a connection pool across Celery's forked
    workers, which is a classic source of 'connection already closed' errors.
    """

    async def _run() -> T:
        engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
        factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
        try:
            async with factory() as session:
                return await coro_factory(session)
        finally:
            await engine.dispose()

    return asyncio.run(_run())
