import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from .adapters.hh import HHClient
from .adapters.speech import LocalWhisperBackend, RemoteSpeachesBackend
from .config import load_settings
from .domain.workflow import APPLICATION_WORKFLOW, WORKFLOW_STATES
from .exporters.excel import export_tracker
from .exporters.markdown import export_vacancy
from .migration import LegacyMigrator
from .paths import DB_PATH, INTERVIEW_DIR
from .repositories.sqlite import CareerRepository
from .services.jobs import JobService
from .services.transcription import TranscriptionService


def _repository(args) -> CareerRepository:
    return CareerRepository(Path(args.db))


def command_init(args) -> int:
    repository = _repository(args)
    repository.initialize()
    print(f"База готова: {repository.path}")
    return 0


def command_migrate(args) -> int:
    migrator = LegacyMigrator(_repository(args))
    counts = migrator.apply() if args.apply else migrator.inspect()
    mode = "Перенесено" if args.apply else "Будет перенесено"
    print(f"{mode}: {json.dumps(counts, ensure_ascii=False)}")
    if not args.apply:
        print("Это был dry-run. Для миграции добавьте --apply.")
    return 0


def _jobs(args) -> JobService:
    return JobService(_repository(args), HHClient())


def command_jobs_search(args) -> int:
    service = _jobs(args)
    vacancies = service.search(
        args.query, args.limit, args.min_score, args.dry_run, args.source, args.force,
    )
    for vacancy in vacancies:
        marker = "отклонена" if vacancy.assessment.rejected else f"{vacancy.score}/100"
        print(f"[{vacancy.source}; {marker}] {vacancy.company} – {vacancy.title} | {vacancy.url}")
    for source in service.skipped_cooldown:
        print(f"[{source}] пропущен: действует интервал между синхронизациями")
    for source, error in service.last_errors.items():
        print(f"[{source}] ошибка: {error}", file=sys.stderr)
    return 1 if service.last_errors and not vacancies else 0


def command_jobs_fetch(args) -> int:
    match = re.search(r"(?:vacancy/)?(\d+)", args.vacancy)
    if not match:
        raise ValueError("Ожидался HH ID или ссылка на вакансию")
    vacancy = _jobs(args).fetch(match.group(1))
    print(f"Сохранено: {vacancy.company} – {vacancy.title}")
    return 0


def command_jobs_refresh(args) -> int:
    service = _jobs(args)
    updated = service.refresh(args.source, args.force)
    print(f"Обновлено: {len(updated)}")
    for source in service.skipped_cooldown:
        print(f"[{source}] пропущен: действует интервал между синхронизациями")
    for source, error in service.last_errors.items():
        print(f"[{source}] ошибка: {error}", file=sys.stderr)
    return 1 if service.last_errors and not updated else 0


def command_jobs_list(args) -> int:
    for row in _repository(args).list_vacancies():
        print(
            f"[{row['application_status']}; {row['source_status']}; {row['score']}/100] "
            f"{row['company']} – {row['title']} | {row['source']}:{row['source_id']}"
        )
    return 0


def command_jobs_status(args) -> int:
    repository = _repository(args)
    JobService(repository).ensure_writable()
    repository.set_application_status(args.source, args.source_id, args.status, args.comment)
    export_tracker(repository)
    print(f"Статус обновлён: {args.source}:{args.source_id} -> {args.status}")
    return 0


def command_jobs_source_copy(args) -> int:
    repository = _repository(args)
    vacancy = repository.mark_source_copy(args.source, args.source_id)
    path = export_vacancy(vacancy)
    export_tracker(repository)
    print(f"Карточка очищена до копии источника: {path}")
    return 0


def command_workflow_init(args) -> int:
    repository = _repository(args)
    vacancies, steps = repository.initialize_application_workflow(
        APPLICATION_WORKFLOW, args.source, args.source_id,
    )
    print(f"Pipeline создан: вакансий {vacancies}, новых шагов {steps}")
    return 0


def command_workflow_list(args) -> int:
    rows = _repository(args).list_application_workflow(args.source, args.source_id)
    current = None
    for row in rows:
        vacancy = (row["source"], row["source_id"])
        if vacancy != current:
            print(f"[{row['source']}:{row['source_id']}] {row['company']} – {row['title']}")
            current = vacancy
        note = f" | {row['note']}" if row["note"] else ""
        print(f"  {row['position']:02d}. [{row['state']}] {row['step_key']}: {row['step_title']}{note}")
    if not rows:
        print("Шаги pipeline не найдены")
    return 0


def command_workflow_set(args) -> int:
    if args.state not in WORKFLOW_STATES:
        raise ValueError("Состояние: " + ", ".join(sorted(WORKFLOW_STATES)))
    repository = _repository(args)
    repository.set_application_workflow_step(
        args.source, args.source_id, args.step, args.state, args.note,
    )
    print(f"Шаг обновлён: {args.source}:{args.source_id} {args.step} -> {args.state}")
    return 0


