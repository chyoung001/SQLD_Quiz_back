# SQLD 자동 문제 생성 시스템 — 아키텍처 설계 명세서

> **목적**: 구조화된 JSON 문제은행 데이터를 원천으로, RAG와 다중 에이전트 LLM을 활용하여 SQLD 시험 문제를 자동 생성하고 할루시네이션을 차단하는 시스템을 구축한다.

---

## 1. 원천 데이터 현황

### 1.1 파일 구조

12개 JSON 파일, 총 297문제.

| 파일 | subject_id | chapter_id | 문제 수 |
|------|-----------|-----------|--------|
| 1__데이터_모델링의_이해.json | 1 | 1 | 33 |
| 2__데이터_모델과_SQL.json | 1 | 2 | 17 |
| 3__SQL_기본.json | 2 | 1 | 50 |
| 4__SQL활용.json | 2 | 2 | 48 |
| 5__관리구문.json | 2 | 3 | 28 |
| 6__SQL_수행_구조.json | 3 | 1 | 19 |
| 7__SQL_분석_도구.json | 3 | 2 | 11 |
| 8__인덱스_튜닝.json | 3 | 3 | 23 |
| 9__조인_튜닝.json | 3 | 4 | 14 |
| 10__SQL_옵티마이저.json | 3 | 5 | 17 |
| 11__고급_SQL_튜닝.json | 3 | 6 | 25 |
| 12__Lock과_트랜잭션_동시성_제어.json | 3 | 7 | 12 |

### 1.2 question_type 분류 (16종)

```
best_choice        : 102건  ← 가장 적절한 것 선택
worst_choice       : 100건  ← 가장 적절하지 않은 것 선택
predict_result     :  24건  ← SQL 실행 결과 예측
fill_blank         :  18건  ← 빈칸 채우기 (단일)
fill_blanks_multi  :  10건  ← 빈칸 채우기 (복수)
identify_sql       :  10건  ← 올바른 SQL 식별
different_result   :   8건  ← 다른 결과를 내는 SQL 식별
derive_count       :   5건  ← 수치 도출 (엔터티 수 등)
identify_normal_form:  4건  ← 정규형 식별
find_erroneous     :   3건  ← 오류 있는 SQL 식별
same_result        :   3건  ← 동일 결과 SQL 식별
design_index       :   3건  ← 인덱스 설계
correct_ordering   :   2건  ← 올바른 순서 선택
select_all_correct :   2건  ← 올바른 것 모두 선택
diagnose_action    :   2건  ← 진단 및 조치 방안
compute_metric     :   1건  ← 수치 계산
```

### 1.3 asset_type 분류 (17종)

```
text_block          : 349건  ← 일반 텍스트 지문
sql_query           :  92건  ← SELECT/DML SQL문
data_table          :  64건  ← 테이블 데이터 (컬럼+로우)
list_items          :  16건  ← 항목 리스트
sql_ddl             :  16건  ← CREATE/ALTER/DROP문
result_table        :  14건  ← SQL 실행 결과 테이블
entity_schema       :  12건  ← 엔터티 스키마 정의
execution_plan      :   7건  ← 실행계획
erd                 :   7건  ← ERD 다이어그램
sql_trace           :   2건  ← SQL 트레이스
schema_variant_pair :   2건  ← 정규화 전후 비교
sql_dml             :   2건  ← INSERT/UPDATE/DELETE
functional_dependency: 1건  ← 함수 종속성
code_compare        :   1건  ← 코드 비교
transaction_steps   :   1건  ← 트랜잭션 단계
concurrent_timeline :   1건  ← 동시성 타임라인
awr_report          :   1건  ← AWR 리포트
```

### 1.4 choice_kind 분류 (9종)

```
text             : 569건  ← 일반 텍스트 보기
sql_query        : 180건  ← SQL문 보기
keyword          : 140건  ← 단일 키워드 보기
tuple            :  72건  ← 값 조합 보기
value            :  63건  ← 단일 값 보기
sql_fragment     :  52건  ← SQL 조각 보기
description      :  52건  ← 설명문 보기
result_table     :  48건  ← 결과 테이블 보기
index_definition :  12건  ← 인덱스 정의 보기
```

### 1.5 question_type → asset_type 매핑 규칙 (필수 제약)

아래는 실제 데이터에서 추출한 co-occurrence 패턴이다. 생성자는 이 매핑을 위반하는 문제를 만들어서는 안 된다.

