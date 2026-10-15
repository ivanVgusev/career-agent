import re
from datetime import datetime
from typing import Any

import httpx

from ..domain.models import Vacancy
from ..domain.scoring import adjust_for_title, assess_text
from .hh import html_to_text


class SourceError(RuntimeError):
    pass


def _matches(queries: list[str], *values: str) -> bool:
    if not queries:
        return True
    haystack = " ".join(values).lower().replace("ё", "е")
    for query in queries:
        normalized = query.lower().replace("ё", "е")
        if normalized in haystack:
            return True
        tokens = [token for token in re.findall(r"[a-zа-я0-9+#.]+", normalized) if len(token) >= 3]
        if any(token in haystack for token in tokens):
            return True
    return False


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if item is not None) or default
    return str(value)


def _remote_assessment(text: str, title: str, eligibility: str = ""):
    assessment = adjust_for_title(assess_text(text, "remote", None, False), title)
    if eligibility:
        assessment.warnings.append(f"Географическая доступность: {eligibility}")
    return assessment


class JSONClient:
    def __init__(self, timeout: float = 30):
        self.client = httpx.Client(
            timeout=timeout, follow_redirects=True,
            headers={"User-Agent": "local-career-agent/0.1", "Accept": "application/json"},
        )

    def get(self, url: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None):
        try:
            response = self.client.get(url, params=params, headers=headers)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise SourceError(f"Ошибка источника {url}: {error}") from error


class RemotiveAdapter:
    name = "remotive"
    api_url = "https://remotive.com/api/remote-jobs"

    def __init__(self, client: JSONClient | None = None):
        self.client = client or JSONClient()

    def search(self, queries: list[str], limit: int) -> list[Vacancy]:
        payload = self.client.get(self.api_url)
        result = []
        for raw in payload.get("jobs", []):
            description = html_to_text(raw.get("description"))
            title, company = raw.get("title", ""), raw.get("company_name", "")
            if not _matches(queries, title, description, " ".join(raw.get("tags") or [])):
                continue
            eligibility = raw.get("candidate_required_location") or "не указана"
            assessment = _remote_assessment(f"{title} {description}", title, eligibility)
            result.append(Vacancy(
                source=self.name, source_id=str(raw["id"]), company=company.strip() or "Не указан",
                title=title or "Без названия", url=raw.get("url") or "",
                source_status="Активна", checked_at=datetime.now().astimezone().isoformat(timespec="seconds"),
                direction=assessment.direction, job_type=raw.get("job_type") or "Вакансия",
                work_format="Удалённая работа", salary=raw.get("salary") or "Не указана",
                score=assessment.score, area=eligibility, employment=raw.get("job_type") or "",
                published_at=raw.get("publication_date"), description=description,
                key_skills=raw.get("tags") or [], assessment=assessment,
                extra={"category": raw.get("category"), "attribution_required": True},
            ))
        return sorted(result, key=lambda item: item.score, reverse=True)[:limit]


class JobicyAdapter:
    name = "jobicy"
    api_url = "https://jobicy.com/api/v2/remote-jobs"

    def __init__(self, client: JSONClient | None = None, max_pages: int = 3):
        self.client = client or JSONClient()
        self.max_pages = max_pages

    def search(self, queries: list[str], limit: int) -> list[Vacancy]:
        result, cursor = [], None
        for _ in range(self.max_pages):
            params: dict[str, Any] = {"count": 200}
            if cursor:
                params["cursor"] = cursor
            payload = self.client.get(self.api_url, params=params)
            for raw in payload.get("jobs", []):
                description = html_to_text(raw.get("jobDescription"))
                title = _text(raw.get("jobTitle"))
                industry = raw.get("jobIndustry")
                industries = industry if isinstance(industry, list) else [industry] if industry else []
                if not _matches(queries, title, description, " ".join(industries)):
                    continue
                eligibility = _text(raw.get("jobGeo"), "не указана")
                assessment = _remote_assessment(f"{title} {description}", title, eligibility)
                job_type = _text(raw.get("jobType"), "Вакансия")
                result.append(Vacancy(
                    source=self.name, source_id=str(raw["id"]),
                    company=_text(raw.get("companyName"), "Не указан"), title=title or "Без названия",
                    url=_text(raw.get("url")), source_status="Активна в свежей выдаче",
                    checked_at=datetime.now().astimezone().isoformat(timespec="seconds"),
                    direction=assessment.direction, job_type=job_type,
                    work_format="Удалённая работа", score=assessment.score, area=eligibility,
                    employment=job_type, published_at=raw.get("pubDate"),
                    description=description, key_skills=industries, assessment=assessment,
                    extra={"job_level": raw.get("jobLevel"), "attribution_required": True},
                ))
            cursor = payload.get("nextCursor")
            if not cursor or not payload.get("hasMore"):
                break
        return sorted(result, key=lambda item: item.score, reverse=True)[:limit]


class ArbeitnowAdapter:
    name = "arbeitnow"
    api_url = "https://www.arbeitnow.com/api/job-board-api"

    def __init__(self, client: JSONClient | None = None, max_pages: int = 3):
        self.client = client or JSONClient()
        self.max_pages = max_pages

    def search(self, queries: list[str], limit: int) -> list[Vacancy]:
        result = []
        for page in range(1, self.max_pages + 1):
            payload = self.client.get(self.api_url, params={"page": page})
            for raw in payload.get("data", []):
                if not raw.get("remote"):
                    continue
                description = html_to_text(raw.get("description"))
                title = raw.get("title", "")
                tags = raw.get("tags") or []
                if not _matches(queries, title, description, " ".join(tags)):
                    continue
                location = raw.get("location") or "не указана"
                assessment = _remote_assessment(f"{title} {description}", title, location)
                result.append(Vacancy(
                    source=self.name, source_id=str(raw["slug"]),
                    company=raw.get("company_name") or "Не указан", title=title or "Без названия",
                    url=raw.get("url") or "", source_status="Активна",
                    checked_at=datetime.now().astimezone().isoformat(timespec="seconds"),
                    direction=assessment.direction,
                    job_type=", ".join(raw.get("job_types") or []) or "Вакансия",
                    work_format="Удалённая работа", score=assessment.score, area=location,
                    employment=", ".join(raw.get("job_types") or []),
                    published_at=raw.get("created_at"), description=description,
                    key_skills=tags, assessment=assessment,
                    extra={"visa_sponsorship": raw.get("visa_sponsorship"), "attribution_required": True},
                ))
            if not (payload.get("links") or {}).get("next"):
                break
        return sorted(result, key=lambda item: item.score, reverse=True)[:limit]


def build_public_adapters() -> dict[str, Any]:
    return {
        "remotive": RemotiveAdapter(),
        "jobicy": JobicyAdapter(),
        "arbeitnow": ArbeitnowAdapter(),
    }
