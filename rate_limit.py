"""
IP 기반 in-memory rate limiter.
Railway 단일 인스턴스 배포 환경 가정 (다중 인스턴스 시 Redis 기반으로 교체 필요).
"""
from collections import defaultdict
from time import time

from fastapi import HTTPException, Request

from config import settings

_WINDOW_SECONDS = 60
_request_log: dict[str, list[float]] = defaultdict(list)


def _prune(client_ip: str, now: float) -> None:
    _request_log[client_ip] = [t for t in _request_log[client_ip] if now - t < _WINDOW_SECONDS]


def llm_rate_limit(request: Request) -> None:
    """LLM 생성 엔드포인트 호출 빈도 제한. FastAPI Depends로 사용."""
    client_ip = request.client.host if request.client else "unknown"
    now = time()
    _prune(client_ip, now)

    limit = settings.llm_rate_limit_per_minute
    if len(_request_log[client_ip]) >= limit:
        oldest = _request_log[client_ip][0]
        retry_after = max(1, int(_WINDOW_SECONDS - (now - oldest)))
        raise HTTPException(
            status_code=429,
            detail=f"요청이 너무 많습니다. {retry_after}초 후 다시 시도하세요.",
            headers={"Retry-After": str(retry_after)},
        )
    _request_log[client_ip].append(now)