def command_transcribe(args) -> int:
    audio = Path(args.input).resolve()
    if not audio.is_file():
        raise FileNotFoundError(audio)
    output_name = Path(args.output_name).name
    settings = load_settings()
    service = TranscriptionService(
        RemoteSpeachesBackend(settings.speech), LocalWhisperBackend(settings.speech),
    )
    result = service.transcribe(audio)
    output_dir = INTERVIEW_DIR / "transcripts" / "raw"
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"{output_name}.txt"
    temporary = output.with_suffix(".txt.tmp")
    temporary.write_text(result.text, encoding="utf-8")
    temporary.replace(output)
    print(f"Готово: {output} | backend={result.backend} | model={result.model}")
    return 0


def command_metrics(args) -> int:
    interpreter = INTERVIEW_DIR / ".venv" / "bin" / "python"
    executable = str(interpreter) if interpreter.exists() else sys.executable
    command = [executable, str(INTERVIEW_DIR / "speech_metrics.py"), args.dialogue]
    if args.raw:
        command.extend(["--raw", args.raw])
    if args.speaker:
        command.extend(["--speaker", args.speaker])
    return subprocess.run(command, check=False).returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Единый CLI локальной career-системы")
    parser.add_argument("--db", default=str(DB_PATH), help="Путь к SQLite")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Инициализировать SQLite")
    init.set_defaults(func=command_init)
    migrate = commands.add_parser("migrate", help="Перенести старые хранилища")
    migrate.add_argument("--apply", action="store_true", help="Выполнить перенос; без флага только подсчёт")
    migrate.set_defaults(func=command_migrate)

    jobs = commands.add_parser("jobs", help="Вакансии и отклики")
    job_commands = jobs.add_subparsers(dest="jobs_command", required=True)
    search = job_commands.add_parser("search")
    search.add_argument("--query", action="append")
    search.add_argument(
        "--source", action="append",
        help="Источник: hh.ru, remotive, jobicy или arbeitnow; можно повторить",
    )
    search.add_argument("--limit", type=int, default=80)
    search.add_argument("--min-score", type=int)
    search.add_argument("--dry-run", action="store_true")
    search.add_argument("--force", action="store_true", help="Игнорировать интервал синхронизации")
    search.set_defaults(func=command_jobs_search)
    fetch = job_commands.add_parser("fetch")
    fetch.add_argument("vacancy")
    fetch.set_defaults(func=command_jobs_fetch)
    refresh = job_commands.add_parser("refresh")
    refresh.add_argument("--source", action="append")
    refresh.add_argument("--force", action="store_true")
    refresh.set_defaults(func=command_jobs_refresh)
    listing = job_commands.add_parser("list")
    listing.set_defaults(func=command_jobs_list)
    status = job_commands.add_parser("status")
    status.add_argument("source")
    status.add_argument("source_id")
    status.add_argument("status")
    status.add_argument("--comment", default="")
    status.set_defaults(func=command_jobs_status)
    source_copy = job_commands.add_parser(
        "source-copy", help="Удалить агентский анализ из карточки вакансии",
    )
    source_copy.add_argument("source")
    source_copy.add_argument("source_id")
    source_copy.set_defaults(func=command_jobs_source_copy)
    workflow = job_commands.add_parser("workflow", help="Pipeline подготовки и сопровождения отклика")
    workflow_commands = workflow.add_subparsers(dest="workflow_command", required=True)
    workflow_init = workflow_commands.add_parser("init", help="Создать шаги для рассматриваемых вакансий")
    workflow_init.add_argument("--source")
    workflow_init.add_argument("--source-id")
    workflow_init.set_defaults(func=command_workflow_init)
    workflow_list = workflow_commands.add_parser("list", help="Показать шаги")
    workflow_list.add_argument("--source")
    workflow_list.add_argument("--source-id")
    workflow_list.set_defaults(func=command_workflow_list)
    workflow_set = workflow_commands.add_parser("set", help="Изменить состояние шага")
    workflow_set.add_argument("source")
    workflow_set.add_argument("source_id")
    workflow_set.add_argument("step")
    workflow_set.add_argument("state", choices=sorted(WORKFLOW_STATES))
    workflow_set.add_argument("--note", default="")
    workflow_set.set_defaults(func=command_workflow_set)

    interviews = commands.add_parser("interviews", help="Собеседования")
    interview_commands = interviews.add_subparsers(dest="interview_command", required=True)
    transcribe = interview_commands.add_parser("transcribe")
    transcribe.add_argument("input")
    transcribe.add_argument("output_name")
    transcribe.set_defaults(func=command_transcribe)
    metrics = interview_commands.add_parser("metrics")
    metrics.add_argument("dialogue")
    metrics.add_argument("--raw")
    metrics.add_argument("--speaker", help="Метка кандидата в диалоге")
    metrics.set_defaults(func=command_metrics)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return args.func(args)
    except Exception as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        return 1