```yaml
# 고빈도 패턴 (필수 준수)
predict_result:
  required_assets: [data_table, sql_query, text_block]  # 20건/24건 (83%)
  alt_assets: [sql_query, text_block]                    # 2건

identify_sql:
  required_assets: [data_table, result_table, text_block]  # 4건
  alt_assets: [data_table, text_block]                     # 2건

fill_blank:
  common_assets:
    - [text_block]                                         # 4건
    - [sql_query, text_block]                              # 4건
    - [result_table, sql_query, text_block]                # 4건

best_choice:
  common_assets:
    - [text_block]                                         # 50건 (단순 지식형)
    - [sql_query, text_block]                              # 15건 (SQL 분석형)
    - [data_table, sql_query, text_block]                  # 4건
    - [erd, text_block]                                    # 3건
    - [execution_plan, text_block]                         # 2건

worst_choice:
  common_assets:
    - [text_block]                                         # 80건 (대부분 단순 지식형)

design_index:
  required_assets: [sql_query, text_block]
  required_choice_kind: index_definition

identify_normal_form:
  required_choice_kind: keyword
  common_assets:
    - [data_table, text_block]
    - [entity_schema, text_block]

derive_count:
  required_choice_kind: value
```

### 1.6 question_type → choice_kind 매핑 규칙

```yaml
predict_result:
  - result_table  # 12건 (결과 테이블로 보기 제시)
  - value         # 9건 (단일 값으로 보기 제시)

identify_sql:       sql_query
different_result:   sql_query
same_result:        sql_query
find_erroneous:     sql_query

design_index:       index_definition
identify_normal_form: keyword
derive_count:       value

best_choice:   text | sql_query | keyword | tuple | description | sql_fragment
worst_choice:  text | description | keyword | sql_query
fill_blank:    keyword | sql_fragment | text
```

### 1.7 단일 문제 JSON 스키마

```jsonc
{
  "question_number": 1,
  "book_section": "I",                    // I, II, III
  "book_question_number": 1,
  "question_type": "best_choice",         // 16종 중 하나
  "assets": [                             // 1~4개, 순서 유지
    {
      "asset_type": "text_block",         // 17종 중 하나
      "payload": {
        "text": "문제 지문 텍스트"
      }
    },
    {
      "asset_type": "sql_query",
      "payload": {
        "dialect": "oracle",              // "oracle" | "ansi"
        "code": "SELECT * FROM EMP;"
      }
    },
    {
      "asset_type": "data_table",
      "payload": {
        "name": "EMP",
        "columns": ["EMPNO", "ENAME", "SAL"],
        "rows": [
          {"EMPNO": 7369, "ENAME": "SMITH", "SAL": 800}
        ],
        "sub_kind": "generic"             // optional
      }
    }
  ],
  "choices": [                            // 보통 4개
    {
      "choice_number": 1,
      "choice_kind": "text",              // 9종 중 하나
      "choice_text": "보기 텍스트",
      "is_correct": false
      // choice_kind가 "value"일 때 추가:
      // "payload": 5
    }
  ],
  "answer": {
    "explanation": "정답 해설 텍스트"
  }
}
```

---

## 2. 시스템 아키텍처 개요

