import json
import random
import re
import uuid
from collections import Counter

import anthropic
from google import genai
from google.genai import types as genai_types

from config import settings
from services.rag_service import search_similar_questions, format_rag_context

# ── 클라이언트 싱글톤 ────────────────────────────────────────────────────────

_gemini_client: genai.Client | None = None
_claude_client: anthropic.AsyncAnthropic | None = None


def _get_gemini() -> genai.Client:
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = genai.Client(api_key=settings.gemini_api_key)
    return _gemini_client


def _get_claude() -> anthropic.AsyncAnthropic:
    global _claude_client
    if _claude_client is None:
        _claude_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _claude_client


# ── asset → 텍스트 변환 ──────────────────────────────────────────────────────

def _data_table_to_text(payload: dict) -> str:
    name = payload.get("name", "")
    columns = payload.get("columns", [])
    rows = payload.get("rows", [])
    lines = []
    if name:
        lines.append(f"[테이블: {name}]")
    lines.append(" | ".join(columns))
    lines.append(" | ".join(["---"] * len(columns)))
    for row in rows:
        lines.append(" | ".join(str(row.get(c, "")) for c in columns))
    return "\n".join(lines)


def _asset_to_text(asset: dict, indent: int = 0) -> str:
    prefix = "  " * indent
    t = asset.get("asset_type", "")
    p = asset.get("payload") or {}

    if t == "text_block":
        return prefix + p.get("text", "").strip()
    if t in ("sql_query", "sql_ddl", "sql_dml"):
        label = p.get("label", t.upper())
        return f"{prefix}[{label}]\n{p.get('code', '').strip()}"
    if t in ("data_table", "result_table"):
        text = p.get("text") or p.get("markdown", "")
        return prefix + (text.strip() if text else _data_table_to_text(p))
    if t == "erd":
        return f"{prefix}[ERD]\n{p.get('code', '').strip()}"
    if t == "labeled_group":
        parts = []
        if p.get("label"):
            parts.append(f"{prefix}[{p['label']}]")
        for item in p.get("items", []):
            converted = _asset_to_text(item, indent + 1)
            if converted.strip():
                parts.append(converted)
        return "\n".join(parts)
    if t == "list_items":
        return "\n".join(f"{prefix}{i+1}. {item}" for i, item in enumerate(p.get("items", [])))
    if t == "entity_schema":
        lines = [f"{prefix}[엔터티: {p.get('name', '')}]"]
        lines += [f"{prefix}  - {a}" for a in p.get("attributes", [])]
        return "\n".join(lines)
    return f"{prefix}[{t}] {json.dumps(p, ensure_ascii=False)}"


def _choice_to_text(c: dict) -> str:
    marker = "✓" if c.get("is_correct") else " "
    kind = c.get("choice_kind", "text")
    num = c.get("choice_number", "")
    text = c.get("choice_text", "").strip()
    if kind in ("sql_query", "sql_ddl", "sql_dml", "sql_fragment"):
        return f"  {num}. [{marker}]\n{text}"
    if kind == "result_table":
        return f"  {num}. [{marker}] (결과 테이블)\n{text}"
    return f"  {num}. [{marker}] {text}"


def _question_to_prompt_text(q: dict) -> str:
    parts = [_asset_to_text(a) for a in q.get("assets", [])]
    parts = [p for p in parts if p.strip()]
    parts += [_choice_to_text(c) for c in q.get("choices", [])]
    explanation = (q.get("answer") or {}).get("explanation", "")
    if explanation:
        parts.append(f"\n[해설] {explanation}")
    return "\n".join(parts)


# ── JSON 파싱 ────────────────────────────────────────────────────────────────

def _extract_json(raw: str) -> list:
    text = raw.strip()
    code_block = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if code_block:
        text = code_block.group(1).strip()
    array_match = re.search(r"\[[\s\S]*\]", text)
    if array_match:
        text = array_match.group(0)
    return json.loads(text)


# ── Few-shot 예시 은행 ───────────────────────────────────────────────────────
# ch 1-2: 데이터 모델링, ch 3-5: SQL 기본/활용/관리구문, ch 6-12: 고급

