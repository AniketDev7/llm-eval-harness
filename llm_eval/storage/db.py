"""SQLite storage. Append-only audit trail (no UPDATE/DELETE)."""
from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from llm_eval.models import CompletionResult, EvalResult, RunRecord


SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    suite_name TEXT NOT NULL,
    suite_version TEXT NOT NULL,
    provider TEXT NOT NULL,
    composite_score REAL NOT NULL,
    coverage_score REAL NOT NULL,
    accuracy_score REAL NOT NULL,
    format_score REAL NOT NULL,
    hallucination_score REAL NOT NULL,
    threshold_status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS eval_results (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    eval_name TEXT NOT NULL,
    category TEXT NOT NULL,
    provider TEXT NOT NULL,
    prompt TEXT NOT NULL,
    response_text TEXT NOT NULL,
    latency_ms INTEGER NOT NULL,
    tokens_used INTEGER NOT NULL,
    assertion_type TEXT NOT NULL,
    assertion_passed INTEGER NOT NULL,
    assertion_score REAL NOT NULL,
    assertion_detail TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(id)
);

-- Canonical lossless audit tables. `eval_results` remains as a flattened
-- compatibility view for existing databases and API consumers.
CREATE TABLE IF NOT EXISTS eval_case_records (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    eval_index INTEGER NOT NULL,
    eval_name TEXT NOT NULL,
    category TEXT NOT NULL,
    provider TEXT NOT NULL,
    prompt TEXT NOT NULL,
    response_text TEXT NOT NULL,
    latency_ms INTEGER NOT NULL,
    tokens_used INTEGER NOT NULL,
    model_version TEXT NOT NULL,
    error TEXT,
    FOREIGN KEY (run_id) REFERENCES runs(id),
    UNIQUE (run_id, eval_index)
);

CREATE TABLE IF NOT EXISTS assertion_records (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    assertion_index INTEGER NOT NULL,
    assertion_type TEXT NOT NULL,
    assertion_passed INTEGER NOT NULL,
    assertion_score REAL NOT NULL,
    assertion_detail TEXT NOT NULL,
    FOREIGN KEY (case_id) REFERENCES eval_case_records(id),
    UNIQUE (case_id, assertion_index)
);

CREATE TABLE IF NOT EXISTS completion_attempts (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    attempt_index INTEGER NOT NULL,
    response_text TEXT NOT NULL,
    latency_ms INTEGER NOT NULL,
    tokens_used INTEGER NOT NULL,
    model_version TEXT NOT NULL,
    error TEXT,
    FOREIGN KEY (case_id) REFERENCES eval_case_records(id),
    UNIQUE (case_id, attempt_index)
);

