import json
import os
from typing import Any

from openai import OpenAI

from .db import run_read_only_sql
from .retriever import Retriever
from .sql_validator import SQLValidator


class NL2SQLAgent:
    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.retriever = Retriever()
        self.validator = SQLValidator()
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = config.get("llm", {}).get("model", "gpt-4o")

    def answer_question(self, question: str, state: dict | None = None) -> dict:
        """Main entry point for answering a natural language question."""
        if state and state.get("pending_clarification"):
            state = self._handle_clarification_answer(question, state)
            question = state["original_question"]
        else:
            state = {
                "mode": "ready",
                "original_question": question,
                "clarification_answers": {},
                "pending_clarification": None,
            }

        # 1. Retrieve Context
        schema_context = self.retriever.retrieve_schema_context(question)
        clarification_rules = self.retriever.retrieve_clarification_rules(question)
        examples = self.retriever.retrieve_query_examples(question)

        # 2. Analyze Question & Decide Clarification
        # We combine analysis and decision in one LLM call for efficiency in MVP
        analysis = self._analyze_and_decide(
            question, 
            state["clarification_answers"], 
            schema_context, 
            clarification_rules
        )

        if analysis.get("type") == "clarification":
            state["mode"] = "awaiting_clarification"
            state["pending_clarification"] = analysis
            return {
                "type": "clarification",
                "question": analysis["question"],
                "options": analysis.get("options", []),
                "state": state,
            }

        # 3. Generate SQL
        sql_result = self._generate_sql(
            question,
            state["clarification_answers"],
            schema_context,
            examples,
            analysis.get("intent_summary", "")
        )

        # 4. Validate SQL
        validation = self.validator.validate(sql_result["sql"])
        if not validation["valid"]:
            return {
                "type": "error",
                "message": "SQL 검증에 실패했습니다.",
                "errors": validation["errors"],
                "state": state
            }

        # 5. Execute SQL
        result_str = run_read_only_sql(validation["sql"])

        # 6. Format Answer
        answer = self._format_answer(
            question,
            validation["sql"],
            result_str,
            sql_result.get("assumptions", [])
        )

        return {
            "type": "answer",
            "answer": answer,
            "sql": validation["sql"],
            "state": state,
        }

    def _handle_clarification_answer(self, answer: str, state: dict) -> dict:
        pending = state.get("pending_clarification")
        if not pending:
            return state

        slot = pending["slot"]
        options = pending.get("options", [])
        
        # Normalize the answer using LLM
        if options:
            normalized_answer = self._normalize_answer(answer, options)
        else:
            normalized_answer = answer

        state["clarification_answers"][slot] = normalized_answer
        state["pending_clarification"] = None
        state["mode"] = "ready"
        return state

    def _normalize_answer(self, user_answer: str, options: list[str]) -> str:
        """Normalize user's natural language answer to one of the options."""
        prompt = f"""
사용자의 답변을 주어진 선택지 중 하나로 변환하세요.

사용자 답변: {user_answer}
선택지: {", ".join(options)}

가장 적절한 선택지를 텍스트로만 응답하세요. 만약 일치하는 것이 없다면 사용자 답변을 그대로 반환하세요.
"""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content.strip()

    def _analyze_and_decide(self, question: str, answers: dict, schema: dict, rules: list[dict]) -> dict:
        """Analyze question and decide if clarification is needed."""
        prompt = f"""
당신은 NL2SQL 에이전트의 판단 모듈입니다. 사용자의 질문을 분석하여 즉시 SQL을 생성할지, 아니면 추가 정보(명료화)를 요청할지 결정하세요.

사용자 질문: {question}
이미 수집된 추가 정보(slot: value): {json.dumps(answers, ensure_ascii=False)}

스키마 정보:
{json.dumps(schema, ensure_ascii=False, indent=2)}

적용 가능한 명료화 규칙 목록:
{json.dumps(rules, ensure_ascii=False, indent=2)}

[판단 지침]
1. '적용 가능한 명료화 규칙'을 하나씩 검토하세요.
2. 질문에 규칙의 'trigger_keywords'가 포함되어 있는지 확인하세요.
3. 해당 규칙의 'missing_slot'이 '이미 수집된 추가 정보'에 아직 없다면, 그 정보를 먼저 물어봐야 합니다 ("type": "clarification").
4. '이미 수집된 추가 정보'에 이미 있는 슬롯은 절대 다시 물어보지 마세요.
5. 모든 필수 모호성(규칙에 해당하고 질문에 포함된 키워드)이 해소되었다면 "type": "sql"로 응답하세요.
6. 명료화 질문은 한 번에 하나씩만 'missing_slot' 이름을 정확히 사용하여 요청하세요.

응답 형식 (JSON):
{{
  "type": "sql" | "clarification",
  "intent_summary": "수집된 정보를 포함하여 최종적으로 파악된 사용자의 상세 의도",
  "question": "사용자에게 던질 명료화 질문 (clarification인 경우)",
  "slot": "명료화 규칙의 'missing_slot' 필드에 정의된 이름 (clarification인 경우)",
  "options": ["해당 규칙의 options 목록"]
}}
"""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)

    def _generate_sql(self, question: str, answers: dict, schema: dict, examples: list[dict], intent: str) -> dict:
        """Generate SQL query."""
        examples_str = "\n\n".join([
            f"질문: {ex['original_question']}\n해결된 의도: {ex['resolved_question']}\nSQL: {ex['sql']}"
            for ex in examples
        ])

        prompt = f"""
당신은 PostgreSQL 전문가입니다. 다음 요청에 대해 최적의 SELECT 쿼리를 작성하세요.

원본 질문: {question}
의도 요약: {intent}
확정된 상세 정보: {json.dumps(answers, ensure_ascii=False)}

[데이터베이스 스키마]
{json.dumps(schema, ensure_ascii=False, indent=2)}

[참고 예시]
{examples_str}

[작성 규칙]
1. 반드시 SELECT 쿼리만 작성하세요.
2. '확정된 상세 정보'에 있는 값을 조건(WHERE 절 등)에 반드시 반영하세요.
3. 스키마에 정의된 테이블과 컬럼만 사용하세요.
4. 결과가 명확하지 않은 경우 가장 합리적인 가정을 세우고 'assumptions'에 기록하세요.

응답 형식 (JSON):
{{
  "sql": "SELECT ...",
  "assumptions": ["전체 기간 기준으로 조회했습니다.", "참여율은 활동 시작 기준으로 계산했습니다."]
}}
"""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)

    def _format_answer(self, question: str, sql: str, result_str: str, assumptions: list[str]) -> str:
        """Format the final answer for the user."""
        prompt = f"""
사용자 질문: {question}
실행한 SQL: {sql}
실행 결과:
{result_str}
가정 사항: {", ".join(assumptions)}

위 결과를 바탕으로 사용자에게 친절하고 요약된 답변을 제공하세요.
결과 표가 포함되어야 합니다. (Markdown table 형식)

응답 예시:
3학년 2반에서 퀴즈를 제출하지 않은 학생은 총 3명입니다.

| 학생 | 활동 | 상태 |
| --- | --- | --- |
| 최수아 | 상태 변화 퀴즈 | assigned |
...

사용한 SQL:
```sql
SELECT ...
```
"""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
