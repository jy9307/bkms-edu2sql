#!/usr/bin/env python3
"""Create and seed the Edu2SQL PoC PostgreSQL schema."""

from __future__ import annotations

import argparse
import os
from datetime import date
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import Json


TABLES = [
    "users",
    "sessions",
    "activities",
    "activity_runs",
    "submissions",
    "activity_logs",
    "access_logs",
    "quiz_answers",
    "discussion_posts",
    "writing_submissions",
]

NAMESPACE = UUID("4e3c149f-6b26-4cf6-9d4c-8b9f3da28e52")


def stable_uuid(name: str) -> str:
    return str(uuid5(NAMESPACE, f"edu2sql-poc:{name}"))


def connect():
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set in .env")
    connection = psycopg2.connect(database_url)
    connection.set_session(readonly=False, autocommit=False)
    return connection


def reset_schema(cursor) -> None:
    for table in reversed(TABLES):
        cursor.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")

    cursor.execute(
        """
        CREATE TABLE users (
            user_id uuid PRIMARY KEY,
            login_id varchar(80) NOT NULL UNIQUE,
            email varchar(255) NOT NULL UNIQUE,
            name varchar(80) NOT NULL,
            role varchar(20) NOT NULL CHECK (role IN ('student', 'teacher', 'admin')),
            school_year int,
            grade int,
            class_number int,
            created_at timestamptz NOT NULL,
            last_login_at timestamptz
        );

        CREATE TABLE sessions (
            session_id uuid PRIMARY KEY,
            teacher_id uuid NOT NULL REFERENCES users(user_id),
            school_year int NOT NULL,
            grade int NOT NULL,
            class_number int NOT NULL,
            subject varchar(80) NOT NULL,
            unit_name varchar(160) NOT NULL,
            title varchar(200) NOT NULL,
            session_date date NOT NULL,
            period int NOT NULL,
            started_at timestamptz,
            ended_at timestamptz,
            status varchar(20) NOT NULL CHECK (status IN ('scheduled', 'live', 'ended', 'cancelled')),
            created_at timestamptz NOT NULL
        );

        CREATE TABLE activities (
            activity_id uuid PRIMARY KEY,
            creator_id uuid NOT NULL REFERENCES users(user_id),
            activity_type varchar(40) NOT NULL CHECK (
                activity_type IN ('reading', 'quiz', 'writing', 'discussion', 'ai_writing', 'external_page')
            ),
            title varchar(200) NOT NULL,
            description text,
            material_title varchar(200),
            material_url text,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL
        );

        CREATE TABLE activity_runs (
            run_id uuid PRIMARY KEY,
            activity_id uuid NOT NULL REFERENCES activities(activity_id),
            session_id uuid NOT NULL REFERENCES sessions(session_id),
            assigned_by uuid NOT NULL REFERENCES users(user_id),
            started_at timestamptz,
            ended_at timestamptz,
            status varchar(20) NOT NULL CHECK (status IN ('ready', 'running', 'closed')),
            display_order int NOT NULL
        );

        CREATE TABLE submissions (
            submission_id uuid PRIMARY KEY,
            run_id uuid NOT NULL REFERENCES activity_runs(run_id),
            student_id uuid NOT NULL REFERENCES users(user_id),
            status varchar(20) NOT NULL CHECK (status IN ('assigned', 'in_progress', 'submitted', 'returned', 'retry')),
            attempt_no int NOT NULL DEFAULT 1,
            content jsonb NOT NULL DEFAULT '{}'::jsonb,
            score numeric(5,2),
            feedback text,
            started_at timestamptz,
            submitted_at timestamptz,
            updated_at timestamptz NOT NULL,
            UNIQUE (run_id, student_id, attempt_no)
        );

        CREATE TABLE activity_logs (
            log_id uuid PRIMARY KEY,
            run_id uuid NOT NULL REFERENCES activity_runs(run_id),
            user_id uuid NOT NULL REFERENCES users(user_id),
            event_type varchar(80) NOT NULL,
            section varchar(80),
            target_type varchar(80),
            target_id varchar(120),
            value_text text,
            value_number numeric,
            duration_ms int,
            payload jsonb NOT NULL DEFAULT '{}'::jsonb,
            occurred_at timestamptz NOT NULL,
            created_at timestamptz NOT NULL
        );

        CREATE TABLE access_logs (
            access_log_id uuid PRIMARY KEY,
            user_id uuid NOT NULL REFERENCES users(user_id),
            session_id uuid REFERENCES sessions(session_id),
            action varchar(40) NOT NULL CHECK (
                action IN ('login', 'logout', 'join_session', 'leave_session', 'navigate', 'open_material')
            ),
            page_path text,
            ip_address varchar(80),
            user_agent text,
            device_type varchar(40),
            occurred_at timestamptz NOT NULL
        );

        CREATE TABLE quiz_answers (
            answer_id uuid PRIMARY KEY,
            run_id uuid NOT NULL REFERENCES activity_runs(run_id),
            student_id uuid NOT NULL REFERENCES users(user_id),
            submission_id uuid NOT NULL REFERENCES submissions(submission_id),
            question_no int NOT NULL,
            question_text text NOT NULL,
            selected_answer text,
            correct_answer text NOT NULL,
            is_correct boolean NOT NULL,
            answered_at timestamptz NOT NULL
        );

        CREATE TABLE discussion_posts (
            post_id uuid PRIMARY KEY,
            run_id uuid NOT NULL REFERENCES activity_runs(run_id),
            author_id uuid NOT NULL REFERENCES users(user_id),
            parent_post_id uuid REFERENCES discussion_posts(post_id),
            space_name varchar(80) NOT NULL,
            body text NOT NULL,
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL
        );

        CREATE TABLE writing_submissions (
            writing_submission_id uuid PRIMARY KEY,
            run_id uuid NOT NULL REFERENCES activity_runs(run_id),
            student_id uuid NOT NULL REFERENCES users(user_id),
            submission_id uuid NOT NULL REFERENCES submissions(submission_id),
            title text NOT NULL,
            body text NOT NULL,
            char_count int NOT NULL,
            revision_no int NOT NULL,
            submitted_at timestamptz NOT NULL,
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL
        );

        CREATE INDEX idx_users_class ON users(role, school_year, grade, class_number);
        CREATE INDEX idx_sessions_class_date ON sessions(school_year, grade, class_number, session_date);
        CREATE INDEX idx_activities_type ON activities(activity_type);
        CREATE INDEX idx_activity_runs_session ON activity_runs(session_id);
        CREATE INDEX idx_submissions_run_status ON submissions(run_id, status);
        CREATE INDEX idx_activity_logs_run_event ON activity_logs(run_id, event_type);
        CREATE INDEX idx_access_logs_session_action ON access_logs(session_id, action);
        CREATE INDEX idx_writing_submissions_submitted_at ON writing_submissions(submitted_at);
        """
    )