```
┌─────────────────────────────────────────────────────────────┐
│                    Layer 1: 데이터 입력                       │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────────┐       │
│  │ JSON     │  │ 벡터 DB      │  │ 스키마 레지스트리 │       │
│  │ 문제은행 │  │ (RAG 교재)   │  │ (입출력 계약)    │       │
│  └────┬─────┘  └──────┬───────┘  └────────┬─────────┘       │
└───────┼───────────────┼───────────────────┼─────────────────┘
        │               │                   │
        ▼               │                   ▼
┌───────────────────────┼─────────────────────────────────────┐
│     Layer 2: 전처리    │                                     │
│  ┌─────────────────┐  │  ┌───────────────────┐              │
│  │ DFS 엔티티 조합 │──┼─→│ 컨텍스트 스코어링 │              │
│  │ 탐색기          │  │  │ (4축 평가)        │              │
│  └─────────────────┘  │  └─────────┬─────────┘              │
└───────────────────────┼────────────┼────────────────────────┘
                        │            │
                        │            ▼
┌───────────────────────┼─────────────────────────────────────┐
│     Layer 3: 생성자 에이전트                                  │
│  ┌────────────────┐  ┌────────────────┐  ┌───────────────┐  │
│  │ 무관용 페르소나 │→│ 시드 문제 생성 │→│ 문항 진화 엔진 │  │
│  │ (JSON 컴파일러)│  │ (핵심어 기반)  │  │ (수평/수직)   │  │
│  └────────────────┘  └────────────────┘  └───────┬───────┘  │
│  ┌────────────────┐  ┌────────────────┐          │          │
│  │ ERD/다이어그램 │  │ 한국어 퓨샷    │          │          │
│  │ 생성           │  │ 보정           │          │          │
│  └────────────────┘  └────────────────┘          │          │
└──────────────────────────────────────────────────┼──────────┘
                                                   │
                        ┌──────────────────────────┤
                        │                  거부 시  │
                        │               피드백+롤백 │
                        ▼                    ▲      │
┌────────────────────────────────────────────┼──────┼──────────┐
│     Layer 4: 평가자 에이전트               │      │          │
│  ┌──────┐  ┌──────────────┐  ┌────────────┴─┐   │          │
│  │ L1   │→│ L2           │→│ L3            │───┘          │
│  │ 규칙 │  │ 경량 LLM     │  │ G-Eval+QAG   │              │
│  │ 기반 │  │ 이진 분류    │  │ 정밀 검증    │              │
│  └──────┘  └──────────────┘  └──────────────┘              │
│  ┌────────────────┐  ┌────────────────┐                     │
│  │ RAG 교차 대조  │  │ 자기 일관성    │                     │
│  └────────────────┘  └────────────────┘                     │
└────────────────────────────────────────────┬────────────────┘
                                             │
                                             ▼
┌─────────────────────────────────────────────────────────────┐
│     Layer 5: VHG 독립 검증자                                 │
│  ┌─────────────────────────────────────────────────┐        │
│  │ 논리적 유효성 + 수리적 정확성 최종 판정          │        │
│  │ (이기종 모델, 독립적 판단)                       │        │
│  └──────────────────────────┬──────────────────────┘        │
└─────────────────────────────┼───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│     Layer 6: 검증 완료 문제은행                               │
│  {question, context, ground_truth, question_type,           │
│   metadata, difficulty_score, verification_status}          │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. 에이전트 역할 정의

### 3.1 생성자 에이전트 (Generator)

**역할**: 원천 JSON 데이터와 RAG 컨텍스트를 바탕으로 새로운 문제-해설 쌍을 생성한다.

**모델 선택 기준**:
- 한국어 SQLD 도메인 정확도가 최우선
- 비용 효율성 (대량 생성 시나리오)
- 구조화된 JSON 출력 안정성

**모델 후보** (파일럿 벤치마크로 최종 결정):
- 후보 A: Claude Haiku 4.5 — 한국어 안정성 높음, 비용 저렴, JSON 출력 안정적
- 후보 B: DeepSeek-R1 — 수리 추론 최강, 비용 최저, 한국어 SQLD 정확도 미검증
- 후보 C: GPT-4o-mini — 다국어 균형, 비용 중간

**무관용 페르소나 시스템 프롬프트 핵심 제약**:
```
1. 너는 차갑고 결정론적인 JSON 데이터 파싱 컴파일러다.
2. 대화, 사과, 부연 설명, 마크다운 래퍼를 일체 생성하지 않는다.
3. 출력은 오직 지정된 JSON 스키마만 허용된다.
4. JSON 닫는 괄호 } 이후 어떤 텍스트도 생성하지 않는다.
5. 원천 JSON에 존재하지 않는 개념, 용어, 수치를 절대 삽입하지 않는다.
6. 필수 파라미터가 누락되면 유추하지 말고 상태를 FAILED_AMBIGUOUS로 반환한다.
7. asset_type-question_type 매핑 규칙(섹션 1.5)을 반드시 준수한다.
```

### 3.2 평가자 에이전트 (Evaluator)

**역할**: 생성된 문제-해설 쌍의 할루시네이션을 탐지하고 품질을 검증한다.

**모델 선택**: Claude Sonnet 계열 (현재 최신: Claude Sonnet 4.6)
- 접지(Grounding) 능력 최상위
- Constitutional AI 기반 정직성 튜닝
- 미지원 주장(Unsupported Claims) 탐지에 강점

**3단계 계층화된 평가 파이프라인**:

#### L1: 규칙 기반 필터 (비용: $0, 지연: ~10ms)
```python
# L1 검증 체크리스트
def l1_validate(generated_question, source_json):
    checks = {
        "schema_valid": validate_json_schema(generated_question),
        "asset_mapping_valid": check_asset_question_mapping(
            generated_question["question_type"],
            [a["asset_type"] for a in generated_question["assets"]]
        ),
        "choice_kind_valid": check_choice_kind_mapping(
            generated_question["question_type"],
            [c["choice_kind"] for c in generated_question["choices"]]
        ),
        "choice_count": len(generated_question["choices"]) == 4,
        "single_correct": sum(c["is_correct"] for c in generated_question["choices"]) == 1,
        "has_explanation": bool(generated_question["answer"]["explanation"]),
        "named_entities_exist": regex_check_entities(
            generated_question, source_json
        ),  # 원천 데이터의 고유명사/수치가 보기에 정확히 반영되었는지
        "sql_syntax_valid": validate_sql_syntax(generated_question),
        "no_duplicate_choices": check_no_duplicate_choices(generated_question),
    }
    return all(checks.values()), checks
