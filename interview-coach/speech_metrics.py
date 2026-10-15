# Объективные метрики речи кандидата из отшлифованного диалога собеседования.
# Считается чисто на Python + nltk, БЕЗ LLM – чтобы цифры были воспроизводимы.
#
# Вход: transcripts/<имя>.md с метками говорящих (**Иван:**, **WB:** и т.п.).
# Метрики:
#   - доля слов кандидата от всех слов (прокси talk-time; не аудио-время!) – из диалога
#   - длина ответа: средняя / медианная / макс. число слов на реплику – из диалога
#   - доля слов-паразитов (% слов) + топ-нарушители
#
# Самопринижение/неуверенность НЕ считаются скриптом: по ключевым словам это
# слишком грубо («не знаю» часто не про неуверенность). Это оценивается
# контекстно при разборе (LLM), а не механически.
#
# ВАЖНО про паразитов: их надо мерить по ДОСЛОВНОМУ тексту.
# Если отшлифованный диалог вычищен от «ну/вот/то есть», метрика будет занижена.
# Поэтому:
#   - если диалог дословный (паразиты сохранены) – запускай без --raw, всё точно;
#   - если паразиты вырезаны – дай сырой ASR через --raw, оттуда возьмётся
#     дословная плотность паразитов (по всему диалогу, т.е. включая интервьюера –
#     помечается как «по всему диалогу»).
#
# Запуск:
#   .venv/bin/python speech_metrics.py "transcripts/<имя>.md"
#   .venv/bin/python speech_metrics.py "transcripts/<имя>.md" --raw "transcripts/raw/<имя>.txt"
#   (опционально: --speaker Иван)
#
# Результаты: печать отчёта + строка в speech_metrics.csv + analysis/<имя>_speech-metrics.md

import os
import re
import csv
import sys
import argparse
import datetime
import statistics

import nltk

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "speech_metrics.csv")
ANALYSIS_DIR = os.path.join(BASE_DIR, "analysis")

# Списки легко редактируются. Слова-паразиты (включая многословные).
# Намеренно НЕ включены спорные «просто», «вообще» – они часто осмысленны;
# раскомментируй, если хочешь их тоже ловить.
FILLERS = [
    "ну", "вот", "то есть", "как бы", "типа", "короче", "в общем",
    "собственно", "значит", "так сказать", "на самом деле", "скажем так",
    "как-то так", "прям", "получается", "условно", "допустим",
    # "просто", "вообще",
]

WORD_RE = re.compile(r"[а-яёa-z]", re.IGNORECASE)
TURN_RE = re.compile(r"^\*\*(.+?):\*\*\s*(.*)$")
STAGE_RE = re.compile(r"\*\(.*?\)\*")        # ремарки вида *(уточняет тон)*
MD_MARKS_RE = re.compile(r"[*_`>#|]")          # markdown-разметка


def clean_text(text: str) -> str:
    text = STAGE_RE.sub(" ", text)
    text = MD_MARKS_RE.sub(" ", text)
    return text


def normalize_speaker(raw: str) -> str:
    # «WB (Владислав)» -> «WB»
    return re.sub(r"\s*\(.*?\)", "", raw).strip()


def parse_dialogue(path: str):
    """Возвращает dict: speaker -> список реплик (строк)."""
    turns = {}
    current_speaker = None
    buffer = []

    def flush():
        if current_speaker is not None and buffer:
            turns.setdefault(current_speaker, []).append(" ".join(buffer).strip())

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            stripped = line.strip()
            m = TURN_RE.match(stripped)
            if m:
                flush()
                current_speaker = normalize_speaker(m.group(1))
                buffer = [clean_text(m.group(2))]
            elif stripped == "" or stripped.startswith("#") or stripped.startswith(">") \
                    or set(stripped) <= {"-"}:
                # пустая строка / заголовок / цитата / разделитель – завершает реплику
                flush()
                current_speaker = None
                buffer = []
            elif current_speaker is not None:
                buffer.append(clean_text(stripped))
        flush()
    return turns


def tokenize_words(text: str):
    try:
        tokens = nltk.word_tokenize(text, language="russian")
    except LookupError:
        tokens = re.findall(r"\w+", text)
    return [t for t in tokens if WORD_RE.search(t)]


def count_phrases(text_lower: str, phrases):
    """Считает вхождения фраз; возвращает (всего_слов_в_паразитах, {фраза: вхождения})."""
    per_phrase = {}
    total_words = 0
    for phrase in phrases:
        pattern = r"(?<![а-яёa-z])" + r"\s+".join(re.escape(w) for w in phrase.split()) \
                  + r"(?![а-яёa-z])"
        hits = re.findall(pattern, text_lower)
        if hits:
            per_phrase[phrase] = len(hits)
            total_words += len(hits) * len(phrase.split())
    return total_words, per_phrase


