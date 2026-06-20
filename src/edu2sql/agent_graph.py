import json
from typing import Any, Literal, Optional, TypedDict

from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph, START
from pydantic import BaseModel, Field

from .db import run_read_only_sql
from .retriever import Retriever
from .sql_validator import SQLValidator


# 1. State Definition
class AgentState(TypedDict):
    # Inputs
    original_question: str
    clarification_answers: dict[str, str]
    
    # Internal State
    pending_clarification: Optional[dict[str, Any]]
    schema_context: dict[str, Any]
    examples: list[dict[str, Any]]
    intent_summary: str
    
    # Outputs
    sql: Optional[str]
    assumptions: list[str]
    result: Optional[str]
    answer: Optional[str]
    errors: list[str]


# 2. Structured Output Schemas
class AnalysisResult(BaseModel):
    type: Literal["sql", "clarification"] = Field(description="Whether to proceed with SQL generation or ask for clarification")
    intent_summary: str = Field(description="A concise summary of the user's intent after considering all provided information")
    question: Optional[str] = Field(None, description="The clarification question to ask the user (if type is 'clarification')")
    slot: Optional[str] = Field(None, description="The name of the missing information slot (if type is 'clarification')")
    options: Optional[list[str]] = Field(None, description="Options for the clarification question")

class SQLResult(BaseModel):
    sql: str = Field(description="The generated PostgreSQL SELECT query")
    assumptions: list[str] = Field(default_factory=list, description="Any assumptions made while generating the query")

class NormalizationResult(BaseModel):
    normalized_answer: str = Field(description="The normalized version of the user's answer based on options")


# 3. Agent Class
class NL2SQLGraphAgent:
    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.retriever = Retriever()
        self.validator = SQLValidator()
        self.llm = ChatOpenAI(
            model=config.get("llm", {}).get("model", "gpt-4o"),
            temperature=0.0
        )
        self.graph = self._build_graph()

    def _build_graph(self):
        builder = StateGraph(AgentState)

        # Define nodes
        builder.add_node("retrieve_and_analyze", self.retrieve_and_analyze_node)
        builder.add_node("generate_sql", self.generate_sql_node)
        builder.add_node("execute_query", self.execute_query_node)
        builder.add_node("format_answer", self.format_answer_node)

        # Define edges
        builder.add_edge(START, "retrieve_and_analyze")
        
        # Conditional edge from analyze
        builder.add_conditional_edges(
            "retrieve_and_analyze",
            self._should_clarify,
            {
                "clarify": END,
                "proceed": "generate_sql"
            }
        )
        
        builder.add_edge("generate_sql", "execute_query")
        builder.add_edge("execute_query", "format_answer")
        builder.add_edge("format_answer", END)

        return builder.compile()

    # --- Node Implementations ---

    def retrieve_and_analyze_node(self, state: AgentState) -> dict[str, Any]:
        """Node 1: Retrieve context and decide whether to clarify or proceed."""
        question = state["original_question"]
        answers = state["clarification_answers"]

        # Retrieve Context
        schema_context = self.retriever.retrieve_schema_context(question)
        clarification_rules = self.retriever.retrieve_clarification_rules(question)
        examples = self.retriever.retrieve_query_examples(question)

        # Analyze and Decide
        analyzer = self.llm.with_structured_output(AnalysisResult)
        
        prompt = f"""
당신은 NL2SQL 에이전트의 판단 모듈입니다. 사용자의 질문을 분석하여 즉시 SQL을 생성할지, 아니면 추가 정보(명료화)를 요청할지 결정하세요.

사용자 질문: {question}
이미 수집된 추가 정보(slot: value): {json.dumps(answers, ensure_ascii=False)}

스키마 정보:
{json.dumps(schema_context, ensure_ascii=False, indent=2)}

적용 가능한 명료화 규칙 목록:
{json.dumps(clarification_rules, ensure_ascii=False, indent=2)}

[판단 지침]
1. '적용 가능한 명료화 규칙'을 하나씩 검토하세요.
2. 질문에 규칙의 'trigger_keywords'가 포함되어 있는지 확인하세요.
3. 해당 규칙의 'missing_slot'이 '이미 수집된 추가 정보'에 아직 없다면, 그 정보를 먼저 물어봐야 합니다 ("type": "clarification").
4. '이미 수집된 추가 정보'에 이미 있는 슬롯은 절대 다시 물어보지 마세요.
5. 모든 필수 모호성(규칙에 해당하고 질문에 포함된 키워드)이 해소되었다면 "type": "sql"로 응답하세요.
6. 명료화 질문은 한 번에 하나씩만 'missing_slot' 이름을 정확히 사용하여 요청하세요.
"""
        analysis = analyzer.invoke(prompt)

        return {
            "schema_context": schema_context,
            "examples": examples,
            "intent_summary": analysis.intent_summary,
            "pending_clarification": analysis.dict() if analysis.type == "clarification" else None,
            "errors": []
        }

    def generate_sql_node(self, state: AgentState) -> dict[str, Any]:
        """Node 2: Generate SQL based on the refined intent and context."""
        question = state["original_question"]
        answers = state["clarification_answers"]
        intent = state["intent_summary"]
        schema = state["schema_context"]
        examples = state["examples"]

        generator = self.llm.with_structured_output(SQLResult)

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
"""
        sql_output = generator.invoke(prompt)

        return {
            "sql": sql_output.sql,
            "assumptions": sql_output.assumptions
        }

    def execute_query_node(self, state: AgentState) -> dict[str, Any]:
        """Node 3: Validate and execute the generated SQL."""
        sql = state["sql"]
        if not sql:
            return {"errors": ["No SQL generated."]}

        validation = self.validator.validate(sql)
        if not validation["valid"]:
            return {"errors": validation["errors"]}

        result_str = run_read_only_sql(validation["sql"])
        return {
            "sql": validation["sql"],
            "result": result_str
        }

    def format_answer_node(self, state: AgentState) -> dict[str, Any]:
        """Node 4: Format the final response for the user."""
        question = state["original_question"]
        sql = state["sql"]
        result_str = state["result"]
        assumptions = state["assumptions"]

        prompt = f"""