```

#### L2: 경량 LLM 이진 분류 (비용: 저, 지연: ~1초)
```yaml
task: 충실도(Faithfulness) 이진 판정
input: [원천_JSON_컨텍스트, 생성된_문제]
output: { faithful: true/false, reason: "..." }
prompt_strategy: Direct Scoring (이진 분류)
focus:
  - 모순(Contradiction) 탐지: 생성된 내용이 원천과 직접 충돌하는가?
  - 미지원 주장(Unsupported Claims) 탐지: 원천에 없는 외부 지식이 삽입되었는가?
```

#### L3: G-Eval 정밀 검증 (비용: 고, 지연: ~5초)
```yaml
trigger: L2 통과 문제 중 고난이도(predict_result, identify_normal_form 등)만
task: G-Eval 다차원 채점 + QAG 교차 검증
dimensions:
  - faithfulness: 원천 데이터 접지 정확도 (1-5)
  - logical_consistency: 문제-정답-해설 간 논리적 일관성 (1-5)
  - difficulty_calibration: 난이도 표기와 실제 난이도 일치 (1-5)
  - distractor_quality: 오답 보기의 그럴듯함과 교육적 가치 (1-5)
process:
  1. Auto-CoT로 평가 단계를 모델이 스스로 구체화
  2. 각 차원별 점수 산출
  3. QAG: 해당 문제에 대한 3~5개의 세부 폐쇄형 질문을 자가 생성→자가 답변
  4. 세부 답변들의 자기 일관성(Self-consistency) 확인
  5. 최종 합격/거부 판정
```

### 3.3 독립 검증자 에이전트 (Verifier — VHG 프레임워크)

**역할**: 생성자/평가자와 완전히 독립된 제3의 모델로, 문제-해설 쌍의 논리적 유효성만 판정한다.

**모델 선택**: 생성자/평가자와 반드시 다른 모델 계열
- 예: 생성자=Haiku, 평가자=Sonnet이면 검증자=GPT-4o 또는 Gemini

**검증 범위**:
```yaml
1. 문제에 정답이 존재하는가 (해답 불가능 문제 차단)
2. 해설이 정답을 논리적으로 도출하는가
3. 오답 보기가 명확히 오답인가 (애매한 보기 차단)
4. SQL 문제의 경우: 실행 결과가 정답과 일치하는가 (가능한 경우 실제 실행 검증)
```

**Circuit Breaker**: 재생성 최대 3회. 3회 모두 거부되면 해당 엔티티 조합을 "생성 불가"로 마킹하고 건너뛴다.

---

## 4. RAG 파이프라인 설계

### 4.1 벡터 DB 구축 대상

```yaml
primary_source:
  - 원천 JSON 문제은행 12개 파일 (ground truth)
  - 각 문제의 answer.explanation 텍스트

secondary_source (RAG 보조 검증용):
  - SQLD 공식 교재/가이드
  - SQL 표준 문서
  - Oracle/SQL Server 공식 문서 (방언 차이 검증용)
```

### 4.2 우선순위 정책

```
원천 JSON (ground truth) > RAG 교재 컨텍스트 > 모델 내재 지식

- 원천 JSON의 해설과 RAG 교재가 충돌할 경우: 원천 JSON이 우선
- RAG는 보조 검증 용도로만 사용 (평가자의 교차 대조 소스)
- 생성자는 원천 JSON만 참조, RAG는 평가자만 접근
```

### 4.3 임베딩 전략

```yaml
chunk_strategy:
  - 문제 단위 청킹 (1문제 = 1청크)
  - 해설 텍스트는 별도 청크로 분리하여 유사 해설 검색 가능
  - 교재 텍스트는 512토큰 단위, 128토큰 오버랩

