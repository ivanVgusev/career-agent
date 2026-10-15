import re
from dataclasses import replace

from .models import Assessment


HIGH_VALUE = {
    "llm": 13, "rag": 12, "langchain": 9, "ai agent": 10, "ии-агент": 10,
    "prompt": 9, "промпт": 9, "чат-бот": 9, "chatbot": 9, "nlp": 8,
    "python": 8, "fastapi": 5, "rest api": 4, "docker": 4,
    "data analyst": 6, "аналитик данных": 6, "sql": 5,
}
TRAVEL_TERMS = ("авиа", "airline", "travel", "туризм", "авиабилет", "бронирован")
MANAGEMENT_TERMS = ("project manager", "product manager", "менеджер проектов", "продакт")
NEGATIVE_TERMS = (
    "5+ лет", "frontend", "react", "1с", "sap", "java developer", "golang", "c#",
    "разметчик данных", "аннотатор", "лингвист-переводчик",
)
TARGET_TITLE_TERMS = (
    "ai engineer", "ai developer", "llm", "rag", "nlp", "python", "data analyst",
    "аналитик данных", "системный аналитик", "чат-бот", "prompt", "промпт",
    "project manager", "product manager", "automation engineer",
)
SENIOR_TITLE_TERMS = (
    "middle", "senior", "sr.", "principal", "staff ", "lead ", "team lead", "teamlead",
    "тимлид", "head of", "director", "руководитель",
)
HARD_EXPERIENCE_PATTERNS = (
    r"(?:от|минимум|не менее)\s*[3-9]\s*(?:лет|год)",
    r"опыт(?:а| работы)?[^.\n]{0,30}\b[3-9]\s*(?:\+\s*)?(?:лет|год(?:а)?)",
    r"[3-9]\s*\+\s*(?:лет|years?)",
    r"(?:at least|minimum)\s*[3-9]\s*years?",
    r"(?:experience|commercial experience)[^.\n]{0,30}\b[3-9]\s*(?:\+\s*)?years?",
)
OFF_TARGET_TITLE_TERMS = (
    "sales", "customer success", "account executive", "copywriter", "marketing lead",
    "recruiter", "talent acquisition", "support specialist", "office assistant",
)


def assess_text(text: str, schedule_id: str | None, experience_id: str | None, archived: bool) -> Assessment:
    text = text.lower().replace("ё", "е")
    reasons: list[str] = []
    warnings: list[str] = []
    score = 10
    matched = []
    for term, points in HIGH_VALUE.items():
        if term in text:
            score += points
            matched.append(term)
    if matched:
        reasons.append("Ключевые совпадения: " + ", ".join(matched[:8]))

    if any(term in text for term in TRAVEL_TERMS):
        score += 18
        reasons.append("Приоритетный домен: авиация или travel-tech")
        direction = "Авиация/Travel"
    elif any(term in text for term in ("llm", "rag", "nlp", "промпт", "чат-бот")):
        direction = "AI/LLM"
    elif any(term in text for term in MANAGEMENT_TERMS):
        direction = "IT-менеджмент"
    else:
        direction = "Python/Аналитика"

    if schedule_id == "remote":
        score += 15
        reasons.append("Явно указана удалённая работа")
    else:
        warnings.append("Удалённая работа не подтверждена")
    if experience_id == "noExperience":
        score += 8
        reasons.append("Можно без опыта")
    elif experience_id == "between1And3":
        score += 6
        reasons.append("Требуемый опыт: 1–3 года")
    elif experience_id in {"between3And6", "moreThan6"}:
        score -= 30
        warnings.append("Требуется более трёх лет опыта")

    negatives = [term for term in NEGATIVE_TERMS if term in text]
    if negatives:
        score -= min(36, len(negatives) * 12)
        warnings.append("Стоп-факторы: " + ", ".join(negatives[:5]))
    if archived:
        score = 0
        warnings.append("Вакансия в архиве")
    hard_experience = any(re.search(pattern, text) for pattern in HARD_EXPERIENCE_PATTERNS)
    if hard_experience:
        score -= 35
        warnings.append("В тексте требуется минимум три года опыта")
    rejected = (
        schedule_id != "remote"
        or experience_id in {"between3And6", "moreThan6"}
        or hard_experience
    )
    return Assessment(max(0, min(100, score)), direction, reasons, warnings, rejected)


def adjust_for_title(assessment: Assessment, title: str) -> Assessment:
    normalized = title.lower().replace("ё", "е")
    score = assessment.score
    reasons = list(assessment.reasons)
    warnings = list(assessment.warnings)
    if any(term in normalized for term in TARGET_TITLE_TERMS):
        score += 12
        reasons.append("Целевая формулировка в названии позиции")
    senior_title = any(term in normalized for term in SENIOR_TITLE_TERMS)
    if senior_title:
        score -= 28
        warnings.append("Высокий уровень позиции указан в названии")
    if any(term in normalized for term in OFF_TARGET_TITLE_TERMS):
        score -= 35
        warnings.append("Название позиции относится к неприоритетному направлению")
    return replace(
        assessment, score=max(0, min(100, score)), reasons=reasons, warnings=warnings,
        rejected=assessment.rejected or senior_title,
    )
