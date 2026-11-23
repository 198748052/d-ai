from __future__ import annotations

from collections.abc import Iterator

from sqlmodel import Session, SQLModel, create_engine

from ..core.config import DB_PATH

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
)


def _migrate() -> None:
    with engine.connect() as conn:
        columns = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(featurerule)")]
        if "replace_mode" not in columns:
            conn.exec_driver_sql(
                "ALTER TABLE featurerule ADD COLUMN replace_mode VARCHAR DEFAULT 'all'"
            )
            conn.commit()
        llm_columns = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(llmsetting)")]
        for column, ddl in [
            ("local_enabled", "BOOLEAN DEFAULT 0"),
            ("local_model", "VARCHAR DEFAULT 'Qwen/Qwen2.5-1.5B'"),
            ("local_dtype", "VARCHAR DEFAULT 'float16'"),
            ("reasoning_effort", "VARCHAR DEFAULT 'medium'"),
            ("ppl_min", "FLOAT DEFAULT 45.0"),
            ("ppl_retry", "INTEGER DEFAULT 2"),
            ("ppl_severe", "FLOAT DEFAULT 20.0"),
            ("candidate_count", "INTEGER DEFAULT 1"),
            ("deep_rewrite", "BOOLEAN DEFAULT 0"),
            ("structure_mode", "VARCHAR DEFAULT 'preserve'"),
        ]:
            if column not in llm_columns:
                conn.exec_driver_sql(f"ALTER TABLE llmsetting ADD COLUMN {column} {ddl}")
        job_columns = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(rewritejob)")]
        for column, ddl in [
            ("updated_at", "DATETIME"),
            ("result_json", "TEXT DEFAULT ''"),
            ("error", "TEXT DEFAULT ''"),
            ("progress_total", "INTEGER DEFAULT 0"),
            ("progress_completed", "INTEGER DEFAULT 0"),
            ("user_id", "INTEGER"),
            ("charged_chars", "INTEGER DEFAULT 0"),
        ]:
            if column not in job_columns:
                conn.exec_driver_sql(f"ALTER TABLE rewritejob ADD COLUMN {column} {ddl}")
        lesson_columns = [
            row[1] for row in conn.exec_driver_sql("PRAGMA table_info(rewritelesson)")
        ]
        outcome_added = "outcome" not in lesson_columns
        template_added = "template" not in lesson_columns
        for column, ddl in [
            ("pattern", "TEXT DEFAULT ''"),
            ("template", "TEXT DEFAULT ''"),
            ("category", "VARCHAR DEFAULT 'low_perplexity'"),
            ("outcome", "VARCHAR DEFAULT 'pending'"),
            ("status", "VARCHAR DEFAULT 'active'"),
            ("scope", "VARCHAR DEFAULT 'sentence'"),
            ("strategy", "TEXT DEFAULT ''"),
            ("last_seen_at", "DATETIME"),
            ("source_job_id", "INTEGER"),
        ]:
            if column not in lesson_columns:
                conn.exec_driver_sql(f"ALTER TABLE rewritelesson ADD COLUMN {column} {ddl}")
        if outcome_added:
            conn.exec_driver_sql(
                "UPDATE rewritelesson SET outcome='survived', pattern=sentence, "
                "template=sentence, category='low_perplexity', status='active', "
                "scope='sentence'"
            )
        elif template_added:
            conn.exec_driver_sql(
                "UPDATE rewritelesson SET template=pattern "
                "WHERE template IS NULL OR template = ''"
            )
        conn.exec_driver_sql(
            "UPDATE rewritelesson SET last_seen_at = updated_at WHERE last_seen_at IS NULL"
        )
        conn.exec_driver_sql(
            "UPDATE rewritejob SET status='error', error='服务重启，任务已中断' "
            "WHERE status IN ('running', 'paused', 'interrupted')"
        )
        conn.commit()


def init_db() -> None:
    from ..models import models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    _migrate()


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
