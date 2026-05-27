from fastapi import APIRouter
from services.question_service import QuestionService

router = APIRouter(tags=["chapters"])


@router.get("/chapters")
async def list_chapters():
    svc = QuestionService()
    return await svc.get_chapters()