_FEW_SHOT_BANK: dict[str, dict] = {
    "modeling": {
        "question_text": (
            "다음 중 데이터 모델링의 3단계(개념적 → 논리적 → 물리적) 진행에 대한 설명으로 "
            "가장 적절하지 않은 것은?"
        ),
        "question_type": "worst_choice",
        "chapter_id": 1,
        "choices": [
            {"choice_number": 1, "choice_kind": "text",
             "choice_text": "개념적 모델링은 추상화 수준이 가장 높으며 업무 중심의 포괄적인 수준에서 핵심 엔터티와 관계를 도출한다."},
            {"choice_number": 2, "choice_kind": "text",
             "choice_text": "논리적 모델링은 특정 DBMS에 종속되지 않으며 정규화를 통해 데이터 중복을 최소화한다."},
            {"choice_number": 3, "choice_kind": "text",
             "choice_text": "물리적 모델링은 특정 DBMS의 특성과 성능을 고려하여 테이블, 컬럼, 인덱스 등을 구체적으로 설계한다."},
            {"choice_number": 4, "choice_kind": "text",
             "choice_text": "개념적 모델링 단계에서 기본 키(PK)와 외래 키(FK)를 반드시 정의해야 데이터 무결성을 보장할 수 있다."},
        ],
        "correct_choice": 4,
        "explanation": (
            "정답 ④: PK·FK 정의는 논리적 모델링 단계의 작업입니다. 개념적 모델링은 핵심 엔터티와 관계만 파악하는 추상적 단계로, 구체적인 키 정의는 수행하지 않습니다.\n"
            "오답 ①: 개념적 모델링은 가장 추상적이고 업무 중심적 — 옳습니다.\n"
            "오답 ②: 논리적 모델링은 DBMS 독립적이며 정규화 작업이 이루어집니다 — 옳습니다.\n"
            "오답 ③: 물리적 모델링에서 비로소 DBMS 특성(스토리지, 파티셔닝 등)을 반영합니다 — 옳습니다."
        ),
    },
    "sql": {
        "question_text": (
            "다음 SQL 실행 결과로 출력되는 행 수로 올바른 것은?\n\n"
            "[사원] 테이블 (5행): EMP_ID(1~5), DEPT_ID(10, 10, 20, 20, NULL)\n"
            "[부서] 테이블 (3행): DEPT_ID(10, 20, 30)\n\n"
            "SELECT E.EMP_ID, D.DEPT_NAME\n"
            "FROM 사원 E, 부서 D\n"
            "WHERE E.DEPT_ID = D.DEPT_ID;"
        ),
        "question_type": "best_choice",
        "chapter_id": 3,
        "choices": [
            {"choice_number": 1, "choice_kind": "text", "choice_text": "3행"},
            {"choice_number": 2, "choice_kind": "text", "choice_text": "4행"},
            {"choice_number": 3, "choice_kind": "text", "choice_text": "5행"},
            {"choice_number": 4, "choice_kind": "text", "choice_text": "6행"},
        ],
        "correct_choice": 2,
        "explanation": (
            "정답 ②: INNER JOIN은 조인 조건을 만족하는 행만 반환합니다. "
            "DEPT_ID가 NULL인 사원(1명)은 NULL = 어떤 값도 성립하지 않아 제외됩니다. "
            "DEPT_ID=30 부서는 해당 사원이 없으므로 제외됩니다. "
            "결과: DEPT_ID=10 사원 2명 + DEPT_ID=20 사원 2명 = 4행.\n"
            "오답 ①(3행): 부서 수를 기준으로 오해한 경우. INNER JOIN은 매칭되는 모든 조합을 반환합니다.\n"
            "오답 ③(5행): DEPT_ID가 NULL인 사원도 포함된다고 오해한 경우. NULL은 등치 비교에서 항상 UNKNOWN을 반환합니다.\n"
            "오답 ④(6행): CROSS JOIN(5×3=15행)과 혼동한 경우."
        ),
    },
    "advanced": {
        "question_text": (
            "다음 SQL에 대한 설명으로 가장 적절하지 않은 것은?\n\n"
            "SELECT /*+ INDEX(O ORD_IDX1) */ O.ORDER_ID, C.CUST_NAME\n"
            "FROM 주문 O, 고객 C\n"
            "WHERE O.CUST_ID = C.CUST_ID\n"
            "  AND O.ORDER_DATE >= '2024-01-01'\n"
            "  AND C.REGION = '서울';"
        ),
        "question_type": "worst_choice",
        "chapter_id": 8,
        "choices": [
            {"choice_number": 1, "choice_kind": "text",
             "choice_text": "INDEX(O ORD_IDX1) 힌트는 옵티마이저가 주문 테이블에 ORD_IDX1 인덱스를 사용하도록 유도한다."},
            {"choice_number": 2, "choice_kind": "text",
             "choice_text": "ORDER_DATE 범위 조건(>=)이 효율적으로 동작하려면 ORD_IDX1의 선두 컬럼에 ORDER_DATE가 포함되어야 한다."},
            {"choice_number": 3, "choice_kind": "text",
             "choice_text": "힌트를 사용하면 옵티마이저의 판단보다 반드시 성능이 향상되므로 운영 환경에서 적극적으로 적용해야 한다."},
            {"choice_number": 4, "choice_kind": "text",
             "choice_text": "고객 테이블의 REGION = '서울' 조건 선택도가 낮다면 고객 테이블을 드라이빙으로 하는 NL 조인이 유리할 수 있다."},
        ],
        "correct_choice": 3,
        "explanation": (
            "정답 ③: 힌트는 옵티마이저에게 특정 실행 계획을 '제안'하지만, 데이터 분포·통계가 변경되면 오히려 성능이 저하될 수 있습니다. "
            "힌트 남용은 유지보수를 어렵게 하므로 옵티마이저가 잘못된 계획을 선택할 때만 제한적으로 사용해야 합니다.\n"
            "오답 ①: INDEX 힌트의 기본 동작을 올바르게 설명합니다 — 옳습니다.\n"
            "오답 ②: 범위 스캔(>=)이 인덱스를 타려면 해당 컬럼이 선두 컬럼이어야 합니다 — 옳습니다.\n"
            "오답 ④: 선택도가 낮은(결과 행 수가 적은) 테이블을 드라이빙으로 하면 NL 조인 내부 루프 횟수가 줄어 유리합니다 — 옳습니다."
        ),
    },
}