CREATE TABLE IF NOT EXISTS baselines (
    id TEXT PRIMARY KEY,
    captured_at TEXT NOT NULL,
    suite_name TEXT NOT NULL,
    provider TEXT NOT NULL,
    composite_score REAL NOT NULL,
    coverage_score REAL NOT NULL,
    accuracy_score REAL NOT NULL,
    format_score REAL NOT NULL,
    hallucination_score REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_runs_suite ON runs(suite_name, provider);
CREATE INDEX IF NOT EXISTS idx_results_run ON eval_results(run_id);
CREATE INDEX IF NOT EXISTS idx_case_records_run ON eval_case_records(run_id, eval_index);
CREATE INDEX IF NOT EXISTS idx_assertion_records_case ON assertion_records(case_id, assertion_index);
CREATE INDEX IF NOT EXISTS idx_completion_attempts_case ON completion_attempts(case_id, attempt_index);
CREATE INDEX IF NOT EXISTS idx_baselines_suite ON baselines(suite_name, provider);
"""


def get_db_path() -> str:
    return os.getenv("LLM_EVAL_DB_PATH", "./llm_eval.db")


def _connect(path: str | None = None) -> sqlite3.Connection:
    path = path or get_db_path()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path: str | None = None) -> None:
    """Idempotent: creates tables if missing."""
    conn = _connect(path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def save_run(record: RunRecord, path: str | None = None) -> None:
    """Insert a run plus all its eval_results. Append-only."""
    init_db(path)
    conn = _connect(path)
    try:
        conn.execute(
            """INSERT INTO runs (
                id, timestamp, suite_name, suite_version, provider,
                composite_score, coverage_score, accuracy_score,
                format_score, hallucination_score, threshold_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.id, record.timestamp, record.suite_name,
                record.suite_version, record.provider,
                record.composite_score, record.coverage_score,
                record.accuracy_score, record.format_score,
                record.hallucination_score, record.threshold_status,
            ),
        )
        for eval_index, r in enumerate(record.results):
            case_id = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO eval_case_records (
                    id, run_id, eval_index, eval_name, category, provider,
                    prompt, response_text, latency_ms, tokens_used,
                    model_version, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    case_id, record.id, eval_index, r.eval_name, r.category,
                    r.provider, r.prompt, r.response, r.latency_ms,
                    r.tokens_used, r.model_version, r.error,
                ),
            )
            completions = r.completions or [CompletionResult(
                text=r.response,
                latency_ms=r.latency_ms,
                tokens_used=r.tokens_used,
                model_version=r.model_version,
                error=r.error,
            )]
            for attempt_index, completion in enumerate(completions):
                conn.execute(
                    """INSERT INTO completion_attempts (
                        id, case_id, attempt_index, response_text, latency_ms,
                        tokens_used, model_version, error
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        str(uuid.uuid4()), case_id, attempt_index,
                        completion.text, completion.latency_ms,
                        completion.tokens_used, completion.model_version,
                        completion.error,
                    ),
                )
            for assertion_index, a in enumerate(r.assertions):
                conn.execute(
                    """INSERT INTO assertion_records (
                        id, case_id, assertion_index, assertion_type,
                        assertion_passed, assertion_score, assertion_detail
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        str(uuid.uuid4()), case_id, assertion_index, a.type,
                        1 if a.passed else 0, a.score, a.detail,
                    ),
                )
                conn.execute(
                    """INSERT INTO eval_results (
                        id, run_id, eval_name, category, provider,
                        prompt, response_text, latency_ms, tokens_used,
                        assertion_type, assertion_passed, assertion_score, assertion_detail
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        str(uuid.uuid4()), record.id, r.eval_name, r.category,
                        r.provider, r.prompt, r.response, r.latency_ms,
                        r.tokens_used, a.type, 1 if a.passed else 0,
                        a.score, a.detail,
                    ),
                )
        conn.commit()
    finally:
        conn.close()


def get_run(run_id: str, path: str | None = None) -> Optional[dict]:
    conn = _connect(path)
    try:
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_runs(
    limit: int = 20, offset: int = 0,
    suite_name: str | None = None, provider: str | None = None,
    path: str | None = None,
) -> list[dict]:
    init_db(path)
    conn = _connect(path)
    try:
        where = []
        params: list = []
        if suite_name:
            where.append("suite_name = ?")
            params.append(suite_name)
        if provider:
            where.append("provider = ?")
            params.append(provider)
        sql = "SELECT * FROM runs"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_results_for_run(run_id: str, path: str | None = None) -> list[dict]:
    conn = _connect(path)
    try:
        rows = conn.execute(
            "SELECT * FROM eval_results WHERE run_id = ?", (run_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_audit_results_for_run(run_id: str, path: str | None = None) -> list[dict]:
    """Return lossless evaluation records with assertions and all completions."""
    init_db(path)
    conn = _connect(path)
    try:
        cases = conn.execute(
            "SELECT * FROM eval_case_records WHERE run_id = ? ORDER BY eval_index",
            (run_id,),
        ).fetchall()
        audit: list[dict] = []
        for case in cases:
            item = dict(case)
            assertions = conn.execute(
                """SELECT assertion_type, assertion_passed, assertion_score,
                          assertion_detail
                   FROM assertion_records WHERE case_id = ? ORDER BY assertion_index""",
                (case["id"],),
            ).fetchall()
            completions = conn.execute(
                """SELECT response_text, latency_ms, tokens_used, model_version, error
                   FROM completion_attempts WHERE case_id = ? ORDER BY attempt_index""",
                (case["id"],),
            ).fetchall()
            item["assertions"] = [dict(row) for row in assertions]
            item["completions"] = [dict(row) for row in completions]
            audit.append(item)
        return audit
    finally:
        conn.close()


def save_baseline(record: RunRecord, path: str | None = None) -> None:
    init_db(path)
    conn = _connect(path)
    try:
        conn.execute(
            """INSERT INTO baselines (
                id, captured_at, suite_name, provider,
                composite_score, coverage_score, accuracy_score,
                format_score, hallucination_score
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()),
                datetime.now(timezone.utc).isoformat(),
                record.suite_name, record.provider,
                record.composite_score, record.coverage_score,
                record.accuracy_score, record.format_score,
                record.hallucination_score,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_baseline(
    suite_name: str, provider: str, path: str | None = None,
) -> Optional[dict]:
    """Returns the most recent baseline for a suite/provider."""
    init_db(path)
    conn = _connect(path)
    try:
        row = conn.execute(
            """SELECT * FROM baselines
            WHERE suite_name = ? AND provider = ?
            ORDER BY captured_at DESC LIMIT 1""",
            (suite_name, provider),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()