metadata_per_chunk:
  - subject_id, chapter_id
  - question_type
  - asset_types (리스트)
  - keywords (자동 추출)

retrieval_at_generation:
  - 생성자에게 해당 chapter의 기존 문제를 3~5개 퓨샷으로 제공
  - 유사 문제 중복 생성 방지를 위한 유사도 필터 (threshold: 0.85)

retrieval_at_evaluation:
  - 평가자가 교재 RAG에서 관련 개념을 검색하여 교차 대조
```

---

## 5. 데이터 흐름 상세

### 5.1 단일 문제 생성 사이클

```
[입력] chapter_id=8, question_type=best_choice 요청
  │
  ▼
[Step 1] DFS 엔티티 조합 탐색
  - JSON 8__인덱스_튜닝.json에서 엔티티 추출
  - 출력: {entities: ["인덱스 범위 스캔", "NL조인", "선두 칼럼"], context_score: 2.8}
  - 임계값(1.5) 통과 → 계속
  │
  ▼
[Step 2] 퓨샷 예시 검색 (RAG)
  - 벡터 DB에서 chapter_id=8 + question_type=best_choice인 기존 문제 3개 검색
  - 유사도 0.85 이상인 기존 문제 확인 (중복 방지)
  │
  ▼
[Step 3] 생성자 호출
  - 시스템 프롬프트: 무관용 페르소나 + 스키마 계약
  - 사용자 프롬프트: 엔티티 조합 + 퓨샷 예시 + 원천 컨텍스트
  - 출력: JSON 문제 객체
  │
  ▼
[Step 4] L1 규칙 기반 검증
  - JSON 스키마 유효성 ✓
  - asset-question 매핑 ✓
  - choice_kind 매핑 ✓
  - 보기 4개, 정답 1개 ✓
  - SQL 문법 ✓
  │ ✗ → 즉시 거부, 재생성 (Step 3으로)
  ▼
[Step 5] L2 경량 LLM 충실도 판정
  - 모순/미지원 주장 이진 분류
  │ ✗ → 거부 사유 반환, 재생성 (Step 3으로)
  ▼
[Step 6] L3 G-Eval 정밀 검증 (조건부)
  - question_type이 predict_result, identify_normal_form,
    derive_count, diagnose_action인 경우만 실행
  - 4차원 채점 + QAG 교차 검증
  │ ✗ → 거부 사유 반환, 재생성 (Step 3으로, max 3회)
  ▼
[Step 7] VHG 독립 검증 (최종)
  - 이기종 모델로 논리적 유효성 최종 판정
  │ ✗ → "생성 불가" 마킹, 다음 엔티티 조합으로
  ▼
[Step 8] 문항 진화 (선택적)
  - 수평적 진화: 같은 개념, 다른 시나리오
  - 수직적 진화: 제약 조건 추가, 다중 컨텍스트 결합
  - 진화된 문제는 Step 4~7을 다시 거침
  │
  ▼
