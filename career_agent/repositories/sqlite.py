import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from ..domain.models import Vacancy
from ..paths import DB_PATH


SCHEMA_VERSION = 3


class CareerRepository:
    def __init__(self, path: Path = DB_PATH):
        self.path = Path(path)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 15000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS vacancies (
                    id INTEGER PRIMARY KEY,
                    source TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    company TEXT NOT NULL,
                    title TEXT NOT NULL,
                    direction TEXT NOT NULL DEFAULT '',
                    job_type TEXT NOT NULL DEFAULT 'Вакансия',
                    work_format TEXT NOT NULL DEFAULT '',
                    salary TEXT NOT NULL DEFAULT 'Не указана',
                    url TEXT NOT NULL,
                    source_status TEXT NOT NULL,
                    score INTEGER NOT NULL DEFAULT 0 CHECK(score BETWEEN 0 AND 100),
                    area TEXT NOT NULL DEFAULT '',
                    employment TEXT NOT NULL DEFAULT '',
                    experience TEXT NOT NULL DEFAULT '',
                    published_at TEXT,
                    description TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    first_seen_at TEXT NOT NULL,
                    checked_at TEXT NOT NULL,
                    UNIQUE(source, source_id)
                );
                CREATE TABLE IF NOT EXISTS applications (
                    vacancy_id INTEGER PRIMARY KEY REFERENCES vacancies(id) ON DELETE CASCADE,
                    status TEXT NOT NULL DEFAULT 'Не подал',
                    comment TEXT NOT NULL DEFAULT '',
                    applied_at TEXT,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS status_events (
                    id INTEGER PRIMARY KEY,
                    vacancy_id INTEGER NOT NULL REFERENCES vacancies(id) ON DELETE CASCADE,
                    status TEXT NOT NULL,
                    comment TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS interview_sessions (
                    id INTEGER PRIMARY KEY,
                    session_key TEXT NOT NULL UNIQUE,
                    session_date TEXT,
                    role_type TEXT,
                    transcript_path TEXT,
                    analysis_path TEXT,
                    score REAL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS connector_runs (
                    id INTEGER PRIMARY KEY,
                    source TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    item_count INTEGER NOT NULL DEFAULT 0,
                    error TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_connector_runs_source_finished
                    ON connector_runs(source, finished_at DESC);
                CREATE TABLE IF NOT EXISTS application_workflow_steps (
                    id INTEGER PRIMARY KEY,
                    vacancy_id INTEGER NOT NULL REFERENCES vacancies(id) ON DELETE CASCADE,
                    step_key TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'todo'
                        CHECK(state IN ('todo', 'in_progress', 'blocked', 'done', 'skipped')),
                    note TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL,
                    UNIQUE(vacancy_id, step_key)
                );
                CREATE INDEX IF NOT EXISTS idx_workflow_vacancy_position
                    ON application_workflow_steps(vacancy_id, position);
            """)
            db.execute(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )

    def set_metadata(self, key: str, value: str) -> None:
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO metadata(key, value) VALUES(?, ?)", (key, value))

    def get_metadata(self, key: str) -> str | None:
        if not self.path.exists():
            return None
        with self.connect() as db:
            row = db.execute("SELECT value FROM metadata WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else None

    def upsert_vacancy(self, vacancy: Vacancy) -> int:
        self.initialize()
        with self.connect() as db:
            existing = db.execute(
                "SELECT payload_json FROM vacancies WHERE source=? AND source_id=?",
                (vacancy.source, vacancy.source_id),
            ).fetchone()
            if existing:
                existing_payload = json.loads(existing["payload_json"])
                if existing_payload.get("extra", {}).get("source_copy_only"):
                    vacancy.score = 0
                    vacancy.direction = ""
                    vacancy.assessment = None
                    vacancy.extra.pop("agent_summary", None)
                    vacancy.extra.pop("hiring_chance", None)
                    vacancy.extra["source_copy_only"] = True
            payload = json.dumps(vacancy.to_dict(), ensure_ascii=False)
            db.execute("""
                INSERT INTO vacancies (
                    source, source_id, company, title, direction, job_type, work_format,
                    salary, url, source_status, score, area, employment, experience,
                    published_at, description, payload_json, first_seen_at, checked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source, source_id) DO UPDATE SET
                    company=excluded.company, title=excluded.title, direction=excluded.direction,
                    job_type=excluded.job_type, work_format=excluded.work_format,
                    salary=excluded.salary, url=excluded.url,
                    source_status=excluded.source_status, score=excluded.score,
                    area=excluded.area, employment=excluded.employment,
                    experience=excluded.experience, published_at=excluded.published_at,
                    description=excluded.description, payload_json=excluded.payload_json,
                    checked_at=excluded.checked_at
            """, (
                vacancy.source, vacancy.source_id, vacancy.company, vacancy.title,
                vacancy.direction, vacancy.job_type, vacancy.work_format, vacancy.salary,
                vacancy.url, vacancy.source_status, vacancy.score, vacancy.area,
                vacancy.employment, vacancy.experience, vacancy.published_at,
                vacancy.description, payload, vacancy.checked_at, vacancy.checked_at,
            ))
            row = db.execute(
                "SELECT id FROM vacancies WHERE source=? AND source_id=?",
                (vacancy.source, vacancy.source_id),
            ).fetchone()
            vacancy_id = int(row["id"])
            db.execute("""
                INSERT INTO applications(vacancy_id, status, updated_at)
                VALUES(?, 'Не подал', ?)
                ON CONFLICT(vacancy_id) DO NOTHING
            """, (vacancy_id, vacancy.checked_at))
            return vacancy_id

    def mark_source_copy(self, source: str, source_id: str) -> Vacancy:
        self.initialize()
        with self.connect() as db:
            row = db.execute(
                "SELECT payload_json FROM vacancies WHERE source=? AND source_id=?",
                (source, source_id),
            ).fetchone()
            if not row:
                raise KeyError(f"Вакансия {source}:{source_id} не найдена")
            payload = json.loads(row["payload_json"])
            payload["score"] = 0
            payload["direction"] = ""
            payload["assessment"] = None
            extra = payload.setdefault("extra", {})
            extra.pop("agent_summary", None)
            extra.pop("hiring_chance", None)
            extra["source_copy_only"] = True
            db.execute("""
                UPDATE vacancies
                SET score = 0, direction = '', payload_json = ?
                WHERE source = ? AND source_id = ?
            """, (json.dumps(payload, ensure_ascii=False), source, source_id))
            return Vacancy.from_dict(payload)

    def set_application_status(
        self, source: str, source_id: str, status: str, comment: str = "", applied_at: str | None = None,
    ) -> None:
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with self.connect() as db:
            row = db.execute(
                "SELECT id FROM vacancies WHERE source=? AND source_id=?", (source, source_id),
            ).fetchone()
            if not row:
                raise KeyError(f"Вакансия {source}:{source_id} не найдена")
            vacancy_id = int(row["id"])
            db.execute("""
                INSERT INTO applications(vacancy_id, status, comment, applied_at, updated_at)
                VALUES(?, ?, ?, ?, ?)
                ON CONFLICT(vacancy_id) DO UPDATE SET
                    status=excluded.status, comment=excluded.comment,
                    applied_at=COALESCE(excluded.applied_at, applications.applied_at),
                    updated_at=excluded.updated_at
            """, (vacancy_id, status, comment, applied_at, now))
            db.execute(
                "INSERT INTO status_events(vacancy_id, status, comment, created_at) VALUES(?, ?, ?, ?)",
                (vacancy_id, status, comment, now),
            )

    def list_vacancies(self) -> list[sqlite3.Row]:
        self.initialize()
        with self.connect() as db:
            return list(db.execute("""
                SELECT v.*, a.status AS application_status, a.comment,
                       a.applied_at, a.updated_at AS application_updated_at
                FROM vacancies v
                LEFT JOIN applications a ON a.vacancy_id = v.id
                ORDER BY v.score DESC, v.checked_at DESC
            """))

    def get_vacancy(self, source: str, source_id: str) -> sqlite3.Row | None:
        self.initialize()
        with self.connect() as db:
            return db.execute(
                "SELECT * FROM vacancies WHERE source=? AND source_id=?", (source, source_id),
            ).fetchone()

    def upsert_interview_payload(self, session_key: str, payload: dict) -> None:
        self.initialize()
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with self.connect() as db:
            existing = db.execute(
                "SELECT payload_json FROM interview_sessions WHERE session_key=?", (session_key,),
            ).fetchone()
            merged = json.loads(existing["payload_json"]) if existing else {}
            merged.update(payload)
            db.execute("""
                INSERT INTO interview_sessions(session_key, session_date, role_type, score, payload_json, updated_at)
                VALUES(?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_key) DO UPDATE SET
                    session_date=excluded.session_date, role_type=excluded.role_type,
                    score=excluded.score, payload_json=excluded.payload_json,
                    updated_at=excluded.updated_at
            """, (
                session_key, payload.get("date"), payload.get("role_type"),
                payload.get("total") or payload.get("score"),
                json.dumps(merged, ensure_ascii=False), now,
            ))

    def record_connector_run(
        self, source: str, started_at: str, status: str, item_count: int = 0, error: str = "",
    ) -> None:
        self.initialize()
        finished_at = datetime.now().astimezone().isoformat(timespec="seconds")
        with self.connect() as db:
            db.execute("""
                INSERT INTO connector_runs(source, started_at, finished_at, status, item_count, error)
                VALUES(?, ?, ?, ?, ?, ?)
            """, (source, started_at, finished_at, status, item_count, error[:1000]))

    def last_successful_sync(self, source: str) -> str | None:
        self.initialize()
        with self.connect() as db:
            row = db.execute("""
                SELECT finished_at FROM connector_runs
                WHERE source=? AND status='success'
                ORDER BY finished_at DESC LIMIT 1
            """, (source,)).fetchone()
            return row["finished_at"] if row else None

    def initialize_application_workflow(
        self, steps, source: str | None = None, source_id: str | None = None,
    ) -> tuple[int, int]:
        self.initialize()
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        where = ["a.status = 'Рассматриваю'"]
        params: list[str] = []
        if source:
            where.append("v.source = ?")
            params.append(source)
        if source_id:
            where.append("v.source_id = ?")
            params.append(source_id)
        with self.connect() as db:
            vacancies = list(db.execute(f"""
                SELECT v.id FROM vacancies v
                JOIN applications a ON a.vacancy_id = v.id
                WHERE {' AND '.join(where)}
            """, params))
            inserted = 0
            for vacancy in vacancies:
                for position, step in enumerate(steps, 1):
                    cursor = db.execute("""
                        INSERT INTO application_workflow_steps(
                            vacancy_id, step_key, position, title, updated_at
                        ) VALUES(?, ?, ?, ?, ?)
                        ON CONFLICT(vacancy_id, step_key) DO NOTHING
                    """, (vacancy["id"], step.key, position, step.title, now))
                    inserted += cursor.rowcount
                    db.execute("""
                        UPDATE application_workflow_steps
                        SET position = ?, title = ?
                        WHERE vacancy_id = ? AND step_key = ?
                    """, (position, step.title, vacancy["id"], step.key))
            return len(vacancies), inserted

    def list_application_workflow(
        self, source: str | None = None, source_id: str | None = None,
    ) -> list[sqlite3.Row]:
        self.initialize()
        where, params = [], []
        if source:
            where.append("v.source = ?")
            params.append(source)
        if source_id:
            where.append("v.source_id = ?")
            params.append(source_id)
        clause = "WHERE " + " AND ".join(where) if where else ""
        with self.connect() as db:
            return list(db.execute(f"""
                SELECT v.source, v.source_id, v.company, v.title,
                       w.step_key, w.position, w.title AS step_title,
                       w.state, w.note, w.updated_at
                FROM application_workflow_steps w
                JOIN vacancies v ON v.id = w.vacancy_id
                {clause}
                ORDER BY v.score DESC, v.company, w.position
            """, params))

    def set_application_workflow_step(
        self, source: str, source_id: str, step_key: str, state: str, note: str = "",
    ) -> None:
        self.initialize()
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with self.connect() as db:
            cursor = db.execute("""
                UPDATE application_workflow_steps
                SET state = ?, note = ?, updated_at = ?
                WHERE vacancy_id = (
                    SELECT id FROM vacancies WHERE source = ? AND source_id = ?
                ) AND step_key = ?
            """, (state, note, now, source, source_id, step_key))
            if cursor.rowcount != 1:
                raise KeyError(f"Шаг {step_key} для {source}:{source_id} не найден")
