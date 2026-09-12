from fastapi import APIRouter

router = APIRouter()


@router.api_route("/health", methods=["GET", "HEAD"])
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