[출력] 검증 완료 문제 → 최종 문제은행 DB에 저장
```

### 5.2 피드백 루프 데이터 형식

```jsonc
// 평가자 → 생성자 거부 피드백
{
  "status": "REJECTED",
  "retry_count": 1,            // 현재 재시도 횟수 (max: 3)
  "rejection_type": "unsupported_claim",  // "contradiction" | "unsupported_claim" | "schema_violation" | "ambiguous_distractor"
  "rejection_detail": "보기 3번에 '클러스터 인덱스는 항상 B-Tree 구조를 사용한다'는 주장이 있으나, 원천 데이터에 해당 내용이 존재하지 않음",
  "problematic_field": "choices[2].choice_text",
  "source_context": "원천 JSON에는 클러스터 인덱스의 구조에 대한 언급 없음",
  "instruction": "보기 3번을 원천 데이터 내에 근거가 있는 내용으로 교체할 것"
}
```

### 5.3 최종 출력 스키마

```jsonc
{
  "question_id": "gen_ch8_001",
  "source_chapter_id": 8,
  "source_subject_id": 3,
  "generation_metadata": {
    "generator_model": "claude-haiku-4-5",
    "evaluator_model": "claude-sonnet-4-6",
    "verifier_model": "gpt-4o",
    "generation_timestamp": "2026-05-26T14:30:00Z",
    "retry_count": 0,
    "evolution_type": null,        // null | "horizontal" | "vertical"
    "parent_question_id": null     // 진화된 문제의 경우 원본 ID
  },
  "verification": {
    "l1_passed": true,
    "l2_faithful": true,
    "l3_geval_scores": {
      "faithfulness": 5,
      "logical_consistency": 5,
      "difficulty_calibration": 4,
      "distractor_quality": 4
    },
    "vhg_approved": true,
    "difficulty_score": 3          // 1(쉬움)~5(매우 어려움)
  },

  // 기존 문제 스키마와 동일한 구조
  "question_number": 1,
  "question_type": "best_choice",
  "assets": [ ... ],
  "choices": [ ... ],
  "answer": {
    "explanation": "..."
  }
}
```

---

## 6. 한국어 SQLD 도메인 특화 전략

### 6.1 퓨샷 프롬프트 내 필수 예시

시스템 프롬프트에 아래 유형별로 최소 2개의 (입력→출력) 매핑 예시를 하드코딩한다:
- best_choice + text_block (가장 빈도 높음)
- predict_result + data_table + sql_query (가장 복잡)
- identify_normal_form + entity_schema (도메인 특화)

### 6.2 한국어 용어 일관성 제약

```yaml
# 생성자에 강제할 용어 매핑 (LLM이 번역 변형을 만들지 못하게)
term_constraints:
  - "부분 함수 종속" (not "부분 함수 의존", "Partial FD")
  - "이행적 종속" (not "이행 종속", "전이 종속")
  - "반정규화" (not "비정규화", "역정규화")
  - "주식별자" (not "기본키", "Primary Key") # SQLD 시험에서는 "주식별자" 용어 사용
  - "제1정규형" (not "1NF", "1차 정규형") # 단, 보기에서는 혼용 가능
```

### 6.3 Oracle vs ANSI 방언 구분

```yaml
dialect_rules:
  - sql_query asset에 반드시 dialect 필드 포함 ("oracle" | "ansi")
  - Oracle 전용 문법: DECODE, NVL, NVL2, (+) 조인, ROWNUM, CONNECT BY
  - ANSI 전용 문법: COALESCE, CASE WHEN, LEFT/RIGHT JOIN, ROW_NUMBER()
  - 문제에서 방언 혼용 금지 (하나의 문제 내에서 일관된 방언 사용)
```

---

## 7. 구현 우선순위

```
Phase 1 (MVP):
  ├─ L1 규칙 기반 검증기 구현 (JSON 스키마 + 매핑 규칙)
  ├─ 생성자 프롬프트 템플릿 설계 (best_choice, worst_choice만)
  ├─ 파일럿 벤치마크 (3개 모델 × 50문제 생성 → 인간 평가)
  └─ 최적 생성자 모델 선정

Phase 2 (Core):
  ├─ L2 경량 LLM 평가자 파이프라인
  ├─ 피드백 루프 + Circuit Breaker
  ├─ predict_result, fill_blank 등 복합 문제 유형 확장
  └─ RAG 벡터 DB 구축 (교재 임베딩)

Phase 3 (Advanced):
  ├─ L3 G-Eval 정밀 검증
  ├─ VHG 독립 검증자 (이기종 모델)
  ├─ 문항 진화 엔진 (수평/수직)
  └─ QAG 자기 일관성 검증

Phase 4 (Optimization):
  ├─ 인-디코딩 협업 (실시간 롤백)
  ├─ 난이도 자동 보정
  ├─ Mermaid ERD 문제 생성
  └─ 비용/품질 대시보드
```

---

## 8. 핵심 주의사항

1. **원천 JSON이 ground truth**: 어떤 상황에서도 원천 데이터를 변형하거나 무시하지 않는다.
2. **매핑 규칙은 하드코딩**: question_type-asset_type, question_type-choice_kind 매핑은 LLM에 의존하지 않고 코드 레벨에서 강제한다.
3. **이기종 모델 필수**: 생성자와 평가자는 반드시 서로 다른 모델 계열을 사용한다.
4. **평가 비용 > 생성 비용 가능**: L3 G-Eval은 조건부로만 실행하여 비용을 제어한다.
5. **한국어 퓨샷 필수**: 영어 프롬프트로 한국어 출력을 기대하지 않는다. 입출력 모두 한국어 예시를 제공한다.
6. **방언 혼용 금지**: 하나의 문제 내에서 Oracle과 ANSI 문법을 섞지 않는다.
7. **Circuit Breaker**: 재생성 3회 초과 시 해당 조합을 포기하고 로그에 기록한다.