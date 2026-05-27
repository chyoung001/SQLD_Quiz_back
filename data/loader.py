"""
실행: python -m data.loader
SQLD_data/json/ 의 JSON 파일을 읽어 MongoDB questions 컬렉션에 적재
"""
import asyncio
import json
import sys
from pathlib import Path

# backend/ 기준으로 프로젝트 루트의 SQLD_data/json 경로
BACKEND_DIR = Path(__file__).parent.parent
DATA_DIR = BACKEND_DIR.parent / "SQLD_data" / "json"

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

# JSON 파일명 → chapter_id 매핑 (파일명 앞 숫자 기준)
FILE_CHAPTER_MAP = {
    "1. 데이터 모델링의 이해.json":       1,
    "2. 데이터 모델과 SQL.json":           2,
    "3. SQL 기본.json":                    3,
    "4. SQL활용.json":                     4,
    "5. 관리구문.json":                    5,
    "6. SQL 수행 구조.json":               6,
    "7. SQL 분석 도구.json":               7,
    "8. 인덱스 튜닝.json":                 8,
    "9. 조인 튜닝.json":                   9,
    "10. SQL 옵티마이저.json":             10,
    "11. 고급 SQL 튜닝.json":              11,
    "12. Lock과 트랜잭션 동시성 제어.json": 12,
}


async def load_all(force: bool = False):
    # models가 backend/ 기준이므로 sys.path 보정
    sys.path.insert(0, str(BACKEND_DIR))

    from models.database import init_db
    from models.question import Question

    await init_db()

    existing = await Question.count()
    if existing > 0 and not force:
        print(f"이미 {existing}건 존재. 스킵. (강제 재적재: --force)")
        return

    if force and existing > 0:
        await Question.delete_all()
        print(f"기존 {existing}건 삭제 후 재적재합니다.")

    total = 0
    for filename, chapter_id in sorted(FILE_CHAPTER_MAP.items(), key=lambda x: x[1]):
        filepath = DATA_DIR / filename
        if not filepath.exists():
            print(f"  [경고] 파일 없음: {filepath}")
            continue

        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        questions = []
        for q in data["questions"]:
            doc = Question(
                chapter_id=chapter_id,
                question_number=q["question_number"],
                book_section=q.get("book_section", ""),
                book_question_number=q.get("book_question_number"),
                question_type=q["question_type"],
                assets=q.get("assets", []),
                choices=q.get("choices", []),
                answer=q["answer"],
            )
            questions.append(doc)

        await Question.insert_many(questions)
        total += len(questions)
        print(f"  ch{chapter_id:2d}  {CHAPTER_MAP[chapter_id]:<28}  {len(questions)}건")

    print(f"\n완료: 총 {total}건 적재")


if __name__ == "__main__":
    force = "--force" in sys.argv
    asyncio.run(load_all(force=force))
