from fastapi import APIRouter, HTTPException, Query
from services.question_service import QuestionService

router = APIRouter(tags=["questions"])


@router.get("/questions")
async def list_questions(
    chapter_id: int = Query(..., description="챕터 ID (1~12)"),
    count: int = Query(default=10, ge=1, le=500, description="문제 수"),
):
    svc = QuestionService()
    questions = await svc.get_random_questions(chapter_id, count)
    if not questions:
        raise HTTPException(status_code=404, detail="해당 챕터에 문제가 없습니다.")
    return questions


@router.get("/questions/{question_id}")
async def get_question(question_id: str):
    svc = QuestionService()
    question = await svc.get_question_by_id(question_id)
    if not question:
        raise HTTPException(status_code=404, detail="문제를 찾을 수 없습니다.")
    return question
