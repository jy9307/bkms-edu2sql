# NL2SQL 에이전트 플로우와 명료화 질문 데이터셋 설계

## 1. 목표

사용자가 LMS 데이터에 대해 자연어로 질문하면, 에이전트는 질문 의도를 해석하고 필요한 경우 명료화 질문을 한 뒤 안전한 SQL을 생성한다. SQL 실행 결과는 표와 간단한 자연어 설명으로 반환한다.

예시 질문:

- "3학년 2반에서 퀴즈 안 낸 학생 보여줘"
- "AI를 많이 쓴 학생이 글쓰기 점수도 높은지 보고 싶어"
- "지난주 과학 수업 참여율 알려줘"
- "읽기 활동 오래 한 학생 순위 보여줘"

## 2. 권장 에이전트 플로우

```text
사용자 질문
  -> 1. 질문 분석
  -> 2. 명료화 필요 여부 판단
  -> 3-A. 명료화 질문 생성
  -> 3-B. SQL 생성
  -> 4. SQL 검증
  -> 5. SQL 실행
  -> 6. 결과 요약
```

## 3. 세부 플로우

### 1단계. 질문 분석

사용자 질문에서 다음 정보를 추출한다.

| 항목 | 예시 |
| --- | --- |
| 분석 대상 | 학생, 학급, 수업, 활동, 제출물, 로그 |
| 지표 | 제출률, 평균 점수, 접속 횟수, 체류 시간, 글쓰기 분량 |
| 필터 | 학년, 반, 과목, 기간, 활동 유형 |
| 정렬/순위 | 가장 높은 순, 상위 5명 |
| 집계 단위 | 학생별, 활동별, 과목별, 날짜별 |
| 결과 형태 | 목록, 개수, 평균, 순위, 비교 |

내부적으로는 아래와 같은 구조로 바꿔두면 좋다.

```json
{
  "intent": "find_non_submitters",
  "entities": {
    "grade": 3,
    "class_number": 2,
    "activity_type": "quiz",
    "date_range": null
  },
  "metrics": ["submission_status"],
  "group_by": ["student"],
  "order_by": null,
  "needs_clarification": true
}
```

### 2단계. 명료화 필요 여부 판단

질문이 모호하면 바로 SQL을 만들지 않고 먼저 되묻는다.

명료화가 필요한 대표 상황:

| 모호한 표현 | 필요한 질문 |
| --- | --- |
| "최근" | 최근 7일, 이번 달, 가장 최근 수업 중 무엇을 의미하나요? |
| "많이 쓴", "분량이 많은" | 글자 수 합계, 평균 글자 수, 제출 글 수 중 무엇으로 볼까요? |
| "참여율" | 접속 기준, 활동 시작 기준, 제출 기준 중 무엇으로 볼까요? |
| "잘한 학생" | 점수 기준, 제출 여부 기준, 활동량 기준 중 무엇으로 볼까요? |
| "우리 반" | 몇 학년 몇 반을 의미하나요? |
| "그 활동" | 어떤 활동을 의미하나요? |

명료화가 필요 없는 질문:

- "3학년 2반 학생들의 평균 퀴즈 점수를 보여줘"
- "2026년 5월 과학 수업의 제출률을 알려줘"
- "글쓰기 분량이 가장 많은 학생 5명을 보여줘"

### 3-A단계. 명료화 질문 생성

명료화 질문은 한 번에 1개만 하는 것이 좋다. 질문이 너무 많으면 사용자가 부담을 느끼고, NL2SQL 과제 시연에서도 흐름이 끊긴다.

좋은 예:

```text
"참여율"을 어떤 기준으로 계산할까요? 접속 기준, 활동 시작 기준, 제출 기준 중 하나를 선택해주세요.
```

나쁜 예:

```text
기간은 언제인가요? 과목은 무엇인가요? 학급은 무엇인가요? 참여율 기준은 무엇인가요?
```

우선순위:

1. SQL 결과가 완전히 달라지는 기준
2. 필수 필터, 예: 학급/기간/활동
3. 정렬이나 출력 개수

### 3-B단계. SQL 생성

SQL 생성 시 에이전트에게 아래 원칙을 강제한다.

- `SELECT` 쿼리만 생성한다.
- `DROP`, `DELETE`, `UPDATE`, `INSERT`, `ALTER`, `TRUNCATE`는 금지한다.
- 필요한 테이블만 조인한다.
- 결과가 너무 많을 수 있으면 기본 `LIMIT 50`을 붙인다.
- 사용자가 특정 기간을 말하지 않으면 전체 기간으로 조회하되, 결과 설명에 "전체 기간 기준"이라고 명시한다.
- 테이블명과 컬럼명은 스키마 문서에 있는 것만 사용한다.

