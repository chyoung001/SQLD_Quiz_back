# SQLD Quiz — Backend

SQLD(SQL 개발자) 자격증 시험 대비 플랫폼의 백엔드 API 서버.
FastAPI + MongoDB Atlas + Gemini + Claude 기반의 RAG·이중 LLM 검증 파이프라인을 제공합니다.

 **배포 주소**: [https://sqld-quiz-front.vercel.app/](https://sqld-quiz-front.vercel.app/)

> 프론트엔드 저장소: [chyoung001/SQLD_Quiz_Front](https://github.com/chyoung001/SQLD_Quiz_Front)

---

## 기술 스택

| 영역 | 기술 |
|------|------|
| **프레임워크** | FastAPI 0.136 + Uvicorn 0.48 |
| **데이터베이스** | MongoDB Atlas + Vector Search (`$vectorSearch`) |
| **ODM** | Beanie 1.28 (Pydantic 기반) + Motor 3.7 (비동기 드라이버) |
| **LLM — 문제 생성** | Google Gemini 3.5 Flash |
| **LLM — 품질 검증** | Claude Opus 4.7 (prompt caching 적용) |
| **LLM — 임베딩** | Gemini Embedding 001 (3072차원, 다국어) |
| **설정** | pydantic-settings 2.14 |

---

## 주요 기능

- **챕터별 문제 출제** — 12개 챕터 × 297문제 무작위 출제 (정답 자동 제거)
- **모의고사** — 1과목(ch 1-2) 10문제 + 2과목(ch 3-12) 40문제 = 50문제 + 일괄 채점
- **AI 변형 문제 생성** — 틀린 문제 N개 → RAG 컨텍스트 + Gemini 생성 + Claude 검증
- **RAG 벡터 검색** — Atlas `$vectorSearch`로 같은 챕터 내 유사 기출 top-3 추출
- **운영 도구** — 전체 문제 임베딩 일괄 생성 / RAG 상태 점검

---

## 시스템 아키텍처

```
┌─────────────────────────────────────────────────────┐
│ FastAPI                                             │
│   ├── /api/chapters       — 챕터 목록               │
│   ├── /api/questions      — 챕터별 문제 출제        │
│   ├── /api/exam/*         — 모의고사 출제·채점      │
│   ├── /api/llm/generate   — AI 변형 문제 생성       │
│   └── /api/admin/*        — 임베딩 관리 (운영자)    │
└────────────────────┬────────────────────────────────┘
                     │
       ┌─────────────┼─────────────┬────────────────┐
       ▼             ▼             ▼                ▼
┌──────────────┐ ┌─────────┐ ┌──────────┐ ┌──────────────┐
│ MongoDB      │ │ Gemini  │ │ Claude   │ │ Gemini       │
│ Atlas        │ │ 3.5     │ │ Opus 4.7 │ │ Embedding001 │
│ (문제+벡터)  │ │ (생성)  │ │ (검증)   │ │ (RAG)        │
└──────────────┘ └─────────┘ └──────────┘ └──────────────┘
```

### AI 문제 생성 파이프라인

상세 설계 명세는 [`Sqld aqg architecture.md`](Sqld%20aqg%20architecture.md)를 참조하세요.

```
[입력] 사용자가 틀린 문제 1~10개
   │
   ▼
[Step 1] 챕터 결정 — Counter로 최빈 chapter_id 채택
   │
   ▼
[Step 2] RAG 컨텍스트 구축
   ├─ 틀린 문제 텍스트 → Gemini Embedding (3072d)
   ├─ 임베딩 평균 → Atlas Vector Search ($vectorSearch)
   └─ 같은 챕터에서 유사도 top-3 기출 추출
   │
   ▼
[Step 3] Gemini 생성 (최대 2회 재시도)
   ├─ 챕터별 few-shot 예시 자동 선택 (modeling/sql/advanced)
   ├─ RAG 컨텍스트 + 출제 지침 + 제약 규칙 주입
   └─ response_schema로 JSON 출력 강제
   │
   ▼
[Step 4] Claude Opus 일괄 검증 (1회 API 호출)
   ├─ 전체 문제를 한 번에 평가 (prompt caching)
   ├─ valid / score(1-10) / feedback / corrected 반환
   ├─ valid=false면 corrected 채택, 수정 불가면 제외
   └─ API 장애 시 fallback (모두 valid:true / score:5)
   │
   ▼
[출력] 검증된 변형 문제 N개 (UUID + 품질 점수 포함)
```

### 설계 vs 현재 구현

[`Sqld aqg architecture.md`](Sqld%20aqg%20architecture.md)는 다중 에이전트 검증 + VHG 독립 검증자까지 포함한 풀 스펙입니다. 현재 구현은 단순화된 버전:

| 설계 | 현재 구현 |
|------|----------|
| L1 규칙 기반 필터 (스키마/매핑 검증) | ❌ 미구현 — Gemini `response_schema`가 부분적으로 대체 |
| L2 경량 LLM 충실도 판정 | ❌ 미구현 |
| L3 G-Eval 정밀 검증 (4차원 채점) | ✅ Claude Opus 단일 검증으로 단순화 |
| VHG 독립 검증자 (이기종 모델) | ✅ Gemini(생성) + Claude(검증) 이기종 사용 |
| Circuit Breaker (재생성 3회) | ❌ — Gemini 2회만 재시도 |
| 문항 진화 엔진 (수평/수직) | ❌ 미구현 |
| 평가 결과 영구화 | ❌ — UUID로 응답만, DB 저장 안 됨 |

---

## API 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/` | 헬스 체크 (`{status: "ok", version: "sequential-v2"}`) |
| GET | `/api/chapters` | 챕터 목록 + 문제 수 |
| GET | `/api/questions?chapter_id=N&count=10` | 챕터별 무작위 문제 (정답 제거) |
| GET | `/api/questions/{id}` | 단일 문제 조회 (정답 포함) |
| GET | `/api/exam/questions` | 모의고사 50문제 (1과목 10 + 2과목 40) |
| POST | `/api/exam/grade` | 모의고사 채점 (request: `{question_ids: [str]}`) |
| POST | `/api/llm/generate` | AI 변형 문제 생성 (`{question_ids: 1-15개, count: 1-5}`) — IP당 분당 3회 제한 |
| POST | `/api/admin/vectorize?force=false` | 전체 문제 임베딩 생성 (`X-Admin-Token` 헤더 필요) |
| GET | `/api/admin/rag-status` | RAG 임베딩 현황 + 벡터 검색 동작 확인 (`X-Admin-Token` 헤더 필요) |

### 인증 / 보호 정책

| 엔드포인트 | 보호 방식 | 설정 환경변수 |
|-----------|----------|--------------|
| `/api/admin/*` | `X-Admin-Token` 헤더로 토큰 검증. 미설정 시 503 비활성화 | `ADMIN_TOKEN` |
| `/api/llm/generate` | IP 기반 in-memory rate limit (기본 분당 3회) | `LLM_RATE_LIMIT_PER_MINUTE` |

```bash
# admin 엔드포인트 호출 예시
curl -X POST https://your-app.up.railway.app/api/admin/vectorize \
  -H "X-Admin-Token: <ADMIN_TOKEN 값>"
```

> ADMIN_TOKEN 생성: `python -c "import secrets; print(secrets.token_urlsafe(32))"`

### 자동 문서

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

---

## 데이터 구조

### Question Document

```json
{
  "_id": "ObjectId",
  "chapter_id": 3,
  "question_number": 7,
  "book_section": "II",
  "question_type": "best_choice",
  "assets": [
    {
      "asset_type": "text_block",
      "payload": { "text": "다음 SQL의 실행 결과는?" }
    },
    {
      "asset_type": "sql_query",
      "payload": { "dialect": "oracle", "code": "SELECT ..." }
    }
  ],
  "choices": [
    {
      "choice_number": 1,
      "choice_kind": "value",
      "choice_text": "4행",
      "is_correct": true
    }
  ],
  "answer": { "explanation": "..." },
  "embedding": [0.123, ...]
}
```

### 분류 체계

- **question_type 16종**: `best_choice`, `worst_choice`, `predict_result`, `fill_blank`, `identify_sql`, `derive_count` 등
- **asset_type 17종**: `text_block`, `sql_query`, `data_table`, `erd`, `execution_plan`, `entity_schema` 등
- **choice_kind 9종**: `text`, `sql_query`, `keyword`, `value`, `result_table`, `index_definition` 등

분포 데이터 및 매핑 규칙은 [`Sqld aqg architecture.md`](Sqld%20aqg%20architecture.md) §1 참조.

---

## 디렉토리 구조

```
backend/
├── main.py                  # FastAPI 앱 + 5개 라우터 등록
├── config.py                # 환경변수 (CORS는 쉼표 구분 문자열 지원)
├── requirements.txt
├── run.bat                  # Windows 실행 스크립트
├── .env.example
│
├── api/
│   ├── chapters.py          # GET /chapters
│   ├── questions.py         # 문제 조회
│   ├── exam.py              # 모의고사 출제/채점
│   ├── llm.py               # AI 변형 문제 생성
│   └── admin.py             # 임베딩 관리
│
├── models/
│   ├── database.py          # Motor + Beanie 초기화
│   └── question.py          # Question Document (assets/choices/embedding)
│
├── services/
│   ├── question_service.py  # 챕터/랜덤 출제
│   ├── llm_service.py       # Gemini 생성 + Claude 검증 파이프라인
│   └── rag_service.py       # 임베딩 + Atlas Vector Search
│
├── data/
│   └── loader.py            # JSON → MongoDB 적재 (1회성)
│
└── Sqld aqg architecture.md # 다중 에이전트 시스템 설계 명세
```

---

## 로컬 실행

### 사전 요구사항

- Python 3.11+
- MongoDB Atlas 계정 (Vector Search 인덱스 생성 가능한 M0 무료 티어로 충분)
- [Google AI Studio API Key](https://aistudio.google.com/apikey)
- [Anthropic API Key](https://console.anthropic.com/)
- SQLD 문제 JSON 데이터 (별도 제공 — `../SQLD_data/json/` 경로 필요)

### 1. 환경 설정

```bash
python -m venv venv

# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
```

`.env` 파일 생성 ([.env.example](.env.example) 참고):

```env
MONGODB_URI=mongodb+srv://<user>:<password>@<cluster>.mongodb.net/sqld_quiz
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=AIza...
# CORS_ORIGINS=http://localhost:5173  (기본값이라 생략 가능)
```

### 2. 문제 데이터 적재 (최초 1회)

`data/loader.py`는 프로젝트 루트의 `SQLD_data/json/` 폴더에서 12개 JSON 파일을 읽어 적재합니다.

```bash
python -m data.loader              # 297문제 적재 (중복 시 스킵)
python -m data.loader --force      # 기존 데이터 삭제 후 재적재
```

### 3. Atlas Vector Search 인덱스 생성

MongoDB Atlas UI → Database → Atlas Search → **Vector Search Index** 생성:

- **Index name**: `embedding_index` (코드에 하드코딩되어 있음 — [`services/rag_service.py:12`](services/rag_service.py#L12))
- **Database**: `sqld_quiz`
- **Collection**: `questions`

```json
{
  "fields": [
    { "type": "vector", "path": "embedding", "numDimensions": 3072, "similarity": "cosine" },
    { "type": "filter", "path": "chapter_id" }
  ]
}
```

### 4. 임베딩 생성 (최초 1회, 약 1~2분 소요)

```bash
# 서버 실행
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 다른 터미널에서 임베딩 일괄 생성
curl -X POST http://localhost:8000/api/admin/vectorize

# 상태 확인
curl http://localhost:8000/api/admin/rag-status
```

### 5. 서버 실행

```bash
# Windows
run.bat

# 또는 직접
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

---

## 배포 — Railway

1. [railway.app](https://railway.app) → **New Project** → Deploy from GitHub
2. **Repository**: 이 backend 저장소 선택
3. **Settings**:
   - **Root Directory**: `/` (이 저장소가 백엔드 단독이므로)
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Build Command**: `pip install -r requirements.txt` (자동 감지됨)
4. **환경변수 (Variables)**:
   | 키 | 값 |
   |----|------|
   | `MONGODB_URI` | Atlas connection string |
   | `ANTHROPIC_API_KEY` | Claude API 키 |
   | `GEMINI_API_KEY` | Gemini API 키 |
   | `CORS_ORIGINS` | `https://sqld-quiz-front.vercel.app` (쉼표 구분으로 여러 개 가능) |
5. **Generate Domain** 클릭 → `sqldquizback-production.up.railway.app` 확보
6. 프론트엔드 저장소의 `vercel.json`에 이 URL 등록 필요

### 헬스 체크

```bash
curl https://sqldquizback-production.up.railway.app/
# {"status":"ok","version":"sequential-v2"}
```

---

## 보안 체크리스트

- [x] `.env` gitignore 처리
- [x] CORS 환경변수 분리 (배포 시 도메인 화이트리스트)
- [x] `/api/admin/*` 엔드포인트 인증 (`X-Admin-Token` 헤더)
- [x] LLM 엔드포인트 rate limit (IP당 분당 3회 기본값)
- [ ] 노출된 시크릿 회수 — 개발 중 노출됐다면 키 재발급
- [ ] 다중 인스턴스 배포 시 rate limit을 Redis 기반으로 교체

---

## 향후 작업

### 단기

- [ ] AI 생성 문제 영구 저장 (`generated_questions` 컬렉션)
- [ ] LLM 호출 로깅 / 비용 추적
- [ ] 단위 테스트 도입 (pytest)

### 중기 — 학습 기록 시스템

- [ ] `UserProgress` / `StudySession` 모델 추가
- [ ] 풀이 기록 저장 API
- [ ] 오답 노트 API
- [ ] 챕터별 정답률 통계 API

### 장기 — 검증 파이프라인 고도화

[`Sqld aqg architecture.md`](Sqld%20aqg%20architecture.md)의 풀 스펙으로 진화:

- [ ] L1 규칙 기반 필터 (스키마/매핑 검증)
- [ ] L2 경량 LLM 충실도 판정
- [ ] L3 G-Eval 정밀 검증
- [ ] VHG 독립 검증자
- [ ] 문항 진화 엔진 (수평/수직)
- [ ] 한국어 용어 일관성 강제 (`주식별자` vs `기본키` 등)
- [ ] Oracle vs ANSI 방언 분리

---

## 참고 문서

- [`Sqld aqg architecture.md`](Sqld%20aqg%20architecture.md) — 다중 에이전트 시스템 설계 명세 (목표 아키텍처)
