import html
import json
import re
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..domain.models import Vacancy
from ..domain.scoring import adjust_for_title, assess_text


class HHError(RuntimeError):
    pass


class _TextExtractor(HTMLParser):
    BLOCKS = {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4"}

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.parts.append("\n- " if tag == "li" else "\n" if tag in self.BLOCKS else "")

    def handle_endtag(self, tag):
        if tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)

    def text(self) -> str:
        value = html.unescape("".join(self.parts)).replace("\xa0", " ")
        value = re.sub(r"[ \t]+", " ", value)
        value = re.sub(r" *\n *", "\n", value)
        return re.sub(r"\n{3,}", "\n\n", value).strip()


def html_to_text(value: str | None) -> str:
    parser = _TextExtractor()
    parser.feed(value or "")
    return parser.text()


def salary_text(salary: dict[str, Any] | None) -> str:
    if not salary:
        return "Не указана"
    lower, upper = salary.get("from"), salary.get("to")
    if lower and upper:
        amount = f"{lower:,}–{upper:,}".replace(",", " ")
    elif lower:
        amount = f"от {lower:,}".replace(",", " ")
    else:
        amount = f"до {upper:,}".replace(",", " ")
    tax = "до вычета налогов" if salary.get("gross") else "на руки"
    return f"{amount} {salary.get('currency', '')}, {tax}".strip()


class HHClient:
    base_url = "https://api.hh.ru"

    def __init__(self, timeout: float = 20, retries: int = 3):
        self.timeout = timeout
        self.retries = retries

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        query = urlencode(params or {}, doseq=True)
        url = f"{self.base_url}{path}" + (f"?{query}" if query else "")
        request = Request(url, headers={
            "HH-User-Agent": "local-career-agent/0.1 (local personal tool)",
            "Accept": "application/json",
        })
        for attempt in range(self.retries):
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    return json.load(response)
            except HTTPError as error:
                if error.code == 404:
                    raise HHError("Вакансия не найдена или удалена") from error
                if error.code == 403:
                    server = error.headers.get("Server", "защитный слой")
                    raise HHError(f"Доступ к HH API отклонён: {server}, HTTP 403") from error
                if (error.code == 429 or error.code >= 500) and attempt + 1 < self.retries:
                    time.sleep(min(int(error.headers.get("Retry-After", 2 ** attempt)), 10))
                    continue
                raise HHError(f"HH API вернул HTTP {error.code}") from error
            except (URLError, TimeoutError) as error:
                if attempt + 1 < self.retries:
                    time.sleep(2 ** attempt)
                    continue
                raise HHError(f"Не удалось подключиться к HH API: {error}") from error
        raise HHError("Не удалось выполнить запрос к HH API")

    def search(self, **params: Any) -> dict[str, Any]:
        return self.get("/vacancies", params)

    def vacancy(self, vacancy_id: str) -> dict[str, Any]:
        return self.get(f"/vacancies/{vacancy_id}")

    def normalize(self, raw: dict[str, Any]) -> Vacancy:
        description = html_to_text(raw.get("description"))
        skills = [item.get("name") for item in raw.get("key_skills") or [] if item.get("name")]
        text = " ".join([raw.get("name", ""), description, *skills])
        schedule = raw.get("schedule") or {}
        experience = raw.get("experience") or {}
        assessment = adjust_for_title(assess_text(
            text, schedule.get("id"), experience.get("id"), bool(raw.get("archived")),
        ), raw.get("name", ""))
        employer = raw.get("employer") or {}
        checked_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        vacancy_id = str(raw["id"])
        return Vacancy(
            source="hh.ru", source_id=vacancy_id,
            company=employer.get("name") or "Не указан",
            title=raw.get("name") or "Без названия",
            url=raw.get("alternate_url") or f"https://hh.ru/vacancy/{vacancy_id}",
            source_status="Закрыта" if raw.get("archived") else "Активна",
            checked_at=checked_at, direction=assessment.direction,
            work_format=schedule.get("name") or "Не указан",
            salary=salary_text(raw.get("salary")), score=assessment.score,
            area=(raw.get("area") or {}).get("name") or "",
            employment=(raw.get("employment") or {}).get("name") or "",
            experience=experience.get("name") or "", published_at=raw.get("published_at"),
            description=description, key_skills=skills, assessment=assessment,
            extra={"schedule_id": schedule.get("id"), "experience_id": experience.get("id")},
        )