def find_candidate(turns, requested: str):
    if requested:
        for sp in turns:
            if requested.lower() in sp.lower():
                return sp
        raise SystemExit(f"Не нашёл говорящего {requested!r}. Доступные: {list(turns)}")
    return next(iter(turns))


def derive_name_and_date(path: str):
    name = os.path.splitext(os.path.basename(path))[0]
    m = re.match(r"(\d{4}-\d{2}-\d{2})", name)
    date = m.group(1) if m else datetime.date.today().isoformat()
    return name, date


def append_csv(row: dict):
    new_file = not os.path.exists(CSV_PATH)
    fields = ["date", "session", "speaker", "total_words", "talk_share_pct",
              "turns", "avg_words_per_turn", "median_words_per_turn",
              "max_words_per_turn", "filler_count", "filler_pct", "filler_scope"]
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if new_file:
            w.writeheader()
        w.writerow(row)


def build_report(name, date, speaker, m, top_fillers, filler_scope) -> str:
    lines = [
        f"# Метрики речи – {name}",
        "",
        f"Кандидат: **{speaker}** | дата: {date} | посчитано скриптом (nltk, без LLM)",
        "",
        "## Сводка",
        "",
        f"- Слов сказано кандидатом: **{m['total_words']}**",
        f"- Доля слов кандидата (прокси talk-time): **{m['talk_share_pct']}%** от всех слов в диалоге",
        f"- Реплик: **{m['turns']}**",
        f"- Длина ответа (слов): средняя **{m['avg_words_per_turn']}**, "
        f"медиана **{m['median_words_per_turn']}**, макс **{m['max_words_per_turn']}**",
        f"- Слова-паразиты ({filler_scope}): **{m['filler_pct']}%** слов ({m['filler_count']} шт.)",
        "",
    ]
    if top_fillers:
        lines += ["## Топ паразитов", ""]
        lines += [f"- «{p}» – {c}" for p, c in top_fillers]
        lines.append("")
    lines += [
        "## Как читать",
        "",
        "Доля слов – это прокси, а не аудио-время (длительности реплик нет). "
        "Цифры воспроизводимы и сравнимы между сессиями: смотри динамику паразитов "
        "от собеса к собесу. Самопринижение/неуверенность здесь не считаются – это "
        "оценивается контекстно в самом разборе.",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dialogue", help="путь к transcripts/<имя>.md")
    ap.add_argument(
        "--speaker",
        default="",
        help="метка кандидата; без параметра используется первый говорящий",
    )
    ap.add_argument("--raw", help="сырой ASR (.txt) – источник дословных паразитов/самопринижения")
    ap.add_argument("--no-save", action="store_true", help="не писать в CSV и не сохранять отчёт")
    args = ap.parse_args()

    turns = parse_dialogue(args.dialogue)
    if not turns:
        raise SystemExit("Не найдено реплик с метками вида **Имя:**")

    candidate = find_candidate(turns, args.speaker)
    cand_text = " ".join(turns[candidate])

    cand_words = tokenize_words(cand_text)
    all_words = tokenize_words(" ".join(t for sp in turns for t in turns[sp]))
    per_turn = [len(tokenize_words(t)) for t in turns[candidate] if tokenize_words(t)]
    total_words = len(cand_words)

    # Паразиты и самопринижение – по дословному тексту.
    if args.raw:
        with open(args.raw, encoding="utf-8") as f:
            filler_text = f.read()
        filler_scope = "по всему диалогу, дословно"
        filler_base = len(tokenize_words(filler_text))
    else:
        filler_text = cand_text
        filler_scope = "по репликам кандидата"
        filler_base = total_words
    filler_text_lower = filler_text.lower()

    filler_count, per_filler = count_phrases(filler_text_lower, FILLERS)

    m = {
        "total_words": total_words,
        "talk_share_pct": round(100 * total_words / len(all_words), 1) if all_words else 0,
        "turns": len(per_turn),
        "avg_words_per_turn": round(statistics.mean(per_turn), 1) if per_turn else 0,
        "median_words_per_turn": int(statistics.median(per_turn)) if per_turn else 0,
        "max_words_per_turn": max(per_turn) if per_turn else 0,
        "filler_count": filler_count,
        "filler_pct": round(100 * filler_count / filler_base, 1) if filler_base else 0,
        "filler_scope": filler_scope,
    }

    name, date = derive_name_and_date(args.dialogue)
    top_fillers = sorted(per_filler.items(), key=lambda x: -x[1])
    report = build_report(name, date, candidate, m, top_fillers, filler_scope)
    print(report)

    if not args.no_save:
        append_csv({"date": date, "session": name, "speaker": candidate, **m})
        os.makedirs(ANALYSIS_DIR, exist_ok=True)
        out = os.path.join(ANALYSIS_DIR, f"{name}_speech-metrics.md")
        with open(out, "w", encoding="utf-8") as f:
            f.write(report + "\n")
        print(f"\n[сохранено] {out}\n[CSV] {CSV_PATH}")


if __name__ == "__main__":
    main()
