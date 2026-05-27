from fastapi import APIRouter, Query
from services.rag_service import vectorize_all_questions, search_similar_questions, embed_text
from models.question import Question

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/vectorize")
async def vectorize(force: bool = Query(default=False, description="이미 임베딩된 문제도 재생성")):
    """
    DB의 모든 문제에 임베딩 벡터를 생성하여 저장합니다.
    Atlas Vector Search 인덱스 생성 후 1회 실행하세요.
    force=true이면 기존 임베딩을 덮어씁니다.
    """
    result = await vectorize_all_questions(force=force)
    return result


@router.get("/rag-status")
async def rag_status():
    """임베딩 저장 현황 및 벡터 검색 동작 확인"""
    # 1. 임베딩 저장 현황
    total = await Question.count()
    embedded = await Question.find(Question.embedding != None).count()

    # 2. 벡터 검색 테스트 (SQL JOIN 개념으로 검색)
    test_query = "INNER JOIN 조건에서 NULL 값 처리와 집계 함수의 동작 방식"
    try:
        results = await search_similar_questions([test_query], chapter_id=3, top_k=3)
        search_ok = len(results) > 0
        sample = [
            {
                "score": round(r.get("score", 0), 4),
                "preview": next(
                    (a.get("payload", {}).get("text", "")[:60]
                     for a in r.get("assets", [])
                     if a.get("asset_type") == "text_block"),
                    "(텍스트 없음)"
                ),
            }
            for r in results
        ]
    except Exception as e:
        search_ok = False
        sample = [{"error": str(e)}]

    return {
        "embedding": {"total": total, "embedded": embedded, "missing": total - embedded},
        "vector_search": {"ok": search_ok, "results": sample},
    }