def insert_many(cursor, sql: str, rows: list[tuple[Any, ...]]) -> None:
    cursor.executemany(sql, rows)


def seed_data(cursor) -> None:
    teacher_id = stable_uuid("teacher-kim")
    admin_id = stable_uuid("admin-main")

    main_students = [
        ("s30201", "김도윤"),
        ("s30202", "이서윤"),
        ("s30203", "박지호"),
        ("s30204", "최하준"),
        ("s30205", "정하은"),
        ("s30206", "강민서"),
        ("s30207", "조서준"),
        ("s30208", "윤지유"),
        ("s30209", "임도현"),
        ("s30210", "한서아"),
        ("s30211", "오지훈"),
        ("s30212", "신예린"),
    ]
    comparison_students = [
        ("s30101", "서민재", 1),
        ("s30102", "권유준", 1),
        ("s30301", "황채원", 3),
    ]

    users = [
        (
            teacher_id,
            "t-kim",
            "teacher.kim@example.school",
            "김민준",
            "teacher",
            None,
            None,
            None,
            "2026-02-20T09:00:00+09:00",
            "2026-06-17T08:15:00+09:00",
        ),
        (
            admin_id,
            "admin-main",
            "admin@example.school",
            "관리자",
            "admin",
            None,
            None,
            None,
            "2026-02-01T09:00:00+09:00",
            "2026-06-16T17:10:00+09:00",
        ),
    ]
    for login_id, name in main_students:
        users.append(
            (
                stable_uuid(login_id),
                login_id,
                f"{login_id}@example.school",
                name,
                "student",
                2026,
                3,
                2,
                "2026-03-02T08:30:00+09:00",
                f"2026-06-{15 + (int(login_id[-2:]) % 3):02d}T08:{20 + int(login_id[-2:]):02d}:00+09:00",
            )
        )
    for login_id, name, class_number in comparison_students:
        users.append(
            (
                stable_uuid(login_id),
                login_id,
                f"{login_id}@example.school",
                name,
                "student",
                2026,
                3,
                class_number,
                "2026-03-02T08:30:00+09:00",
                "2026-06-16T08:25:00+09:00",
            )
        )

    insert_many(
        cursor,
        """
        INSERT INTO users (
            user_id, login_id, email, name, role, school_year, grade, class_number, created_at, last_login_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """,
        users,
    )

    sessions = [
        (
            stable_uuid("session-science-water"),
            teacher_id,
            2026,
            3,
            2,
            "과학",
            "물의 순환",
            "물의 순환 읽기와 퀴즈",
            date(2026, 6, 12),
            2,
            "2026-06-12T09:50:00+09:00",
            "2026-06-12T10:35:00+09:00",
            "ended",
            "2026-05-30T14:00:00+09:00",
        ),
        (
            stable_uuid("session-science-climate"),
            teacher_id,
            2026,
            3,
            2,
            "과학",
            "기후와 생활",
            "기후 변화 토론과 AI 글쓰기",
            date(2026, 6, 16),
            3,
            "2026-06-16T10:45:00+09:00",
            "2026-06-16T11:30:00+09:00",
            "ended",
            "2026-06-10T15:00:00+09:00",
        ),
        (
            stable_uuid("session-korean-opinion"),
            teacher_id,
            2026,
            3,
            2,
            "국어",
            "의견을 담은 글",
            "우리 동네 문제 글쓰기",
            date(2026, 6, 13),
            1,
            "2026-06-13T09:00:00+09:00",
            "2026-06-13T09:45:00+09:00",
            "ended",
            "2026-05-31T11:00:00+09:00",
        ),
        (
            stable_uuid("session-science-may"),
            teacher_id,
            2026,
            3,
            2,
            "과학",
            "생물의 한살이",
            "배추흰나비 관찰 정리",
            date(2026, 5, 24),
            4,
            "2026-05-24T11:40:00+09:00",
            "2026-05-24T12:25:00+09:00",
            "ended",
            "2026-05-20T10:00:00+09:00",
        ),
        (
            stable_uuid("session-science-other-class"),
            teacher_id,
            2026,
            3,
            1,
            "과학",
            "물의 순환",
            "3학년 1반 물의 순환 퀴즈",
            date(2026, 6, 12),
            5,
            "2026-06-12T13:20:00+09:00",
            "2026-06-12T14:05:00+09:00",
            "ended",
            "2026-05-30T14:30:00+09:00",
        ),
    ]
    insert_many(
        cursor,
        """
        INSERT INTO sessions (
            session_id, teacher_id, school_year, grade, class_number, subject, unit_name, title,
            session_date, period, started_at, ended_at, status, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """,
        sessions,
    )

    activities = [
        (
            stable_uuid("activity-reading-water"),
            teacher_id,
            "reading",
            "물의 순환 읽기",
            "물의 상태 변화와 순환 과정을 읽고 핵심 내용을 정리한다.",
            "물은 어디에서 와서 어디로 갈까?",
            "https://example.school/materials/water-cycle",
            Json({"pages": 4, "level": "grade3"}),
            "2026-05-30T14:10:00+09:00",
        ),
        (
            stable_uuid("activity-quiz-water"),
            teacher_id,
            "quiz",
            "물의 순환 퀴즈",
            "증발, 응결, 강수 개념을 확인하는 5문항 퀴즈.",
            "물의 순환 확인 문제",
            "https://example.school/materials/water-quiz",
            Json({"question_count": 5, "max_score": 100}),
            "2026-05-30T14:20:00+09:00",
        ),
        (
            stable_uuid("activity-writing-water"),
            teacher_id,
            "writing",
            "물 절약 설명문 쓰기",
            "물의 순환을 바탕으로 물 절약 방법을 설명문으로 작성한다.",
            "물 절약 글쓰기 안내",
            "https://example.school/materials/water-writing",
            Json({"rubric": ["내용", "구성", "표현"]}),
            "2026-05-31T09:20:00+09:00",
        ),
        (
            stable_uuid("activity-discussion-climate"),
            teacher_id,
            "discussion",
            "기후 변화 토론",
            "기후 변화가 생활에 미치는 영향을 찬반 공간에서 토론한다.",
            "기후 변화 토론 자료",
            "https://example.school/materials/climate-discussion",
            Json({"spaces": ["찬성", "반대", "질문"]}),
            "2026-06-10T15:15:00+09:00",
        ),
        (
            stable_uuid("activity-ai-writing-climate"),
            teacher_id,
            "ai_writing",
            "기후 변화 해결 제안 AI 글쓰기",
            "AI 피드백을 참고해 기후 변화 해결 제안문을 작성한다.",
            "제안문 쓰기 가이드",
            "https://example.school/materials/climate-ai-writing",
            Json({"ai_feedback": True}),
            "2026-06-10T15:25:00+09:00",
        ),
        (
            stable_uuid("activity-writing-korean"),
            teacher_id,
            "writing",
            "우리 동네 문제 의견문",
            "동네 문제를 찾고 해결 의견을 글로 쓴다.",
            "의견문 예시",
            "https://example.school/materials/opinion-writing",
            Json({"genre": "opinion"}),
            "2026-05-31T11:10:00+09:00",
        ),
        (
            stable_uuid("activity-reading-butterfly"),
            teacher_id,
            "reading",
            "배추흰나비 한살이 읽기",
            "배추흰나비의 알, 애벌레, 번데기, 어른벌레 단계를 읽고 관찰 내용을 정리한다.",
            "배추흰나비 관찰 기록",
            "https://example.school/materials/butterfly-reading",
            Json({"pages": 3, "level": "grade3"}),
            "2026-05-20T10:10:00+09:00",
        ),
        (
            stable_uuid("activity-quiz-butterfly"),
            teacher_id,
            "quiz",
            "배추흰나비 한살이 퀴즈",
            "배추흰나비의 성장 단계와 특징을 확인하는 5문항 퀴즈.",
            "배추흰나비 확인 문제",
            "https://example.school/materials/butterfly-quiz",
            Json({"question_count": 5, "max_score": 100}),
            "2026-05-20T10:20:00+09:00",
        ),
    ]
    insert_many(
        cursor,
        """
        INSERT INTO activities (
            activity_id, creator_id, activity_type, title, description, material_title, material_url, metadata, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
        """,
        activities,
    )

    run_keys = {
        "reading": "run-reading-water",
        "quiz": "run-quiz-water",
        "writing": "run-writing-water",
        "discussion": "run-discussion-climate",
        "ai_writing": "run-ai-writing-climate",
        "korean_writing": "run-writing-korean",
        "may_reading": "run-reading-butterfly",
        "may_quiz": "run-quiz-butterfly",
        "other_quiz": "run-quiz-other-class",
    }
    activity_runs = [
        (
            stable_uuid(run_keys["reading"]),
            stable_uuid("activity-reading-water"),
            stable_uuid("session-science-water"),
            teacher_id,
            "2026-06-12T09:55:00+09:00",
            "2026-06-12T10:08:00+09:00",
            "closed",
            1,
        ),
        (
            stable_uuid(run_keys["quiz"]),
            stable_uuid("activity-quiz-water"),
            stable_uuid("session-science-water"),
            teacher_id,
            "2026-06-12T10:10:00+09:00",
            "2026-06-12T10:32:00+09:00",
            "closed",
            2,
        ),
        (
            stable_uuid(run_keys["writing"]),
            stable_uuid("activity-writing-water"),
            stable_uuid("session-science-water"),
            teacher_id,
            "2026-06-12T10:32:00+09:00",
            "2026-06-12T10:35:00+09:00",
            "closed",
            3,
        ),
        (
            stable_uuid(run_keys["discussion"]),
            stable_uuid("activity-discussion-climate"),
            stable_uuid("session-science-climate"),
            teacher_id,
            "2026-06-16T10:50:00+09:00",
            "2026-06-16T11:08:00+09:00",
            "closed",
            1,
        ),
        (
            stable_uuid(run_keys["ai_writing"]),
            stable_uuid("activity-ai-writing-climate"),
            stable_uuid("session-science-climate"),
            teacher_id,
            "2026-06-16T11:08:00+09:00",
            "2026-06-16T11:28:00+09:00",
            "closed",
            2,
        ),
        (
            stable_uuid(run_keys["korean_writing"]),
            stable_uuid("activity-writing-korean"),
            stable_uuid("session-korean-opinion"),
            teacher_id,
            "2026-06-13T09:05:00+09:00",
            "2026-06-13T09:42:00+09:00",
            "closed",
            1,
        ),
        (
            stable_uuid(run_keys["may_reading"]),
            stable_uuid("activity-reading-butterfly"),
            stable_uuid("session-science-may"),
            teacher_id,
            "2026-05-24T11:45:00+09:00",
            "2026-05-24T11:58:00+09:00",
            "closed",
            1,
        ),
        (
            stable_uuid(run_keys["may_quiz"]),
            stable_uuid("activity-quiz-butterfly"),
            stable_uuid("session-science-may"),
            teacher_id,
            "2026-05-24T11:58:00+09:00",
            "2026-05-24T12:22:00+09:00",
            "closed",
            2,
        ),
        (
            stable_uuid(run_keys["other_quiz"]),
            stable_uuid("activity-quiz-water"),
            stable_uuid("session-science-other-class"),
            teacher_id,
            "2026-06-12T13:25:00+09:00",
            "2026-06-12T13:48:00+09:00",
            "closed",
            1,
        ),
    ]
    insert_many(
        cursor,
        """
        INSERT INTO activity_runs (
            run_id, activity_id, session_id, assigned_by, started_at, ended_at, status, display_order
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
        """,
        activity_runs,
    )

    submissions: list[tuple[Any, ...]] = []
    submission_ids: dict[tuple[str, str], str] = {}

    def add_submission(
        run_key: str,
        student_login: str,
        status: str,
        score: float | None,
        started_at: str | None,
        submitted_at: str | None,
        attempt_no: int = 1,
        feedback: str | None = None,
    ) -> str:
        submission_id = stable_uuid(f"submission-{run_key}-{student_login}-{attempt_no}")
        submission_ids[(run_key, student_login)] = submission_id
        submissions.append(
            (
                submission_id,
                stable_uuid(run_key),
                stable_uuid(student_login),
                status,
                attempt_no,
                Json({"source": "poc_seed"}),
                score,
                feedback,
                started_at,
                submitted_at,
                submitted_at or started_at or "2026-06-17T08:00:00+09:00",
            )
        )
        return submission_id

    quiz_statuses = {
        "s30201": ("submitted", 95),
        "s30202": ("submitted", 88),
        "s30203": ("assigned", None),
        "s30204": ("submitted", 76),
        "s30205": ("submitted", 91),
        "s30206": ("in_progress", None),
        "s30207": ("submitted", 82),
        "s30208": ("submitted", 67),
        "s30209": ("submitted", 100),
        "s30210": ("retry", 54),
        "s30211": ("submitted", 73),
        "s30212": ("assigned", None),
    }
    for index, (student_login, _name) in enumerate(main_students, start=1):
        status, score = quiz_statuses[student_login]
        started_at = f"2026-06-12T10:{9 + index:02d}:00+09:00" if status != "assigned" else None
        submitted_at = f"2026-06-12T10:{18 + index:02d}:00+09:00" if status == "submitted" else None
        add_submission(run_keys["quiz"], student_login, status, score, started_at, submitted_at)

    writing_counts = {
        "s30201": 640,
        "s30202": 520,
        "s30203": 0,
        "s30204": 710,
        "s30205": 830,
        "s30206": 390,
        "s30207": 760,
        "s30208": 450,
        "s30209": 980,
        "s30210": 0,
        "s30211": 610,
        "s30212": 570,
    }
    writing_scores = {
        "s30201": 86,
        "s30202": 79,
        "s30204": 88,
        "s30205": 94,
        "s30206": 72,
        "s30207": 90,
        "s30208": 74,
        "s30209": 97,
        "s30211": 82,
        "s30212": 78,
    }
    for index, (student_login, _name) in enumerate(main_students, start=1):
        count = writing_counts[student_login]
        status = "submitted" if count else "in_progress"
        submitted_at = f"2026-06-12T10:{22 + (index % 9):02d}:30+09:00" if count else None
        add_submission(
            run_keys["writing"],
            student_login,
            status,
            writing_scores.get(student_login),
            f"2026-06-12T10:{10 + (index % 12):02d}:00+09:00",
            submitted_at,
        )

    ai_counts = {
        "s30201": 710,
        "s30202": 660,
        "s30204": 590,
        "s30205": 880,
        "s30207": 730,
        "s30208": 640,
        "s30209": 1010,
        "s30211": 690,
    }
    ai_scores = {
        "s30201": 88,
        "s30202": 84,
        "s30204": 80,
        "s30205": 92,
        "s30207": 87,
        "s30208": 83,
        "s30209": 96,
        "s30211": 85,
    }
    for index, student_login in enumerate(ai_counts, start=1):
        add_submission(
            run_keys["ai_writing"],
            student_login,
            "submitted",
            ai_scores[student_login],
            f"2026-06-16T11:{8 + index:02d}:00+09:00",
            f"2026-06-16T11:{18 + index:02d}:00+09:00",
        )

    ai_anomaly_statuses = {
        "s30203": ("assigned", None, None, None, "latest_session_no_show"),
        "s30206": (
            "in_progress",
            None,
            "2026-06-16T11:11:00+09:00",
            None,
            "started_but_not_finished",
        ),
        "s30210": (
            "retry",
            48,
            "2026-06-16T11:14:00+09:00",
            None,
            "low_score_retry",
        ),
        "s30212": ("assigned", None, None, None, "latest_session_no_show"),
    }
    for student_login, (status, score, started_at, submitted_at, feedback) in ai_anomaly_statuses.items():
        add_submission(
            run_keys["ai_writing"],
            student_login,
            status,
            score,
            started_at,
            submitted_at,
            feedback=feedback,
        )

    korean_counts = {
        "s30201": 740,
        "s30202": 680,
        "s30203": 310,
        "s30204": 800,
        "s30205": 860,
        "s30206": 430,
        "s30207": 790,
        "s30208": 520,
        "s30209": 910,
        "s30210": 280,
        "s30211": 720,
        "s30212": 0,
    }
    korean_scores = {
        "s30201": 89,
        "s30202": 84,
        "s30203": 62,
        "s30204": 91,
        "s30205": 95,
        "s30206": 70,
        "s30207": 90,
        "s30208": 76,
        "s30209": 97,
        "s30210": 58,
        "s30211": 86,
    }
    for index, (student_login, _name) in enumerate(main_students, start=1):
        count = korean_counts[student_login]
        status = "submitted" if count else "assigned"
        submitted_at = f"2026-06-13T09:{22 + (index % 12):02d}:00+09:00" if count else None
        add_submission(
            run_keys["korean_writing"],
            student_login,
            status,
            korean_scores.get(student_login),
            f"2026-06-13T09:{4 + (index % 12):02d}:00+09:00" if count else None,
            submitted_at,
        )

    may_quiz_statuses = {
        "s30201": ("submitted", 84),
        "s30202": ("submitted", 81),
        "s30203": ("submitted", 68),
        "s30204": ("submitted", 70),
        "s30205": ("submitted", 89),
        "s30206": ("submitted", 64),
        "s30207": ("submitted", 74),
        "s30208": ("submitted", 72),
        "s30209": ("submitted", 92),
        "s30210": ("in_progress", None),
        "s30211": ("submitted", 76),
        "s30212": ("assigned", None),
    }
    for index, (student_login, _name) in enumerate(main_students, start=1):
        status, score = may_quiz_statuses[student_login]
        started_at = f"2026-05-24T11:{56 + (index % 4):02d}:00+09:00" if status != "assigned" else None
        submitted_at = f"2026-05-24T12:{4 + (index % 12):02d}:00+09:00" if status == "submitted" else None
        add_submission(run_keys["may_quiz"], student_login, status, score, started_at, submitted_at)

    for index, student_login in enumerate(["s30101", "s30102", "s30301"], start=1):
        add_submission(
            run_keys["other_quiz"],
            student_login,
            "submitted",
            80 + index,
            f"2026-06-12T13:{20 + index:02d}:00+09:00",
            f"2026-06-12T13:{35 + index:02d}:00+09:00",
        )

    insert_many(
        cursor,
        """
        INSERT INTO submissions (
            submission_id, run_id, student_id, status, attempt_no, content, score, feedback,
            started_at, submitted_at, updated_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """,
        submissions,
    )

    writing_rows = []
    for student_login, char_count in writing_counts.items():
        if not char_count:
            continue
        writing_rows.append(
            (
                stable_uuid(f"writing-{run_keys['writing']}-{student_login}"),
                stable_uuid(run_keys["writing"]),
                stable_uuid(student_login),
                submission_ids[(run_keys["writing"], student_login)],
                "물 절약을 위한 나의 실천",
                f"{student_login} 학생의 물 절약 설명문입니다. 증발과 응결을 바탕으로 물의 순환을 설명했습니다.",
                char_count,
                1,
                "2026-06-12T10:31:00+09:00",
                "2026-06-12T10:31:00+09:00",
                "2026-06-12T10:31:00+09:00",
            )
        )
    for student_login, char_count in ai_counts.items():
        writing_rows.append(
            (
                stable_uuid(f"writing-{run_keys['ai_writing']}-{student_login}"),
                stable_uuid(run_keys["ai_writing"]),
                stable_uuid(student_login),
                submission_ids[(run_keys["ai_writing"], student_login)],
                "기후 변화 해결 제안",
                f"{student_login} 학생의 AI 피드백 반영 제안문입니다. 학교와 가정에서 할 수 있는 실천을 정리했습니다.",
                char_count,
                2,
                "2026-06-16T11:29:00+09:00",
                "2026-06-16T11:29:00+09:00",
                "2026-06-16T11:29:00+09:00",
            )
        )
    for student_login, char_count in korean_counts.items():
        if not char_count:
            continue
        writing_rows.append(
            (
                stable_uuid(f"writing-{run_keys['korean_writing']}-{student_login}"),
                stable_uuid(run_keys["korean_writing"]),
                stable_uuid(student_login),
                submission_ids[(run_keys["korean_writing"], student_login)],
                "우리 동네 문제 해결 의견문",
                f"{student_login} 학생의 동네 문제 해결 의견문입니다. 문제 상황과 해결 방안을 제시했습니다.",
                char_count,
                1,
                "2026-06-13T09:40:00+09:00",
                "2026-06-13T09:40:00+09:00",
                "2026-06-13T09:40:00+09:00",
            )
        )

    insert_many(
        cursor,
        """
        INSERT INTO writing_submissions (
            writing_submission_id, run_id, student_id, submission_id, title, body, char_count,
            revision_no, submitted_at, created_at, updated_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """,
        writing_rows,
    )

    question_bank = [
        ("물의 순환에서 물이 수증기가 되는 과정은?", "증발"),
        ("수증기가 물방울로 변하는 과정은?", "응결"),
        ("구름에서 비나 눈이 내리는 현상은?", "강수"),
        ("물이 땅속으로 스며드는 현상은?", "침투"),
        ("식물이 물을 공기 중으로 내보내는 작용은?", "증산"),
    ]
    quiz_rows = []
    correctness_by_score = {
        "s30201": [True, True, True, True, True],
        "s30202": [True, True, True, True, False],
        "s30204": [True, True, False, True, False],
        "s30205": [True, True, True, True, False],
        "s30207": [True, True, True, False, False],
        "s30208": [True, False, True, False, False],
        "s30209": [True, True, True, True, True],
        "s30211": [True, True, False, False, True],
    }
    for student_login, answers in correctness_by_score.items():
        for question_no, ((question_text, correct_answer), is_correct) in enumerate(zip(question_bank, answers), start=1):
            quiz_rows.append(
                (
                    stable_uuid(f"quiz-answer-{student_login}-{question_no}"),
                    stable_uuid(run_keys["quiz"]),
                    stable_uuid(student_login),
                    submission_ids[(run_keys["quiz"], student_login)],
                    question_no,
                    question_text,
                    correct_answer if is_correct else "모름",
                    correct_answer,
                    is_correct,
                    f"2026-06-12T10:{14 + question_no:02d}:00+09:00",
                )
            )
    may_question_bank = [
        ("배추흰나비가 알에서 깨어나 처음 되는 단계는?", "애벌레"),
        ("애벌레가 자라며 여러 번 하는 것은?", "허물벗기"),
        ("어른벌레가 되기 전 단계는?", "번데기"),
        ("배추흰나비가 알을 낳는 식물은?", "배추"),
        ("한살이는 무엇을 뜻하나요?", "자라는 과정"),
    ]
    may_correctness = {
        "s30201": [True, True, True, True, False],
        "s30202": [True, True, True, False, False],
        "s30203": [True, False, True, False, False],
        "s30204": [True, False, True, True, False],
        "s30205": [True, True, True, True, False],
        "s30206": [True, False, False, True, False],
        "s30207": [True, True, False, True, False],
        "s30208": [True, False, True, False, True],
        "s30209": [True, True, True, True, True],
        "s30211": [True, True, False, True, False],
    }
    for student_login, answers in may_correctness.items():
        for question_no, ((question_text, correct_answer), is_correct) in enumerate(zip(may_question_bank, answers), start=1):
            quiz_rows.append(
                (
                    stable_uuid(f"quiz-answer-may-{student_login}-{question_no}"),
                    stable_uuid(run_keys["may_quiz"]),
                    stable_uuid(student_login),
                    submission_ids[(run_keys["may_quiz"], student_login)],
                    question_no,
                    question_text,
                    correct_answer if is_correct else "모름",
                    correct_answer,
                    is_correct,
                    f"2026-05-24T12:{2 + question_no:02d}:00+09:00",
                )
            )

    insert_many(
        cursor,
        """
        INSERT INTO quiz_answers (
            answer_id, run_id, student_id, submission_id, question_no, question_text,
            selected_answer, correct_answer, is_correct, answered_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """,
        quiz_rows,
    )

    activity_log_rows = []

    def add_activity_log(
        log_key: str,
        run_key: str,
        student_login: str,
        event_type: str,
        section: str,
        target_type: str,
        target_id: str,
        value_text: str | None,
        value_number: int | float | None,
        duration_ms: int | None,
        payload: dict[str, Any],
        occurred_at: str,
    ) -> None:
        activity_log_rows.append(
            (
                stable_uuid(log_key),
                stable_uuid(run_key),
                stable_uuid(student_login),
                event_type,
                section,
                target_type,
                target_id,
                value_text,
                value_number,
                duration_ms,
                Json(payload),
                occurred_at,
                occurred_at,
            )
        )

    reading_seconds = [420, 360, 180, 510, 540, 240, 480, 330, 600, 210, 390, 300]
    for index, ((student_login, _name), seconds) in enumerate(zip(main_students, reading_seconds), start=1):
        activity_log_rows.append(
            (
                stable_uuid(f"log-reading-{student_login}"),
                stable_uuid(run_keys["reading"]),
                stable_uuid(student_login),
                "page_viewed",
                "reading",
                "page",
                f"water-page-{(index % 4) + 1}",
                None,
                seconds,
                seconds * 1000,
                Json({"page_count": 4}),
                f"2026-06-12T09:{50 + (index % 8):02d}:00+09:00",
                f"2026-06-12T09:{51 + (index % 8):02d}:00+09:00",
            )
        )
        if quiz_statuses[student_login][0] != "assigned":
            activity_log_rows.append(
                (
                    stable_uuid(f"log-quiz-start-{student_login}"),
                    stable_uuid(run_keys["quiz"]),
                    stable_uuid(student_login),
                    "activity_started",
                    "quiz",
                    "activity",
                    "water-quiz",
                    None,
                    None,
                    None,
                    Json({}),
                    f"2026-06-12T10:{8 + index:02d}:00+09:00",
                    f"2026-06-12T10:{8 + index:02d}:00+09:00",
                )
            )
        if student_login in ai_counts:
            activity_log_rows.append(
                (
                    stable_uuid(f"log-ai-message-{student_login}"),
                    stable_uuid(run_keys["ai_writing"]),
                    stable_uuid(student_login),
                    "ai_message_sent",
                    "ai_writing",
                    "prompt",
                    "draft-feedback",
                    "내 글에서 근거가 부족한 부분을 알려줘",
                    1,
                    None,
                    Json({"message_type": "feedback_request"}),
                    f"2026-06-16T11:{9 + index:02d}:00+09:00",
                    f"2026-06-16T11:{9 + index:02d}:00+09:00",
                )
            )

    may_reading_seconds = [360, 330, 210, 410, 450, 180, 390, 240, 520, 120, 310, 90]
    for index, ((student_login, _name), seconds) in enumerate(zip(main_students, may_reading_seconds), start=1):
        add_activity_log(
            f"log-may-reading-{student_login}",
            run_keys["may_reading"],
            student_login,
            "page_viewed",
            "reading",
            "page",
            f"butterfly-page-{(index % 3) + 1}",
            None,
            seconds,
            seconds * 1000,
            {"page_count": 3},
            f"2026-05-24T11:{45 + (index % 8):02d}:00+09:00",
        )

    for index, (student_login, _name) in enumerate(main_students, start=1):
        may_status, _may_score = may_quiz_statuses[student_login]
        if may_status != "assigned":
            add_activity_log(
                f"log-may-quiz-start-{student_login}",
                run_keys["may_quiz"],
                student_login,
                "activity_started",
                "quiz",
                "activity",
                "butterfly-quiz",
                None,
                None,
                None,
                {},
                f"2026-05-24T11:{56 + (index % 4):02d}:00+09:00",
            )
        if may_status == "submitted":
            add_activity_log(
                f"log-may-quiz-completed-{student_login}",
                run_keys["may_quiz"],
                student_login,
                "activity_completed",
                "quiz",
                "activity",
                "butterfly-quiz",
                None,
                1,
                None,
                {"status": "submitted"},
                f"2026-05-24T12:{4 + (index % 12):02d}:00+09:00",
            )

    for index, (student_login, _name) in enumerate(main_students, start=1):
        for run_key, counts, target_id, day, hour, base_minute in [
            (run_keys["writing"], writing_counts, "water-writing", "2026-06-12", 10, 10),
            (run_keys["korean_writing"], korean_counts, "opinion-writing", "2026-06-13", 9, 4),
        ]:
            char_count = counts[student_login]
            if char_count:
                add_activity_log(
                    f"log-{run_key}-start-{student_login}",
                    run_key,
                    student_login,
                    "activity_started",
                    "writing",
                    "activity",
                    target_id,
                    None,
                    None,
                    None,
                    {},
                    f"{day}T{hour:02d}:{base_minute + (index % 12):02d}:00+09:00",
                )
                add_activity_log(
                    f"log-{run_key}-typed-{student_login}",
                    run_key,
                    student_login,
                    "text_typed",
                    "writing",
                    "editor",
                    target_id,
                    None,
                    char_count,
                    12 * 60 * 1000 + index * 1000,
                    {"char_count": char_count},
                    f"{day}T{hour:02d}:{base_minute + 12 + (index % 10):02d}:00+09:00",
                )
                add_activity_log(
                    f"log-{run_key}-completed-{student_login}",
                    run_key,
                    student_login,
                    "activity_completed",
                    "writing",
                    "activity",
                    target_id,
                    None,
                    1,
                    None,
                    {"status": "submitted"},
                    f"{day}T{hour:02d}:{base_minute + 22 + (index % 12):02d}:00+09:00",
                )
            elif run_key == run_keys["writing"]:
                add_activity_log(
                    f"log-{run_key}-start-{student_login}",
                    run_key,
                    student_login,
                    "activity_started",
                    "writing",
                    "activity",
                    target_id,
                    None,
                    None,
                    None,
                    {"status": "in_progress"},
                    f"{day}T{hour:02d}:{base_minute + (index % 12):02d}:00+09:00",
                )

    for index, student_login in enumerate(ai_counts, start=1):
        add_activity_log(
            f"log-ai-writing-start-{student_login}",
            run_keys["ai_writing"],
            student_login,
            "activity_started",
            "ai_writing",
            "activity",
            "climate-ai-writing",
            None,
            None,
            None,
            {},
            f"2026-06-16T11:{8 + index:02d}:00+09:00",
        )
        add_activity_log(
            f"log-ai-writing-completed-{student_login}",
            run_keys["ai_writing"],
            student_login,
            "activity_completed",
            "ai_writing",
            "activity",
            "climate-ai-writing",
            None,
            1,
            None,
            {"status": "submitted"},
            f"2026-06-16T11:{18 + index:02d}:00+09:00",
        )

    for index, student_login in enumerate(["s30201", "s30204", "s30205", "s30207", "s30209"], start=1):
        add_activity_log(
            f"log-discussion-posted-{student_login}",
            run_keys["discussion"],
            student_login,
            "discussion_posted",
            "discussion",
            "post",
            "climate-discussion",
            "기후 변화 대응 의견",
            1,
            None,
            {"space_name": "찬성" if index % 2 else "질문"},
            f"2026-06-16T10:{51 + index:02d}:00+09:00",
        )
    for index, student_login in enumerate(["s30202", "s30208", "s30211"], start=1):
        add_activity_log(
            f"log-discussion-commented-{student_login}",
            run_keys["discussion"],
            student_login,
            "discussion_commented",
            "discussion",
            "comment",
            "climate-discussion",
            "친구 의견에 댓글 작성",
            1,
            None,
            {"space_name": "댓글"},
            f"2026-06-16T11:{index:02d}:00+09:00",
        )

    focus_signal_rows = [
        (
            "s30206",
            "log-focus-signal-s30206",
            "2026-06-16T11:12:00+09:00",
            42_000,
            "joined_latest_session_but_left_activity_early",
        ),
        (
            "s30210",
            "log-focus-signal-s30210",
            "2026-06-16T11:15:00+09:00",
            38_000,
            "repeated_short_starts_and_retry_status",
        ),
    ]
    for student_login, log_key, occurred_at, duration_ms, signal in focus_signal_rows:
        add_activity_log(
            log_key,
            run_keys["ai_writing"],
            student_login,
            "activity_started",
            "ai_writing",
            "activity",
            "climate-ai-writing",
            None,
            None,
            duration_ms,
            {
                "difficulty_focusing": True,
                "participation_issue": True,
                "consistency_issue": True,
                "signal": signal,
            },
            occurred_at,
        )

    for student_login, log_key, occurred_at, signal in [
        ("s30203", "log-no-show-signal-s30203", "2026-06-16T11:31:00+09:00", "latest_session_no_show"),
        ("s30212", "log-no-show-signal-s30212", "2026-06-16T11:32:00+09:00", "latest_session_no_show"),
    ]:
        add_activity_log(
            log_key,
            run_keys["ai_writing"],
            student_login,
            "activity_started",
            "ai_writing",
            "activity",
            "climate-ai-writing",
            None,
            None,
            50_000,
            {
                "difficulty_focusing": True,
                "participation_issue": True,
                "consistency_issue": True,
                "signal": signal,
                "synthetic_observation": "assigned_without_meaningful_progress",
            },
            occurred_at,
        )

    short_start_students = ["s30203", "s30206", "s30210", "s30212"]
    start_duration_by_user = {
        stable_uuid(student_login): (35 + index * 5) * 1000
        for index, student_login in enumerate(short_start_students)
    }
    activity_log_rows = [
        row[:9] + (start_duration_by_user.get(row[2], 95_000),) + row[10:]
        if row[3] == "activity_started"
        else row
        for row in activity_log_rows
    ]

    insert_many(
        cursor,
        """
        INSERT INTO activity_logs (
            log_id, run_id, user_id, event_type, section, target_type, target_id, value_text,
            value_number, duration_ms, payload, occurred_at, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """,
        activity_log_rows,
    )

    access_log_rows = []

    def add_access_log(
        log_key: str,
        student_login: str,
        session_key: str | None,
        action: str,
        page_path: str,
        occurred_at: str,
        index: int,
    ) -> None:
        access_log_rows.append(
            (
                stable_uuid(log_key),
                stable_uuid(student_login),
                stable_uuid(session_key) if session_key else None,
                action,
                page_path,
                f"10.20.3.{index}",
                "Edu2SQL PoC Browser",
                "tablet" if index % 2 else "desktop",
                occurred_at,
            )
        )

    for index, (student_login, _name) in enumerate(main_students, start=1):
        access_log_rows.append(
            (
                stable_uuid(f"access-login-{student_login}"),
                stable_uuid(student_login),
                None,
                "login",
                "/login",
                f"10.20.3.{index}",
                "Edu2SQL PoC Browser",
                "tablet" if index % 2 else "desktop",
                f"2026-06-12T09:{35 + (index % 10):02d}:00+09:00",
            )
        )
        if student_login not in {"s30212"}:
            access_log_rows.append(
                (
                    stable_uuid(f"access-join-{student_login}"),
                    stable_uuid(student_login),
                    stable_uuid("session-science-water"),
                    "join_session",
                    "/sessions/water-cycle",
                    f"10.20.3.{index}",
                    "Edu2SQL PoC Browser",
                    "tablet" if index % 2 else "desktop",
                f"2026-06-12T09:{48 + (index % 8):02d}:00+09:00",
            )
        )
        if student_login in {"s30201", "s30202", "s30204", "s30205", "s30207", "s30208", "s30209", "s30211"}:
            add_access_log(
                f"access-join-climate-{student_login}",
                student_login,
                "session-science-climate",
                "join_session",
                "/sessions/climate-discussion",
                f"2026-06-16T10:{44 + (index % 9):02d}:00+09:00",
                index,
            )
        if student_login in {"s30206", "s30210"}:
            add_access_log(
                f"access-join-climate-anomaly-{student_login}",
                student_login,
                "session-science-climate",
                "join_session",
                "/sessions/climate-discussion",
                f"2026-06-16T10:{52 + (index % 5):02d}:00+09:00",
                index,
            )
        if student_login in {"s30201", "s30202", "s30204", "s30205", "s30206", "s30207", "s30208", "s30209", "s30210", "s30211"}:
            add_access_log(
                f"access-join-korean-{student_login}",
                student_login,
                "session-korean-opinion",
                "join_session",
                "/sessions/opinion-writing",
                f"2026-06-13T08:{54 + (index % 6):02d}:00+09:00",
                index,
            )
        if student_login not in {"s30210", "s30212"}:
            add_access_log(
                f"access-join-may-{student_login}",
                student_login,
                "session-science-may",
                "join_session",
                "/sessions/butterfly-cycle",
                f"2026-05-24T11:{38 + (index % 8):02d}:00+09:00",
                index,
            )
        if student_login in {"s30201", "s30202", "s30205", "s30207", "s30209", "s30211"}:
            for repeat in range(1, 4):
                add_access_log(
                    f"access-recent-study-{student_login}-{repeat}",
                    student_login,
                    None,
                    "navigate",
                    "/dashboard/today",
                    f"2026-06-{10 + repeat:02d}T19:{10 + index:02d}:00+09:00",
                    index,
                )

    insert_many(
        cursor,
        """
        INSERT INTO access_logs (
            access_log_id, user_id, session_id, action, page_path, ip_address,
            user_agent, device_type, occurred_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
        """,
        access_log_rows,
    )

    post_rows = []
    parent_ids: dict[str, str] = {}
    for index, student_login in enumerate(["s30201", "s30204", "s30205", "s30207", "s30209"], start=1):
        post_id = stable_uuid(f"discussion-post-{student_login}")
        parent_ids[student_login] = post_id
        post_rows.append(
            (
                post_id,
                stable_uuid(run_keys["discussion"]),
                stable_uuid(student_login),
                None,
                "찬성" if index % 2 else "질문",
                "기후 변화 대응을 위해 학교에서 전기 절약 캠페인을 하면 좋겠습니다.",
                f"2026-06-16T10:{51 + index:02d}:00+09:00",
                f"2026-06-16T10:{51 + index:02d}:00+09:00",
            )
        )
    replies = [
        ("s30202", "s30201", "저도 동의해요. 교실 불 끄기부터 할 수 있어요."),
        ("s30208", "s30204", "질문에 답하자면 급식실 음식물 쓰레기 줄이기도 관련 있어요."),
        ("s30211", "s30205", "캠페인 포스터를 만들면 참여가 더 늘 것 같아요."),
    ]
    for index, (author, parent, body) in enumerate(replies, start=1):
        post_rows.append(
            (
                stable_uuid(f"discussion-reply-{author}-{parent}"),
                stable_uuid(run_keys["discussion"]),
                stable_uuid(author),
                parent_ids[parent],
                "댓글",
                body,
                f"2026-06-16T11:{index:02d}:00+09:00",
                f"2026-06-16T11:{index:02d}:00+09:00",
            )
        )

    insert_many(
        cursor,
        """
        INSERT INTO discussion_posts (
            post_id, run_id, author_id, parent_post_id, space_name, body, created_at, updated_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
        """,
        post_rows,
    )


def print_counts(cursor) -> None:
    print("Seeded PoC row counts:")
    for table in TABLES:
        cursor.execute(f"SELECT COUNT(*) FROM {table};")
        count = cursor.fetchone()[0]
        print(f"- {table}: {count}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed the Edu2SQL PoC PostgreSQL database.")
    parser.add_argument("--reset", action="store_true", help="Drop and recreate the PoC tables before seeding.")
    parser.add_argument("--yes", action="store_true", help="Confirm destructive reset of PoC tables.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.reset:
        raise SystemExit("This PoC seed is deterministic and currently requires --reset.")
    if not args.yes:
        raise SystemExit("Refusing to reset without --yes.")

    connection = connect()
    try:
        with connection:
            with connection.cursor() as cursor:
                reset_schema(cursor)
                seed_data(cursor)
                print_counts(cursor)
    finally:
        connection.close()


if __name__ == "__main__":
    main()
