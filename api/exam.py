from beanie import PydanticObjectId
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from models.database import get_collection
from models.question import Question

router = APIRouter(prefix="/exam", tags=["exam"])

SUBJECT1_CHAPTERS = [1, 2]
SUBJECT2_CHAPTERS = list(range(3, 13))


@router.get("/questions")
async def get_exam_questions():
    """모의고사용 50문제 반환 — 과목1(ch1-2): 10문제, 과목2(ch3-12): 40문제, 정답 제거."""
    col = get_collection("questions")

    sub1 = await col.aggregate([
        {"$match": {"chapter_id": {"$in": SUBJECT1_CHAPTERS}}},
        {"$sample": {"size": 10}},
    ]).to_list(None)

    sub2 = await col.aggregate([
        {"$match": {"chapter_id": {"$in": SUBJECT2_CHAPTERS}}},
        {"$sample": {"size": 40}},
    ]).to_list(None)

    if len(sub1) < 10 or len(sub2) < 40:
        raise HTTPException(status_code=503, detail="문제 데이터가 부족합니다.")

    return [_strip_answer(q) for q in sub1 + sub2]


class GradeRequest(BaseModel):
    question_ids: list[str]


@router.post("/grade")
async def grade_exam(req: GradeRequest):
    """문제 ID 목록을 받아 정답·해설·선택지(정답 포함)를 일괄 반환."""
    results = []
    for qid in req.question_ids:
        try:
            q = await Question.get(PydanticObjectId(qid))
        except Exception:
            continue
        if not q:
            continue
        correct = next((c for c in q.choices if c.is_correct), None)
        results.append({
            "question_id": qid,
            "correct_choice": correct.choice_number if correct else None,
            "explanation": q.answer.explanation if q.answer else "",
            "choices": [c.model_dump() for c in q.choices],
        })
    return results


def _strip_answer(q: dict) -> dict:
    return {
        "id": str(q["_id"]),
        "chapter_id": q["chapter_id"],
        "question_number": q["question_number"],
        "question_type": q["question_type"],
        "assets": q.get("assets", []),
        "choices": [
            {k: v for k, v in c.items() if k != "is_correct"}
            for c in q.get("choices", [])
        ],
    }