### 4단계. SQL 검증

실행 전 검증:

- 금지 키워드 포함 여부
- 존재하지 않는 테이블/컬럼 사용 여부
- `SELECT`로 시작하는지
- 무제한 대량 조회 위험 여부
- 조인 조건 누락 여부

가능하면 `EXPLAIN`을 먼저 실행해 문법 오류를 잡는다.

### 5단계. SQL 실행

실행 결과는 원본 row와 함께 메타데이터를 저장한다.

```json
{
  "sql": "SELECT ...",
  "row_count": 12,
  "columns": ["student_name", "score"],
  "rows": []
}
```

### 6단계. 결과 요약

결과 응답은 세 부분으로 구성한다.

1. 짧은 결론
2. 결과 표
3. 실행한 SQL

예시:

```text
3학년 2반에서 퀴즈를 제출하지 않은 학생은 총 3명입니다.

| 학생 | 활동 | 상태 |
| --- | --- | --- |
| 최수아 | 상태 변화 퀴즈 | assigned |
| 류준서 | 분수 곱셈 퀴즈 | in_progress |

사용한 SQL:
SELECT ...
```

## 4. 에이전트 구성안

복잡한 멀티 에이전트보다, 과제용으로는 역할이 분리된 단일 파이프라인이 좋다.

| 모듈 | 역할 |
| --- | --- |
| SchemaProvider | 테이블/컬럼/관계/용어 사전을 제공 |
| QuestionAnalyzer | 사용자 질문을 구조화 |
| ClarificationDecider | 명료화 질문 필요 여부 판단 |
| SQLGenerator | SQL 초안 생성 |
| SQLValidator | SQL 안전성/문법/스키마 검증 |
| QueryExecutor | DB 조회 실행 |
| AnswerFormatter | 결과 표와 설명 생성 |

흐름:

```text
QuestionAnalyzer
  -> ClarificationDecider
  -> SQLGenerator
  -> SQLValidator
  -> QueryExecutor
  -> AnswerFormatter
```

## 5. 명료화 질문 데이터셋 제공 방식

명료화 질문은 LLM이 즉흥적으로만 만들게 하지 말고, 별도 데이터셋으로 제공하는 것이 좋다.

추천 형태는 `clarification_rules.json`이다.

```json
[
  {
    "id": "ambiguous_recent",
    "trigger_keywords": ["최근", "요즘", "최근에"],
    "missing_slot": "date_range",
    "question": "\"최근\"은 어떤 기간을 의미하나요?",
    "options": ["최근 7일", "이번 달", "가장 최근 수업"],
    "default_if_skipped": "최근 7일"
  },
  {
    "id": "ambiguous_participation_rate",
    "trigger_keywords": ["참여율", "참여도"],
    "missing_slot": "participation_metric",
    "question": "참여율을 어떤 기준으로 계산할까요?",
    "options": ["수업 접속 기준", "활동 시작 기준", "제출 완료 기준"],
    "default_if_skipped": "활동 시작 기준"
  }
]
```

## 6. 명료화 데이터셋에 들어갈 정보

각 rule은 다음 필드를 가지면 충분하다.

| 필드 | 설명 |
| --- | --- |
| id | 규칙 ID |
| trigger_keywords | 모호성을 유발하는 표현 |
| intent | 적용되는 질문 의도 |
| missing_slot | 채워야 하는 정보 |
| question | 사용자에게 물어볼 질문 |
| options | 선택지 |
| default_if_skipped | 사용자가 답하지 않았을 때 기본값 |
| examples | 해당 규칙이 적용되는 사용자 질문 예시 |

## 7. 명료화 규칙 예시

