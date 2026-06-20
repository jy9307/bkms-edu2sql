from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from edu2sql.agent_graph import NL2SQLGraphAgent
from edu2sql.config import load_config
from edu2sql.db import get_connection
from edu2sql.sql_validator import SQLValidator


EXAMPLE_QUESTIONS = [
    "이번 수업에서 애들이 제대로 참여한 편인지 보고 싶어",
    "요즘 유난히 지쳐 보이는 애들이 있어서, 데이터로 이상 신호가 있는지 보고 싶어",
    "우리 반에서 꾸준히 잘 따라오는 애들이 누구인지 보고 싶어",
    "이 글쓰기 활동에서 애들이 얼마나 많이 썼는지 순서대로 보고 싶어",
]


def init_session_state() -> None:
    defaults = {
        "messages": [],
        "agent_state": None,
        "last_trace": None,
        "last_result": None,
        "pending_input": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def data_signature() -> tuple[tuple[str, int], ...]:
    paths = [
        Path("data/clarification_rules.json"),
        Path("data/query_examples.json"),
        Path("data/schema_dictionary.json"),
        Path("config/default.yaml"),
    ]
    return tuple((str(path), path.stat().st_mtime_ns) for path in paths)


@st.cache_resource
def get_agent(signature: tuple[tuple[str, int], ...]) -> NL2SQLGraphAgent:
    _ = signature
    load_dotenv(override=True)
    return NL2SQLGraphAgent(load_config())


def check_db() -> tuple[bool, str]:
    try:
        connection = get_connection(readonly=True)
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database(), current_user;")
            database, user = cursor.fetchone()
        connection.close()
        return True, f"{database} / {user}"
    except Exception as error:
        return False, str(error)


def parse_plain_table(result: str | None) -> pd.DataFrame | None:
    if not result or result.startswith(("ERROR:", "SQL ERROR:", "(")):
        return None

    lines = [line.strip() for line in result.splitlines() if line.strip()]
    if len(lines) < 2 or " | " not in lines[0]:
        return None

    columns = [column.strip() for column in lines[0].split("|")]
    rows: list[list[str]] = []
    for line in lines[2:]:
        if line.startswith("("):
            continue
        values = [value.strip() for value in line.split("|")]
        if len(values) == len(columns):
            rows.append(values)

    if not rows:
        return None
    return pd.DataFrame(rows, columns=columns)


def describe_step(result: dict[str, Any] | None) -> list[tuple[str, str, str]]:
    if not result:
        return [
            ("1. Retrieve", "대기", "질문과 관련된 스키마, 명료화 규칙, 예시 SQL을 찾습니다."),
            ("2. Clarify", "대기", "질문이 모호하면 필요한 기준을 하나씩 물어봅니다."),
            ("3. Generate SQL", "대기", "확정된 의도와 예시를 바탕으로 SELECT SQL을 만듭니다."),
            ("4. Validate/Run", "대기", "쓰기 작업을 막고 read-only 쿼리만 실행합니다."),
            ("5. Answer", "대기", "실행 결과를 교사용 답변으로 정리합니다."),
        ]

    result_type = result.get("type")
    if result_type == "clarification":
        return [
            ("1. Retrieve", "완료", "스키마, 규칙, 예시를 가져왔습니다."),
            ("2. Clarify", "진행 중", "추가 기준이 필요해서 사용자에게 되묻습니다."),
            ("3. Generate SQL", "대기", "명료화 답변을 받은 뒤 진행합니다."),
            ("4. Validate/Run", "대기", "SQL 생성 후 실행됩니다."),
            ("5. Answer", "대기", "DB 결과가 나온 뒤 작성됩니다."),
        ]
    if result_type == "answer":
        return [
            ("1. Retrieve", "완료", "스키마, 규칙, 예시를 가져왔습니다."),
            ("2. Clarify", "완료", "필요한 기준이 확정되었습니다."),
            ("3. Generate SQL", "완료", "SELECT SQL을 생성했습니다."),
            ("4. Validate/Run", "완료", "SQL 검증 후 DB에서 실행했습니다."),
            ("5. Answer", "완료", "실행 결과를 자연어 답변으로 정리했습니다."),
        ]
    return [
        ("1. Retrieve", "확인 필요", "처리 도중 오류가 발생했습니다."),
        ("2. Clarify", "확인 필요", "상태 패널에서 오류를 확인하세요."),
        ("3. Generate SQL", "확인 필요", "상태 패널에서 오류를 확인하세요."),
        ("4. Validate/Run", "확인 필요", "상태 패널에서 오류를 확인하세요."),
        ("5. Answer", "확인 필요", "상태 패널에서 오류를 확인하세요."),
    ]


def run_agent(user_input: str) -> None:
    agent = get_agent(data_signature())
    state_input = st.session_state.agent_state
    result = agent.answer_question(user_input, state_input=state_input)

    st.session_state.last_result = result
    st.session_state.last_trace = result.get("state")
    st.session_state.agent_state = result.get("state") if result.get("type") == "clarification" else None

    st.session_state.messages.append({"role": "user", "content": user_input})

    if result.get("type") == "clarification":
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": result.get("question", "추가 정보가 필요합니다."),
                "options": result.get("options") or [],
            }
        )
    elif result.get("type") == "answer":
        st.session_state.messages.append(
            {"role": "assistant", "content": result.get("answer", "답변을 생성했습니다.")}
        )
    else:
        errors = "\n".join(f"- {error}" for error in result.get("errors", []))
        st.session_state.messages.append(
            {"role": "assistant", "content": f"처리에 실패했습니다.\n{errors}"}
        )