def _get_few_shot_example(chapter_id: int) -> str:
    if chapter_id <= 2:
        example = _FEW_SHOT_BANK["modeling"]
    elif chapter_id <= 5:
        example = _FEW_SHOT_BANK["sql"]
    else:
        example = _FEW_SHOT_BANK["advanced"]
    return json.dumps(example, ensure_ascii=False, indent=2)


# ── Gemini response_schema 정의 ──────────────────────────────────────────────

def _build_question_schema() -> genai_types.Schema:
    choice_schema = genai_types.Schema(
        type=genai_types.Type.OBJECT,
        properties={
            "choice_number": genai_types.Schema(type=genai_types.Type.INTEGER),
            "choice_kind": genai_types.Schema(type=genai_types.Type.STRING),
            "choice_text": genai_types.Schema(type=genai_types.Type.STRING),
        },
        required=["choice_number", "choice_kind", "choice_text"],
    )
    question_schema = genai_types.Schema(
        type=genai_types.Type.OBJECT,
        properties={
            "question_text": genai_types.Schema(type=genai_types.Type.STRING),
            "question_type": genai_types.Schema(type=genai_types.Type.STRING),
            "chapter_id": genai_types.Schema(type=genai_types.Type.INTEGER),
            "choices": genai_types.Schema(
                type=genai_types.Type.ARRAY,
                items=choice_schema,
            ),
            "correct_choice": genai_types.Schema(type=genai_types.Type.INTEGER),
            "explanation": genai_types.Schema(type=genai_types.Type.STRING),
        },
        required=["question_text", "question_type", "chapter_id", "choices", "correct_choice", "explanation"],
    )
    return genai_types.Schema(
        type=genai_types.Type.ARRAY,
        items=question_schema,
    )


# ── Step 1: Gemini로 문제 생성 ───────────────────────────────────────────────

