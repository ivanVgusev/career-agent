import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ..adapters.hh import HHClient, HHError
from ..adapters.job_boards import SourceError, build_public_adapters
from ..domain.models import Vacancy
from ..exporters.excel import export_tracker
from ..exporters.markdown import export_vacancy
from ..paths import CONFIG_PATH, JOB_DIR, TRACKER_PATH
from ..repositories.sqlite import CareerRepository


class MigrationRequired(RuntimeError):
    pass


class JobService:
    def __init__(
        self, repository: CareerRepository, client: HHClient | None = None,
        adapters: dict[str, Any] | None = None,
    ):
        self.repository = repository
        self.client = client or HHClient()
        self.adapters = adapters if adapters is not None else build_public_adapters()
        self.search_config = json.loads((JOB_DIR / "hh_search.json").read_text(encoding="utf-8"))
        self.source_config = json.loads(CONFIG_PATH.read_text(encoding="utf-8")).get("job_sources", {})
        self.last_errors: dict[str, str] = {}
        self.skipped_cooldown: list[str] = []

    def ensure_writable(self) -> None:
        if TRACKER_PATH.exists() and not self.repository.get_metadata("legacy_migrated_at"):
            raise MigrationRequired(
                "Найден старый tracker.xlsx. Сначала выполните: python3 career.py migrate --apply"
            )

    def _save(self, vacancy: Vacancy) -> None:
        self.repository.upsert_vacancy(vacancy)
        export_vacancy(vacancy)

    def _search_hh(self, queries: list[str], limit: int) -> list[Vacancy]:
        config = self.search_config
        candidates: dict[str, dict[str, Any]] = {}
        for query in queries:
            for page in range(config.get("pages_per_query", 1)):
                result = self.client.search(
                    text=query, area=config.get("area", "113"),
                    schedule=config.get("schedule", "remote"),
                    experience=config.get("experience", []), period=config.get("period_days", 30),
                    per_page=config.get("per_page", 50), page=page,
                    order_by="publication_time", host="hh.ru",
                )
                for item in result.get("items", []):
                    candidates[str(item["id"])] = item
        found = []
        for item in list(candidates.values())[:limit]:
            try:
                found.append(self.client.normalize(self.client.vacancy(str(item["id"]))))
            except HHError as error:
                if "не найдена" not in str(error).lower():
                    raise
        return found

    def _default_sources(self) -> list[str]:
        return [name for name, config in self.source_config.items() if config.get("enabled")]

    def _cooldown_active(self, source: str, force: bool) -> bool:
        if force:
            return False
        hours = float(self.source_config.get(source, {}).get("cooldown_hours", 0))
        last_sync = self.repository.last_successful_sync(source)
        if not last_sync or hours <= 0:
            return False
        return datetime.fromisoformat(last_sync) + timedelta(hours=hours) > datetime.now().astimezone()

    def search(
        self, queries: list[str] | None = None, limit: int = 80,
        minimum_score: int | None = None, dry_run: bool = False,
        sources: list[str] | None = None, force: bool = False,
    ) -> list[Vacancy]:
        config = self.search_config
        if not dry_run:
            self.ensure_writable()
        queries = queries or config["queries"]
        minimum_score = minimum_score if minimum_score is not None else config["minimum_score"]
        sources = sources or self._default_sources()
        known = {"hh.ru", *self.adapters}
        unknown = set(sources) - known
        if unknown:
            raise ValueError("Неизвестные источники: " + ", ".join(sorted(unknown)))
        found: list[Vacancy] = []
        self.last_errors = {}
        self.skipped_cooldown = []
        for source in sources:
            if not dry_run and self._cooldown_active(source, force):
                self.skipped_cooldown.append(source)
                continue
            started_at = datetime.now().astimezone().isoformat(timespec="seconds")
            try:
                vacancies = (
                    self._search_hh(queries, limit)
                    if source == "hh.ru"
                    else self.adapters[source].search(queries, limit)
                )
                found.extend(vacancies)
                if not dry_run:
                    self.repository.record_connector_run(source, started_at, "success", len(vacancies))
            except (HHError, SourceError) as error:
                self.last_errors[source] = str(error)
                if not dry_run:
                    self.repository.record_connector_run(source, started_at, "error", error=str(error))
        if not dry_run:
            for vacancy in found:
                if not vacancy.assessment.rejected and vacancy.score >= minimum_score:
                    self._save(vacancy)
        found.sort(key=lambda item: item.score, reverse=True)
        if not dry_run:
            export_tracker(self.repository)
        return found

    def fetch(self, vacancy_id: str) -> Vacancy:
        self.ensure_writable()
        vacancy = self.client.normalize(self.client.vacancy(vacancy_id))
        self._save(vacancy)
        export_tracker(self.repository)
        return vacancy

    def _unavailable_from_row(self, row, status: str = "Недоступна") -> Vacancy:
        return Vacancy(
            source=row["source"], source_id=row["source_id"], company=row["company"],
            title=row["title"], url=row["url"], source_status=status,
            checked_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            direction=row["direction"], work_format=row["work_format"],
            salary=row["salary"], score=0, description=row["description"],
        )

    def refresh(self, sources: list[str] | None = None, force: bool = False) -> list[Vacancy]:
        self.ensure_writable()
        rows = self.repository.list_vacancies()
        sources = sources or self._default_sources()
        known = {"hh.ru", *self.adapters}
        unknown = set(sources) - known
        if unknown:
            raise ValueError("Неизвестные источники: " + ", ".join(sorted(unknown)))
        updated: list[Vacancy] = []
        self.last_errors = {}
        self.skipped_cooldown = []
        for source in sources:
            source_rows = [row for row in rows if row["source"] == source]
            if not source_rows:
                continue
            if self._cooldown_active(source, force):
                self.skipped_cooldown.append(source)
                continue
            started_at = datetime.now().astimezone().isoformat(timespec="seconds")
            updated_before = len(updated)
            try:
                if source == "hh.ru":
                    for row in source_rows:
                        try:
                            vacancy = self.client.normalize(self.client.vacancy(row["source_id"]))
                        except HHError as error:
                            if "не найдена" not in str(error).lower():
                                raise
                            vacancy = self._unavailable_from_row(row)
                        self._save(vacancy)
                        updated.append(vacancy)
                elif source in self.adapters:
                    snapshot = self.adapters[source].search([], 10000)
                    by_id = {vacancy.source_id: vacancy for vacancy in snapshot}
                    for row in source_rows:
                        vacancy = by_id.get(row["source_id"])
                        if vacancy:
                            self._save(vacancy)
                            updated.append(vacancy)
                        elif source == "remotive":
                            vacancy = self._unavailable_from_row(row)
                            self._save(vacancy)
                            updated.append(vacancy)
                self.repository.record_connector_run(
                    source, started_at, "success", len(updated) - updated_before,
                )
            except (HHError, SourceError) as error:
                self.last_errors[source] = str(error)
                self.repository.record_connector_run(source, started_at, "error", error=str(error))
        export_tracker(self.repository)
        return updated
