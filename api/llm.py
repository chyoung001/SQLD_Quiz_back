from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from rate_limit import llm_rate_limit
from services.llm_service import generate_practice_questions
from services.question_service import QuestionService

router = APIRouter(prefix="/llm", tags=["llm"])


class GenerateRequest(BaseModel):
    question_ids: list[str] = Field(..., min_length=1, max_length=15)
    count: int = Field(default=5, ge=1, le=5)


@router.post("/generate", dependencies=[Depends(llm_rate_limit)])
async def generate_questions(req: GenerateRequest):
    svc = QuestionService()
    questions = []
    for qid in req.question_ids:
        q = await svc.get_question_by_id(qid)
        if q:
            questions.append({
                "chapter_id": q.chapter_id,
                "assets": [a.model_dump() for a in q.assets],
                "choices": [c.model_dump() for c in q.choices],
                "answer": q.answer.model_dump() if q.answer else {},
            })

    if not questions:
        raise HTTPException(status_code=404, detail="문제를 찾을 수 없습니다.")

    try:
        generated = await generate_practice_questions(questions, count=req.count)
    except ValueError as e:
        raise HTTPException(status_code=502, detail=f"AI 응답 파싱 실패: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"문제 생성 중 오류 발생: {str(e)}")

    return generated