async def _generate_with_gemini(
    formatted: str,
    count: int,
    chapter_id: int,
    rag_context: str = "",
) -> list[dict]:
    few_shot = _get_few_shot_example(chapter_id)
    rag_section = f"\n{rag_context}\n" if rag_context else ""
    prompt = f"""# 역할
당신은 SQLD(SQL 개발자) 자격증 출제 경험이 풍부한 데이터베이스 전문가입니다.

# 목표
사용자가 틀린 문제에서 드러난 약점 개념을 보강할 변형 연습 문제 {count}개를 출제합니다.

# 참고 예시 (이 수준의 품질로 출제하세요)
{few_shot}
{rag_section}
# 입력: 사용자가 틀린 문제
{formatted}

# 출제 지침
1. **포맷**: 4지 선다형, `question_type`은 "best_choice"("옳은 것은?") 또는 "worst_choice"("옳지 않은 것은?" / "가장 거리가 먼 것은?")
2. **매력적 오답**: 개념을 부분적으로 오해한 수험생이 고르기 쉬운 논리적 함정을 포함하세요. 단순 오타·말장난 금지.
3. **새 시나리오**: 참고 예시·유사 기출·원본 문제의 테이블명·예시를 그대로 사용하지 마세요.
   - 데이터 모델링(chapter_id 1~2): ERD/엔터티/관계 중심
   - SQL(chapter_id 3+): 쇼핑몰·병원·인사·재고 등 현실 비즈니스 테이블
4. **해설**: 정답 근거 + 각 오답이 왜 틀렸는지 구체적으로 작성하세요.
5. **선택지 타입**: SQL 코드 포함 시 `choice_kind`를 "sql_query"로, 일반 텍스트는 "text"로 명확히 구분하세요.
6. **chapter_id**: 반드시 {chapter_id}로 설정하세요."""

    client = _get_gemini()
    response = await client.aio.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=_build_question_schema(),
        ),
    )
    return _extract_json(response.text)


# ── Step 2: Claude Opus로 일괄 검증 ─────────────────────────────────────────

