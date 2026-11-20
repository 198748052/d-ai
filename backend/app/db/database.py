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
            ("ppl_min", "FLOAT DEFAULT 60.0"),
            ("ppl_retry", "INTEGER DEFAULT 2"),
            ("ppl_severe", "FLOAT DEFAULT 25.0"),
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
        ]:
            if column not in job_columns:
                conn.exec_driver_sql(f"ALTER TABLE rewritejob ADD COLUMN {column} {ddl}")
        conn.exec_driver_sql(
            "UPDATE rewritejob SET status='interrupted' WHERE status='running'"
        )
        conn.commit()


def init_db() -> None:
    from ..models import models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    _migrate()


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
