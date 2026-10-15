# Vacancy search

Use the CLI for public sources and save only vacancies that pass the configured threshold.

```bash
career-agent jobs search --dry-run --limit 20
career-agent jobs search
career-agent jobs refresh
career-agent jobs list
```

Search phrases and HH.ru filters live in `hh_search.json`. Connector switches and cooldowns live in `../config/career.json`.

The automatic score is a first-pass filter. Before recommending a vacancy, read its complete saved description and check required experience, location, work authorization, schedule and seniority against `../CANDIDATE.md`.

Do not turn a missing requirement into a claimed skill. Record the gap and let the user decide whether to apply.

Store generated artifacts in the ignored directories:

- vacancy cards: `vacancies/`
- adapted resumes: `resumes-adapted/`
- cover letters: `cover-letters/`
- application packages: `application-kits/`