def render_sidebar() -> None:
    st.sidebar.title("Edu2SQL PoC")
    st.sidebar.caption("질문이 SQL로 바뀌는 과정을 보여주는 데모")

    has_key = bool(os.getenv("OPENAI_API_KEY"))
    db_ok, db_message = check_db()

    st.sidebar.subheader("Runtime")
    st.sidebar.write("OpenAI API Key:", "set" if has_key else "missing")
    st.sidebar.write("DB:", "connected" if db_ok else "error")
    st.sidebar.caption(db_message)

    st.sidebar.subheader("Example questions")
    for question in EXAMPLE_QUESTIONS:
        if st.sidebar.button(question, use_container_width=True):
            st.session_state.pending_input = question
            st.rerun()

    if st.sidebar.button("대화 초기화", use_container_width=True):
        st.session_state.messages = []
        st.session_state.agent_state = None
        st.session_state.last_trace = None
        st.session_state.last_result = None
        st.session_state.pending_input = None
        st.rerun()


def render_chat() -> None:
    st.header("Question to SQL")

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            for option in message.get("options", []):
                if st.button(option, key=f"option-{len(st.session_state.messages)}-{option}"):
                    st.session_state.pending_input = option
                    st.rerun()

    prompt = st.chat_input("교사 질문을 입력하세요")
    if prompt:
        st.session_state.pending_input = prompt
        st.rerun()


def render_trace() -> None:
    result = st.session_state.last_result
    trace = st.session_state.last_trace or {}

    st.header("How it works")
    steps = describe_step(result)
    columns = st.columns(len(steps))
    for column, (title, status, description) in zip(columns, steps):
        with column:
            st.metric(title, status)
            st.caption(description)

    original_question = trace.get("original_question")
    if original_question:
        agent = get_agent(data_signature())
        rules = agent.retriever.retrieve_clarification_rules(original_question)
    else:
        rules = []

    tab_context, tab_sql, tab_result, tab_state = st.tabs(
        ["Retrieved context", "SQL path", "DB result", "State"]
    )

    with tab_context:
        st.subheader("Intent")
        st.write(trace.get("intent_summary") or "아직 분석 결과가 없습니다.")

        st.subheader("Clarification")
        pending = trace.get("pending_clarification")
        answers = trace.get("clarification_answers") or {}
        if pending:
            st.info(pending.get("question", "추가 질문이 필요합니다."))
            st.write("slot:", pending.get("slot"))
            st.write("options:", pending.get("options") or [])
        elif answers:
            st.success("명료화 답변이 반영되었습니다.")
            st.json(answers)
        else:
            st.caption("아직 명료화가 발생하지 않았거나, 질문이 충분히 명확합니다.")

        st.subheader("Matched rules")
        st.json(rules)

        st.subheader("Few-shot examples")
        st.json(trace.get("examples") or [])

    with tab_sql:
        sql = trace.get("sql")
        assumptions = trace.get("assumptions") or []
        validation = SQLValidator().validate(sql) if sql else None

        st.subheader("Generated SQL")
        if sql:
            st.code(sql, language="sql")
        else:
            st.caption("명료화가 끝나면 SQL이 생성됩니다.")

        st.subheader("Validation")
        if validation:
            st.json(validation)
        else:
            st.caption("아직 검증할 SQL이 없습니다.")

        st.subheader("Assumptions")
        if assumptions:
            for assumption in assumptions:
                st.write("-", assumption)
        else:
            st.caption("기록된 가정이 없습니다.")

    with tab_result:
        result_text = trace.get("result")
        dataframe = parse_plain_table(result_text)
        if dataframe is not None:
            st.dataframe(dataframe, use_container_width=True, hide_index=True)
        elif result_text:
            st.code(result_text)
        else:
            st.caption("SQL 실행 후 결과가 표시됩니다.")

        if result and result.get("type") == "answer":
            st.subheader("Final answer")
            st.markdown(result.get("answer", ""))

        if result and result.get("type") == "error":
            st.error(result.get("message", "처리에 실패했습니다."))
            st.json(result.get("errors", []))

    with tab_state:
        st.caption("PoC 설명용 원본 상태입니다. 민감 정보는 포함하지 않습니다.")
        st.json(trace or {})


def main() -> None:
    st.set_page_config(page_title="Edu2SQL PoC", layout="wide")
    load_dotenv(override=True)
    init_session_state()
    render_sidebar()

    pending_input = st.session_state.pending_input
    if pending_input:
        st.session_state.pending_input = None
        with st.spinner("에이전트가 질문을 분석하고 있습니다..."):
            run_agent(pending_input)
        st.rerun()

    left, right = st.columns([0.9, 1.1], gap="large")
    with left:
        render_chat()
    with right:
        render_trace()


if __name__ == "__main__":
    main()
