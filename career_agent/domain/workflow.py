from dataclasses import dataclass


@dataclass(frozen=True)
class WorkflowStep:
    key: str
    title: str


APPLICATION_WORKFLOW = [
    WorkflowStep("verify_source", "Проверить актуальность, формат и ограничения"),
    WorkflowStep("analyze_vacancy", "Разобрать требования, задачи и стоп-факторы"),
    WorkflowStep("evidence_matrix", "Составить матрицу подтверждений из мастер-профиля"),
    WorkflowStep("adapt_resume", "Подготовить адаптированное резюме"),
    WorkflowStep("ats_review", "Проверить ATS, факты и читаемость"),
    WorkflowStep("cover_letter", "Подготовить сопроводительное письмо"),
    WorkflowStep(
        "style_review",
        "Проверить стиль резюме и письма без изменения фактов",
    ),
    WorkflowStep("application_kit", "Подготовить пакет отклика"),
    WorkflowStep("user_review", "Получить подтверждение пользователя"),
    WorkflowStep("submit", "Отправить отклик и зафиксировать дату"),
    WorkflowStep("follow_up", "Провести follow-up при отсутствии ответа"),
    WorkflowStep("interview_prep", "Подготовиться к интервью"),
    WorkflowStep("outcome", "Зафиксировать итог и обратную связь"),
]

WORKFLOW_STATES = {"todo", "in_progress", "blocked", "done", "skipped"}
