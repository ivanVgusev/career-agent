#!/usr/bin/env python3
"""Heuristic ATS compatibility check for a vacancy and an adapted resume."""

import argparse
import json
import re
from collections import Counter
from pathlib import Path


TOKEN_RE = re.compile(r"[a-zа-яё][a-zа-яё0-9+#.]{1,}", re.IGNORECASE)
STOP_WORDS = {
    "and", "are", "for", "from", "have", "into", "our", "the", "this", "with", "you",
    "будет", "быть", "ваш", "для", "или", "как", "команда", "который", "мы", "нам", "наш",
    "опыт", "работа", "работать", "свой", "также", "чтобы", "это",
}
SECTION_NAMES = {
    "summary": ("summary", "профиль", "обо мне"),
    "skills": ("skills", "навыки", "ключевые навыки", "технологии"),
    "experience": ("experience", "опыт", "опыт работы"),
    "education": ("education", "образование"),
}


def normalize(text):
    text = re.sub(r"https?://\S+", " ", text)
    return text.lower().replace("ё", "е")


def tokens(text):
    cleaned = (token.strip(".") for token in TOKEN_RE.findall(normalize(text)))
    return [token for token in cleaned if token and token not in STOP_WORDS]


def ranked_terms(vacancy, limit=35):
    counts = Counter(tokens(vacancy))
    first_position = {}
    for index, token in enumerate(tokens(vacancy)):
        first_position.setdefault(token, index)

    def score(item):
        term, count = item
        latin_or_tech = bool(re.search(r"[a-z+#.]", term))
        acronym = term.isascii() and len(term) <= 6
        boost = 2 if latin_or_tech else 0
        boost += 1 if acronym else 0
        return count * 3 + boost - first_position[term] / 10000

    candidates = ((term, count) for term, count in counts.items() if len(term) >= 3)
    return [term for term, _ in sorted(candidates, key=score, reverse=True)[:limit]]


def structural_warnings(resume):
    warnings = []
    lowered = normalize(resume)
    word_count = len(tokens(resume))

    if re.search(r"^\s*\|.+\|\s*$", resume, re.MULTILINE):
        warnings.append("Обнаружена Markdown-таблица. Не используйте таблицы для основного содержания.")
    if re.search(r"!\[[^]]*]\([^)]+\)", resume):
        warnings.append("Обнаружено изображение. Значимая информация должна дублироваться текстом.")
    if word_count < 180:
        warnings.append(f"Резюме очень короткое: примерно {word_count} значимых слов.")
    if word_count > 1100:
        warnings.append(f"Резюме длинное: примерно {word_count} значимых слов.")

    for canonical, variants in SECTION_NAMES.items():
        if not any(re.search(rf"^#+\s+{re.escape(name)}\s*$", lowered, re.MULTILINE) for name in variants):
            warnings.append(f"Не найден стандартный раздел: {canonical}.")

    repeated = [(term, count) for term, count in Counter(tokens(resume)).items() if count >= 12]
    if repeated:
        details = ", ".join(f"{term} ({count})" for term, count in sorted(repeated, key=lambda x: -x[1])[:5])
        warnings.append(f"Проверьте неестественные повторы: {details}.")

    return warnings


def analyze(vacancy, resume, limit=35):
    terms = ranked_terms(vacancy, limit)
    resume_terms = set(tokens(resume))
    matched = [term for term in terms if term in resume_terms]
    missing = [term for term in terms if term not in resume_terms]
    coverage = round(100 * len(matched) / len(terms)) if terms else 0
    return {
        "heuristic_coverage_percent": coverage,
        "matched_terms": matched,
        "missing_terms_to_review": missing,
        "warnings": structural_warnings(resume),
        "disclaimer": "Эвристика не воспроизводит конкретную ATS и не разрешает добавлять неподтвержденные навыки.",
    }


def markdown_report(result):
    matched = ", ".join(result["matched_terms"]) or "нет"
    missing = ", ".join(result["missing_terms_to_review"]) or "нет"
    warnings = result["warnings"] or ["Критических структурных рисков не найдено."]
    lines = [
        "# Отчёт ATS-проверки",
        "",
        f"Эвристическое покрытие терминов: {result['heuristic_coverage_percent']}%",
        "",
        f"Совпавшие термины: {matched}",
        "",
        f"Термины для ручной проверки: {missing}",
        "",
        "## Структура",
        "",
    ]
    lines.extend(f"- {warning}" for warning in warnings)
    lines.extend(["", result["disclaimer"]])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("vacancy", type=Path)
    parser.add_argument("resume", type=Path)
    parser.add_argument("--limit", type=int, default=35, help="Количество терминов для проверки")
    parser.add_argument("--json", action="store_true", help="Вывести JSON")
    args = parser.parse_args()

    vacancy = args.vacancy.read_text(encoding="utf-8")
    resume = args.resume.read_text(encoding="utf-8")
    result = analyze(vacancy, resume, max(1, args.limit))
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else markdown_report(result))


if __name__ == "__main__":
    main()
