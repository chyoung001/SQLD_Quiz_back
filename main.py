from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from models.database import init_db
from config import settings
from api.chapters import router as chapters_router
from api.questions import router as questions_router
from api.llm import router as llm_router
from api.exam import router as exam_router
from api.admin import router as admin_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="SQLD Quiz API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chapters_router, prefix="/api")
app.include_router(questions_router, prefix="/api")
app.include_router(llm_router, prefix="/api")
app.include_router(exam_router, prefix="/api")
app.include_router(admin_router, prefix="/api")


@app.get("/")
async def health_check():
    return {"status": "ok", "version": "sequential-v2"}
