import asyncio

import httpx

from config import settings
from models.database import get_collection
from models.question import Question

# SDK embed_content가 2.x에서 동작하지 않아 REST API 직접 호출
_EMBED_MODEL = "gemini-embedding-001"  # 한국어 포함 다국어 지원, 3072차원
_EMBED_DIM = 3072
_ATLAS_INDEX = "embedding_index"
_EMBED_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{_EMBED_MODEL}:embedContent"
)


async def embed_text(text: str) -> list[float]:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            _EMBED_URL,
            params={"key": settings.gemini_api_key},
            json={
                "model": f"models/{_EMBED_MODEL}",
                "content": {"parts": [{"text": text}]},
            },
        )
        resp.raise_for_status()
        return resp.json()["embedding"]["values"]


def _question_to_embed_text(q: Question) -> str:
    """문제 전체 텍스트 추출 (임베딩용 — 풍부한 의미 표현)"""
    parts = []
    for asset in q.assets:
        p = asset.payload or {}
        t = asset.asset_type
        if t == "text_block":
            parts.append(p.get("text", "").strip())
        elif t in ("sql_query", "sql_ddl", "sql_dml"):
            parts.append(p.get("code", "").strip())
        elif t in ("data_table", "result_table"):
            parts.append(p.get("text") or p.get("markdown", ""))
    for c in q.choices:
        parts.append(f"{c.choice_number}. {c.choice_text.strip()}")
    if q.answer and q.answer.explanation:
        parts.append(q.answer.explanation.strip())
    return "\n".join(p for p in parts if p)


async def vectorize_all_questions(force: bool = False) -> dict:
    """
    DB의 모든 문제를 임베딩하여 embedding 필드에 저장.
    force=False이면 이미 embedding이 있는 문제는 건너뜀.
    """
    questions = await Question.find_all().to_list()
    success = skipped = failed = 0

    for q in questions:
        if not force and q.embedding:
            skipped += 1
            continue
        try:
            text = _question_to_embed_text(q)
            embedding = await embed_text(text)
            await get_collection("questions").update_one(
                {"_id": q.id},
                {"$set": {"embedding": embedding}},
            )
            success += 1
            await asyncio.sleep(0.15)  # Gemini embedding API 레이트 리밋 방지
        except Exception as e:
            failed += 1
            print(f"[RAG] 임베딩 실패 ({q.id}): {e}")

    return {"success": success, "skipped": skipped, "failed": failed, "total": len(questions)}


async def search_similar_questions(
    query_texts: list[str],
    chapter_id: int,
    top_k: int = 3,
) -> list[dict]:
    """
    틀린 문제 텍스트들의 평균 벡터로 Atlas Vector Search 수행.
    같은 chapter_id 내에서 top_k개의 유사 기출 반환.
    임베딩 미구축 시 빈 리스트 반환.
    """
    if not query_texts:
        return []

    # 최대 3개 질의 텍스트만 임베딩 (비용 제한)
    try:
        embeddings = []
        for text in query_texts[:3]:
            emb = await embed_text(text)
            embeddings.append(emb)
    except Exception as e:
        print(f"[RAG] 쿼리 임베딩 실패: {e}")
        return []

    # 평균 벡터 계산
    avg_embedding = [
        sum(e[i] for e in embeddings) / len(embeddings)
        for i in range(_EMBED_DIM)
    ]

    collection = get_collection("questions")
    pipeline = [
        {
            "$vectorSearch": {
                "index": _ATLAS_INDEX,
                "path": "embedding",
                "queryVector": avg_embedding,
                "numCandidates": 60,
                "limit": top_k + 3,
                "filter": {"chapter_id": {"$eq": chapter_id}},
            }
        },
        {
            "$project": {
                "_id": 1,
                "chapter_id": 1,
                "assets": 1,
                "choices": 1,
                "answer": 1,
                "score": {"$meta": "vectorSearchScore"},
            }
        },
    ]

    try:
        results = await collection.aggregate(pipeline).to_list(length=top_k + 3)
        return results[:top_k]
    except Exception as e:
        print(f"[RAG] Vector Search 실패: {e}")
        return []


def format_rag_context(similar_questions: list[dict]) -> str:
    """유사 기출을 Gemini 프롬프트에 주입할 텍스트로 변환"""
    if not similar_questions:
        return ""

    lines = ["# 유사 기출 문제 (같은 개념 영역 — 중복 출제 금지, 맥락 참고용)"]
    for i, q in enumerate(similar_questions, 1):
        # 문제 텍스트 추출
        q_text = ""
        for asset in q.get("assets", []):
            p = asset.get("payload") or {}
            t = asset.get("asset_type", "")
            if t == "text_block":
                q_text = p.get("text", "").strip()
                break

        # 정답 선택지 텍스트
        choices = q.get("choices", [])
        correct_text = ""
        for c in choices:
            if c.get("is_correct"):
                correct_text = c.get("choice_text", "").strip()
                break

        explanation = (q.get("answer") or {}).get("explanation", "").strip()
        # 해설 앞 100자만 (토큰 절약)
        explanation_short = explanation[:120] + "…" if len(explanation) > 120 else explanation

        lines.append(
            f"\n[기출 {i}]\n"
            f"문제: {q_text}\n"
            f"정답: {correct_text}\n"
            f"해설 요약: {explanation_short}"
        )

    return "\n".join(lines)