async def _validate_batch_with_claude(questions: list[dict]) -> list[dict]:
    """
    Claude Opus-4-7이 생성 문제 전체를 한 번의 API 호출로 검토합니다.
    반환: [{ "valid": bool, "score": int(1-10), "feedback": str, "corrected": dict | null, "issues": [str] }, ...]
    API 장애 시 모든 문제를 valid:true / score:5로 fallback합니다.
    """
    fallback = [
        {"valid": True, "score": 5, "feedback": "검증 생략됨", "issues": [], "corrected": None}
        for _ in range(len(questions))
    ]

    q_text = json.dumps(questions, ensure_ascii=False, indent=2)
    prompt = f"""다음 SQLD 시험 문제들을 전문가 입장에서 각각 검토하세요.

{q_text}

각 문제에 대한 검증 기준:
1. 정답(correct_choice)이 명확히 하나인가?
2. 오답 보기들이 그럴듯하지만 명확히 틀렸는가?
3. SQL/데이터베이스 개념이 정확한가?
4. 문제 본문과 선택지가 자연스러운 한국어인가?
5. SQLD 시험 수준에 적절한가?

# 평가 출력
각 문제에 대해 다음을 반환하세요:
- `valid`: 문제가 그대로 사용 가능하면 true, 결함이 있으면 false
- `score`: 종합 품질 점수 (1~10 정수). 8 이상은 우수, 5~7은 보통, 4 이하는 결함 있음
- `feedback`: 품질 평가를 한 줄로 (예: "개념은 정확하나 오답 1번이 너무 명백함")
- `issues`: 문제점 목록 (없으면 빈 배열)
- `corrected`: valid가 false일 때 수정된 문제 객체, 수정 불가능하면 null

반드시 아래 JSON 배열 형식만 반환하세요 (문제 수: {len(questions)}개):
[
  {{"valid": true, "score": 9, "feedback": "정답 명확하고 오답도 매력적임", "issues": [], "corrected": null}},
  {{"valid": false, "score": 4, "feedback": "정답이 두 개로 해석 가능", "issues": ["choice 2와 3 모두 정답 가능"], "corrected": {{...수정된 문제...}}}}
]"""

    try:
        client = _get_claude()
        message = await client.messages.create(
            model="claude-opus-4-7",
            max_tokens=4096,
            system=[{
                "type": "text",
                "text": "당신은 SQLD 자격증 시험 문제의 품질을 검증하는 전문가입니다. 반드시 JSON 배열만 반환하세요.",
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": prompt}],
        )

        raw = message.content[0].text
        result = _extract_json(raw)
        if not isinstance(result, list):
            result = [result]
        while len(result) < len(questions):
            result.append({"valid": True, "score": 5, "feedback": "검증 누락", "issues": [], "corrected": None})
        return result[:len(questions)]

    except anthropic.APIStatusError as e:
        # 429 Rate limit, 529 Overload 등 → 검증 생략하고 원본 사용
        print(f"[Claude] APIStatusError ({e.status_code}): {e.message} — 검증 생략")
        return fallback
    except anthropic.APIConnectionError as e:
        print(f"[Claude] 연결 오류: {e} — 검증 생략")
        return fallback
    except Exception as e:
        print(f"[Claude] 예상치 못한 오류: {e} — 검증 생략")
        return fallback


# ── 메인 생성 함수 ───────────────────────────────────────────────────────────

async def generate_practice_questions(wrong_questions: list[dict], count: int = 5) -> list[dict]:
    if not wrong_questions:
        return []

    chapter_ids = [q.get("chapter_id", 1) for q in wrong_questions]
    chapter_id = Counter(chapter_ids).most_common(1)[0][0]

    formatted = "\n\n".join(
        f"[문제 {i+1}]\n{_question_to_prompt_text(q)}"
        for i, q in enumerate(wrong_questions)
    )

    # RAG: 틀린 문제와 유사한 기출 검색 → 프롬프트 컨텍스트로 주입
    # wrong_questions는 dict이므로 이미 dict를 처리하는 _question_to_prompt_text 재사용
    # 틀린 문제가 10개 초과면 무작위로 10개 샘플링 (매번 다른 조합으로 다양한 RAG 결과 유도)
    rag_pool = wrong_questions if len(wrong_questions) <= 10 else random.sample(wrong_questions, 10)
    query_texts = [_question_to_prompt_text(q) for q in rag_pool]
    print(f"[RAG] 벡터 검색 시작 — chapter_id={chapter_id}, 쿼리 {len(query_texts)}개")
    similar = await search_similar_questions(query_texts, chapter_id, top_k=5)
    rag_context = format_rag_context(similar)
    if rag_context:
        scores = [round(s.get("score", 0), 4) for s in similar]
        print(f"[RAG] 유사 기출 {len(similar)}개 주입 — 유사도 점수: {scores}")
    else:
        print("[RAG] 유사 기출 없음 — RAG 없이 생성 진행")

    # Step 1: Gemini로 문제 생성 (최대 2회 시도)
    last_error: Exception | None = None
    generated_raw: list = []
    for attempt in range(2):
        try:
            generated_raw = await _generate_with_gemini(formatted, count, chapter_id, rag_context)
            break
        except Exception as e:
            last_error = e
            if attempt == 1:
                raise ValueError(f"Gemini 생성 실패 (2회 시도): {last_error}")

    # Step 2: Claude Opus로 일괄 검증 + 수정 (1회 API 호출)
    items = generated_raw[:count]
    validations = await _validate_batch_with_claude(items)

    validated: list[dict] = []
    for item, validation in zip(items, validations):
        if validation.get("valid"):
            final_item = item
        elif validation.get("corrected"):
            final_item = validation["corrected"]
        else:
            continue  # 수정 불가 → 제외

        qid = f"generated_{uuid.uuid4().hex[:12]}"
        validated.append({
            "id": qid,
            "chapter_id": final_item.get("chapter_id", chapter_id),
            "question_number": f"AI-{len(validated) + 1}",
            "question_type": final_item.get("question_type", "best_choice"),
            "assets": [
                {"asset_type": "text_block", "payload": {"text": final_item["question_text"]}}
            ],
            "choices": [
                {
                    "choice_number": c["choice_number"],
                    "choice_kind": c.get("choice_kind", "text"),
                    "choice_text": c["choice_text"],
                    "payload": None,
                }
                for c in final_item["choices"]
            ],
            "correct_choice": final_item["correct_choice"],
            "explanation": final_item.get("explanation", ""),
            "validated": validation.get("valid", False),
            "quality_score": validation.get("score"),
            "quality_feedback": validation.get("feedback", ""),
        })

    return validated
