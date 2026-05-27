# RAG 파이프라인 설계 문서

SQLD Quiz 백엔드의 AI 변형 문제 생성에 사용되는 RAG(Retrieval-Augmented Generation) 파이프라인 상세 설명.

---

## 전체 흐름

```
사용자가 틀린 문제 N개 (최대 15개)
         │
         ▼
  ┌──────────────────────────────┐
  │  Step 0. 챕터 결정           │
  │  Counter → 최빈 chapter_id   │
  └──────────────┬───────────────┘
                 │
                 ▼
  ┌──────────────────────────────┐
  │  Step 1. RAG 쿼리 풀 구성   │
  │  N ≤ 10 → 전부 사용          │
  │  N > 10 → 무작위 10개 샘플링 │
  └──────────────┬───────────────┘
                 │
                 ▼
  ┌──────────────────────────────┐
  │  Step 2. 임베딩 생성         │
  │  선택된 문제 각각 → Gemini   │
  │  Embedding 001 (3072차원)    │
  └──────────────┬───────────────┘
                 │
                 ▼
  ┌──────────────────────────────┐
  │  Step 3. 평균 벡터 계산      │
  │  N개 임베딩 → 위치별 평균    │
  │  → 대표 벡터 1개             │
  └──────────────┬───────────────┘
                 │
                 ▼
  ┌──────────────────────────────┐
  │  Step 4. Atlas Vector Search │
  │  같은 chapter_id 내에서      │
  │  유사도 top-5 기출 추출      │
  └──────────────┬───────────────┘
                 │
                 ▼
  ┌──────────────────────────────┐
  │  Step 5. Gemini 문제 생성    │
  │  틀린 문제 전체 +            │
  │  유사 기출 5개 → 프롬프트    │
  │  → 변형 문제 5개 생성        │
  └──────────────┬───────────────┘
                 │
                 ▼
  ┌──────────────────────────────┐
  │  Step 6. Claude Opus 검증    │
  │  생성 문제 전체 일괄 검증    │
  │  valid=false → 수정 또는 제외│
  └──────────────────────────────┘
```

---

## 각 단계 상세

### Step 0. 챕터 결정

- 틀린 문제들의 `chapter_id` 중 **가장 많이 등장한 챕터**를 채택
- 여러 챕터에 걸쳐 틀렸어도 **단일 챕터**로 통일해서 생성 (챕터 혼합 생성 미지원)

```python
chapter_id = Counter(chapter_ids).most_common(1)[0][0]
```

---

### Step 1. RAG 쿼리 풀 구성

| 틀린 문제 수 | 동작 |
|-------------|------|
| 10개 이하 | 전부 사용 |
| 11~15개 | **무작위 10개 샘플링** |

- 무작위 샘플링을 사용하는 이유: 매번 다른 조합으로 다양한 RAG 결과 유도
- 관련 코드: [`services/llm_service.py`](services/llm_service.py)

```python
rag_pool = wrong_questions if len(wrong_questions) <= 10 else random.sample(wrong_questions, 10)
```

---

### Step 2. 임베딩 생성

- 모델: **Gemini Embedding 001** (3072차원, 다국어 지원)
- 각 문제에서 임베딩 텍스트 추출 규칙:

| asset_type | 추출 내용 |
|-----------|----------|
| `text_block` | 문제 본문 텍스트 |
| `sql_query` / `sql_ddl` / `sql_dml` | SQL 코드 |
| `data_table` / `result_table` | 테이블 텍스트 |
| 선택지 전체 | `1. 선택지내용` 형식으로 추가 |
| 해설 | 전체 텍스트 추가 |

- 관련 코드: [`services/rag_service.py`](services/rag_service.py) `_question_to_embed_text()`

---

### Step 3. 평균 벡터 계산

