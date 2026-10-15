import re
from pathlib import Path

from ..domain.models import Vacancy
from ..paths import VACANCIES_DIR


def _slug(value: str) -> str:
    value = re.sub(r"[^a-zа-яё0-9]+", "_", value.lower(), flags=re.IGNORECASE)
    return value.strip("_")[:70] or "vacancy"


def export_vacancy(vacancy: Vacancy, directory: Path = VACANCIES_DIR) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    assessment = vacancy.assessment
    reasons = assessment.reasons if assessment else []
    warnings = assessment.warnings if assessment else []
    summary = str(vacancy.extra.get("agent_summary") or "").strip()
    hiring_chance = vacancy.extra.get("hiring_chance")
    source_copy_only = bool(vacancy.extra.get("source_copy_only"))
    prefix = "hh" if vacancy.source == "hh.ru" else _slug(vacancy.source)
    path = directory / f"{prefix}_{vacancy.source_id}_{_slug(vacancy.company)}_{_slug(vacancy.title)}.md"
    content = [
        f"# {vacancy.company}: {vacancy.title}", "",
        f"Площадка: {vacancy.source}", "",
        f"Источник: {vacancy.url}", "",
        f"ID источника: `{vacancy.source_id}`", "",
        f"Статус источника: {vacancy.source_status}", "",
        f"Проверено: {vacancy.checked_at}", "",
        *(["## Краткое резюме", "", summary, ""] if summary and not source_copy_only else []),
        "## Условия", "",
        f"- Формат: {vacancy.work_format or 'Не указан'}",
        f"- Регион: {vacancy.area or 'Не указан'}",
        f"- Занятость: {vacancy.employment or 'Не указана'}",
        f"- Опыт: {vacancy.experience or 'Не указан'}",
        f"- Доход: {vacancy.salary}", "",
        *([] if source_copy_only else [
            "## Предварительная оценка", "",
            f"Оценка: {vacancy.score}/100", "",
            *([f"Шанс найма: {hiring_chance}/100", ""] if hiring_chance is not None else []),
            f"Направление: {vacancy.direction}", "",
            "### Совпадения", "",
            *(f"- {item}" for item in reasons),
            *( ["- Сильных совпадений не найдено"] if not reasons else [] ), "",
            "### Риски", "",
            *(f"- {item}" for item in warnings),
            *( ["- Явных стоп-факторов не найдено"] if not warnings else [] ), "",
        ]),
        "## Ключевые навыки из источника", "",
        ", ".join(vacancy.key_skills) or "Не указаны", "",
        "## Полное описание", "", vacancy.description or "Описание недоступно.", "",
    ]
    temporary = path.with_suffix(".md.tmp")
    temporary.write_text("\n".join(content), encoding="utf-8")
    temporary.replace(path)
    return path
