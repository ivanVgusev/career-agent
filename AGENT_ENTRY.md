# Agent entry point

This repository is a local career workspace. Use the shortest route for the requested task.

| Task | Read first | Command |
| --- | --- | --- |
| Search for vacancies | `job-search/SEARCH_INSTRUCTIONS.md` | `career-agent jobs search` |
| Refresh saved vacancies | `CONNECTORS.md` | `career-agent jobs refresh` |
| List vacancies | nothing else | `career-agent jobs list` |
| Change application status | `job-search/WORKFLOW.md` | `career-agent jobs status <source> <source_id> <status>` |
| Prepare an application | `job-search/WORKFLOW.md`, then `job-search/ATS_GUIDE.md` | `career-agent jobs workflow list --source <source> --source-id <id>` |
| Transcribe an interview | `interview-coach/README.md` | `career-agent interviews transcribe <file> <name>` |
| Measure interview speech | `interview-coach/README.md` | `career-agent interviews metrics <dialogue>` |

## Sources of truth

- Candidate facts: `CANDIDATE.md`. Read it only for candidate-specific tasks.
- Vacancy and application state: `data/career.db`.
- `job-search/tracker.xlsx` and Markdown vacancy cards: generated views.
- Search settings: `job-search/hh_search.json`.
- Connectors and speech settings: `config/career.json`.
- Application workflow: `job-search/WORKFLOW.md`.

## Safety

- Use only facts present in `CANDIDATE.md` when writing application materials.
- Do not infer missing dates, skills, results or experience.
- Do not send an application or employer message without explicit approval.
- Open one selected vacancy at a time. Do not load the complete vacancy catalog into context.
- Keep local data and generated materials out of Git.