- N개의 3072차원 벡터를 **위치별(dimension별) 평균**으로 합산 → 대표 벡터 1개 생성
- Atlas Vector Search는 단일 벡터 1개만 입력받으므로, 여러 문제의 공통 의미 방향을 1개로 압축

```
문제 1 임베딩: [0.12, 0.85, 0.33, ...]
문제 2 임베딩: [0.44, 0.21, 0.91, ...]
문제 3 임베딩: [0.78, 0.55, 0.10, ...]
                 ↓
평균 벡터:      [0.44, 0.53, 0.44, ...]  ← 이걸로 검색
```

---

### Step 4. Atlas Vector Search

- 인덱스명: `embedding_index` (MongoDB Atlas Vector Search)
- 검색 범위: **같은 `chapter_id`** 내로 필터링 (다른 챕터 기출은 후보 제외)
- 후보 수: `numCandidates: 60` → 상위 `top_k + 3 = 8`개 추출 → 최종 **5개 반환**
- 유사도 기준: **코사인 유사도** (cosine)

```python
"$vectorSearch": {
    "index": "embedding_index",
    "queryVector": avg_embedding,
    "numCandidates": 60,
    "limit": 8,          # top_k(5) + 3 여유분
    "filter": {"chapter_id": {"$eq": chapter_id}},
}
```

---

### Step 5. Gemini 프롬프트 구성 및 생성

Gemini에게 전달되는 프롬프트 구성:

```
[few-shot 예시]          ← 챕터별 출제 수준 예시 1개 (modeling / sql / advanced)
[유사 기출 5개]          ← RAG로 추출한 기출 (맥락 참고용, 중복 출제 금지)
[틀린 문제 전체]         ← wrong_questions 전부 (최대 15개)
[출제 지침]              ← 포맷, 오답 조건, 해설 조건 등
```

- 생성 모델: **Gemini 2.5 Flash**
- `response_schema`로 JSON 구조 강제 출력
- 최대 2회 재시도

---

### Step 6. Claude Opus 검증

- 모델: **Claude Opus 4.7** (prompt caching 적용)
- 생성된 문제 전체를 **1회 API 호출**로 일괄 검증
- 검증 기준:
  1. 정답이 명확히 하나인가
  2. 오답이 그럴듯하지만 명확히 틀렸는가
  3. SQL/DB 개념이 정확한가
  4. 자연스러운 한국어인가
  5. SQLD 시험 수준에 적절한가

| 검증 결과 | 처리 |
|----------|------|
| `valid: true` | 원본 그대로 사용 |
| `valid: false` + `corrected` 있음 | 수정된 버전으로 교체 |
| `valid: false` + `corrected: null` | 해당 문제 제외 |

- API 장애 시 fallback: 모든 문제 `valid: true / score: 5`로 처리 후 통과

---

## 제약 및 한계

| 항목 | 현재 값 | 비고 |
|------|--------|------|
| 최대 입력 문제 수 | **15개** | `api/llm.py` `max_length` |
| RAG 임베딩 쿼리 수 | **최대 10개** | 비용 제한, 초과 시 무작위 샘플링 |
| 유사 기출 추출 수 | **5개** | `top_k=5` |
| 생성 문제 수 | **1~5개** | `count` 파라미터, 기본값 5 |
| 챕터 범위 | **단일 챕터** | 최빈 chapter_id 1개로 고정 |
| Gemini 재시도 | **최대 2회** | 실패 시 502 반환 |

---

## 관련 파일

| 파일 | 역할 |
|------|------|
| [`api/llm.py`](api/llm.py) | API 엔드포인트, 요청 유효성 검사 |
| [`services/llm_service.py`](services/llm_service.py) | 전체 파이프라인 오케스트레이션, Gemini 생성, Claude 검증 |
| [`services/rag_service.py`](services/rag_service.py) | 임베딩 생성, 평균 벡터 계산, Atlas Vector Search |
| [`models/question.py`](models/question.py) | Question Document 스키마 |
