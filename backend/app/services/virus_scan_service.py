"""Virus scanning on upload (Sprint 25, US-105).

Scans run against a clamd daemon over TCP using the standard INSTREAM protocol.
With no `CLAMAV_HOST` configured, scanning is skipped entirely — the same
degrade-gracefully treatment every other optional integration in this codebase
gets (`ai_service`, `etims_service`, the accounting OAuth connections). A
daemon that is configured but unreachable at scan time does not block the
upload either: virus scanning here is defence in depth, not the thing standing
between a landlord and a working upload button. A failed scan is recorded as
such so the retry sweep (`rentflow.rescan_stored_files`) can pick it up later.
"""

import io
import logging
from dataclasses import dataclass
from functools import lru_cache

from app.core.config import settings
from app.models.file import ScanStatus

logger = logging.getLogger("rentflow.virus_scan")


@dataclass(slots=True)
class ScanOutcome:
    status: ScanStatus
    detail: str | None = None


@lru_cache
def _client():  # type: ignore[no-untyped-def]
    import clamd

    return clamd.ClamdNetworkSocket(
        host=settings.CLAMAV_HOST, port=settings.CLAMAV_PORT, timeout=settings.CLAMAV_TIMEOUT_SECONDS
    )


def scan_bytes(data: bytes) -> ScanOutcome:
    """Scan one file's contents. Never raises — a scanning problem is reported
    as a `ScanOutcome`, not an exception, so a caller can always decide what to
    do with it rather than being forced into an error path."""
    if not settings.clamav_configured:
        return ScanOutcome(status=ScanStatus.SKIPPED, detail="ClamAV not configured")

    try:
        result = _client().instream(io.BytesIO(data))
    except Exception as exc:  # daemon down, connection refused, timeout, ...
        logger.warning("ClamAV scan failed: %s", exc)
        return ScanOutcome(status=ScanStatus.FAILED, detail=str(exc)[:255])

    verdict, signature = result.get("stream", ("ERROR", None))
    if verdict == "OK":
        return ScanOutcome(status=ScanStatus.CLEAN)
    if verdict == "FOUND":
        return ScanOutcome(status=ScanStatus.INFECTED, detail=signature)
    return ScanOutcome(status=ScanStatus.FAILED, detail=f"Unexpected ClamAV verdict: {verdict}")