사용자 질문: {question}
실행한 SQL: {sql}
실행 결과:
{result_str}
가정 사항: {", ".join(assumptions)}

위 결과를 바탕으로 사용자에게 친절하고 요약된 답변을 제공하세요.
결과 표가 포함되어야 합니다. (Markdown table 형식)
"""
        response = self.llm.invoke(prompt)
        return {"answer": response.content}

    # --- Helper Methods ---

    def _should_clarify(self, state: AgentState) -> Literal["clarify", "proceed"]:
        if state["pending_clarification"]:
            return "clarify"
        return "proceed"

    def _normalize_answer(self, user_answer: str, options: list[str]) -> str:
        """Normalize user's natural language answer to one of the options."""
        normalizer = self.llm.with_structured_output(NormalizationResult)
        prompt = f"""
사용자의 답변을 주어진 선택지 중 하나로 변환하세요.

사용자 답변: {user_answer}
선택지: {", ".join(options)}

가장 적절한 선택지를 반환하세요. 만약 일치하는 것이 전혀 없다면 사용자 답변을 최대한 가공하지 않고 반환하세요.
"""
        result = normalizer.invoke(prompt)
        return result.normalized_answer

    def answer_question(self, question: str, state_input: dict | None = None) -> dict:
        """Entry point for the graph agent."""
        if state_input and state_input.get("pending_clarification"):
            # Handle clarification answer
            pending = state_input["pending_clarification"]
            slot = pending["slot"]
            options = pending.get("options", [])
            
            normalized = self._normalize_answer(question, options)
            
            # Update state with the new answer
            clarification_answers = state_input.get("clarification_answers", {})
            clarification_answers[slot] = normalized
            
            # Resume from the original question
            initial_state = {
                "original_question": state_input["original_question"],
                "clarification_answers": clarification_answers,
                "pending_clarification": None,
                "schema_context": {},
                "examples": [],
                "intent_summary": "",
                "sql": None,
                "assumptions": [],
                "result": None,
                "answer": None,
                "errors": []
            }
        else:
            # Initial question
            initial_state = {
                "original_question": question,
                "clarification_answers": {},
                "pending_clarification": None,
                "schema_context": {},
                "examples": [],
                "intent_summary": "",
                "sql": None,
                "assumptions": [],
                "result": None,
                "answer": None,
                "errors": []
            }

        final_state = self.graph.invoke(initial_state)
        
        if final_state.get("pending_clarification"):
            return {
                "type": "clarification",
                "question": final_state["pending_clarification"]["question"],
                "options": final_state["pending_clarification"].get("options"),
                "state": final_state
            }
        
        if final_state.get("errors"):
            return {
                "type": "error",
                "message": "처리에 실패했습니다.",
                "errors": final_state["errors"],
                "state": final_state
            }

        return {
            "type": "answer",
            "answer": final_state["answer"],
            "sql": final_state["sql"],
            "state": final_state
        }
