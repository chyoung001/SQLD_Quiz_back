from models.question import Question
from models.database import get_collection

CHAPTER_MAP = {
    1:  "데이터 모델링의 이해",
    2:  "데이터 모델과 SQL",
    3:  "SQL 기본",
    4:  "SQL 활용",
    5:  "관리 구문",
    6:  "SQL 수행 구조",
    7:  "SQL 분석 도구",
    8:  "인덱스 튜닝",
    9:  "조인 튜닝",
    10: "SQL 옵티마이저",
    11: "고급 SQL 튜닝",
    12: "Lock과 트랜잭션 동시성 제어",
}


class QuestionService:

    async def get_chapters(self) -> list[dict]:
        pipeline = [
            {"$group": {"_id": "$chapter_id", "count": {"$sum": 1}}},
            {"$sort": {"_id": 1}},
        ]
        results = await Question.aggregate(pipeline).to_list()
        return [
            {
                "chapter_id": r["_id"],
                "name": CHAPTER_MAP.get(r["_id"], f"챕터 {r['_id']}"),
                "count": r["count"],
            }
            for r in results
        ]

    async def get_random_questions(
        self, chapter_id: int, count: int = 10
    ) -> list[dict]:
        col = get_collection("questions")
        pipeline = [
            {"$match": {"chapter_id": chapter_id}},
            {"$sample": {"size": count}},
        ]
        questions = await col.aggregate(pipeline).to_list(None)
        return [_strip_answer(q) for q in questions]

    async def get_question_by_id(self, question_id: str) -> Question | None:
        return await Question.get(question_id)


def _strip_answer(q: dict) -> dict:
    """List 응답용: 정답/해설 정보를 제거하여 풀이 화면이 정답을 미리 알 수 없도록 함."""
    return {
        "id": str(q["_id"]),
        "chapter_id": q["chapter_id"],
        "question_number": q["question_number"],
        "book_section": q.get("book_section", ""),
        "question_type": q["question_type"],
        "assets": q.get("assets", []),
        "choices": [
            {k: v for k, v in c.items() if k != "is_correct"}
            for c in q.get("choices", [])
        ],
    }
