from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Assessment:
    score: int
    direction: str
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    rejected: bool = False


@dataclass
class Vacancy:
    source: str
    source_id: str
    company: str
    title: str
    url: str
    source_status: str
    checked_at: str
    direction: str = ""
    job_type: str = "Вакансия"
    work_format: str = ""
    salary: str = "Не указана"
    score: int = 0
    area: str = ""
    employment: str = ""
    experience: str = ""
    published_at: str | None = None
    description: str = ""
    key_skills: list[str] = field(default_factory=list)
    assessment: Assessment | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Vacancy":
        values = dict(payload)
        assessment = values.get("assessment")
        if isinstance(assessment, dict):
            values["assessment"] = Assessment(**assessment)
        return cls(**values)


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    backend: str
    model: str
