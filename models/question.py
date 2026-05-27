from beanie import Document, Indexed
from pydantic import BaseModel
from typing import Any


class Asset(BaseModel):
    asset_type: str
    payload: Any


class Choice(BaseModel):
    choice_number: int
    choice_kind: str
    choice_text: str
    payload: Any = None
    is_correct: bool


class Answer(BaseModel):
    explanation: str


class Question(Document):
    chapter_id: int
    question_number: int
    book_section: str
    book_question_number: int | None = None
    question_type: str
    assets: list[Asset] = []
    choices: list[Choice] = []
    answer: Answer
    embedding: list[float] | None = None  # text-embedding-004, 768차원

    class Settings:
        name = "questions"
        indexes = [
            "chapter_id",
            "question_type",
            [("chapter_id", 1), ("question_number", 1)],
        ]