```json
[
  {
    "id": "missing_class",
    "trigger_keywords": ["우리 반", "학생들", "반 학생"],
    "missing_slot": "class_scope",
    "question": "몇 학년 몇 반을 기준으로 조회할까요?",
    "options": ["3학년 2반", "전체 학급"],
    "default_if_skipped": "전체 학급",
    "examples": ["우리 반에서 퀴즈 안 낸 학생 보여줘"]
  },
  {
    "id": "ambiguous_good_student",
    "trigger_keywords": ["잘한", "우수한", "상위"],
    "missing_slot": "performance_metric",
    "question": "잘한 학생을 어떤 기준으로 볼까요?",
    "options": ["평균 점수", "제출률", "활동 로그 수"],
    "default_if_skipped": "평균 점수",
    "examples": ["과학 수업에서 잘한 학생 보여줘"]
  },
  {
    "id": "ambiguous_writing_length",
    "trigger_keywords": ["글쓰기 분량", "많이 쓴", "긴 글", "글자 수"],
    "missing_slot": "writing_length_metric",
    "question": "글쓰기 분량을 어떤 기준으로 계산할까요?",
    "options": ["글자 수 합계", "평균 글자 수", "제출 글 수"],
    "default_if_skipped": "글자 수 합계",
    "examples": ["글쓰기 분량 많은 학생 순위 보여줘"]
  },
  {
    "id": "ambiguous_reading_time",
    "trigger_keywords": ["오래 읽은", "읽기 시간", "체류 시간"],
    "missing_slot": "reading_time_metric",
    "question": "읽기 시간은 어떤 로그를 기준으로 계산할까요?",
    "options": ["page_viewed duration 합계", "page_viewed duration 평균"],
    "default_if_skipped": "page_viewed duration 합계",
    "examples": ["읽기 활동 오래 한 학생 보여줘"]
  },
  {
    "id": "missing_date_range",
    "trigger_keywords": ["제출률", "평균", "순위", "참여율"],
    "missing_slot": "date_range",
    "question": "조회 기간을 지정할까요?",
    "options": ["전체 기간", "이번 달", "최근 7일"],
    "default_if_skipped": "전체 기간",
    "examples": ["과학 수업 제출률 알려줘"]
  }
]
```

## 8. 스키마 사전도 함께 제공하기

명료화 데이터셋만 있으면 부족하다. 에이전트가 "참여율", "글쓰기 분량", "읽기 시간" 같은 말을 실제 컬럼으로 매핑할 수 있도록 스키마 사전도 같이 제공해야 한다.

추천 파일:

```text
schema_dictionary.json
clarification_rules.json
query_examples.json
```

### schema_dictionary.json 예시

```json
{
  "tables": {
    "users": {
      "description": "학생, 교사, 관리자 정보",
      "important_columns": ["user_id", "name", "role", "grade", "class_number"]
    },
    "submissions": {
      "description": "학생별 활동 제출 상태와 점수",
      "important_columns": ["submission_id", "run_id", "student_id", "status", "score", "submitted_at"]
    },
    "activity_logs": {
      "description": "활동 중 발생한 학생 행동 로그",
      "important_columns": ["run_id", "user_id", "event_type", "section", "duration_ms", "occurred_at"]
    }
  },
  "metric_mappings": {
    "제출률": "submitted submissions / total submissions",
    "평균 점수": "AVG(submissions.score)",
    "글쓰기 분량": "SUM(writing_submissions.char_count)",
    "읽기 시간": "SUM(activity_logs.duration_ms) WHERE event_type = 'page_viewed'",
    "접속 횟수": "COUNT(access_logs.access_log_id) WHERE action = 'login'"
  }
}
```

### query_examples.json 예시

```json
[
  {
    "question": "3학년 2반에서 퀴즈를 제출하지 않은 학생은?",
    "sql": "SELECT u.name, a.title, s.status FROM submissions s JOIN users u ON u.user_id = s.student_id JOIN activity_runs ar ON ar.run_id = s.run_id JOIN activities a ON a.activity_id = ar.activity_id WHERE u.role = 'student' AND u.grade = 3 AND u.class_number = 2 AND a.activity_type = 'quiz' AND s.status <> 'submitted';"
  }
]
```

## 9. 추천 구현 순서

1. `schema_dictionary.json` 작성
2. `clarification_rules.json` 작성
3. 질문 분석 결과를 JSON으로 뽑는 함수 작성
4. 명료화 필요 여부 판단 함수 작성
5. SQL 생성 프롬프트 작성
6. SQL validator 작성
7. DB 실행과 결과 포맷팅 연결
8. 대표 질문 20개로 테스트

## 10. 과제 발표에서 설명할 포인트

- 에이전트가 바로 SQL을 만들지 않고, 질문이 모호하면 먼저 되묻는다.
- 명료화 질문은 하드코딩된 if문이 아니라 별도 규칙 데이터셋으로 관리한다.
- 스키마 사전과 예시 SQL을 제공해 LLM이 테이블과 컬럼을 안정적으로 선택하게 한다.
- SQL 실행 전 검증 단계를 두어 위험한 쿼리를 차단한다.
- 결과는 SQL뿐 아니라 사용자가 이해할 수 있는 자연어 요약으로 반환한다.
