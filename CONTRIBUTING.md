# Contributing

Create a focused branch, add tests for changed behavior and run:

```bash
python -m unittest discover -s tests -v
```

Do not use real candidate profiles, vacancies, interview transcripts or credentials in tests. Use synthetic names, URLs and records.

Keep network access in adapters, business rules in `career_agent/domain/`, persistence in `career_agent/repositories/` and orchestration in `career_agent/services/`.
