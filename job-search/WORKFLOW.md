# Application workflow

The workflow applies to vacancies with the status `Рассматриваю`. Its state lives in `data/career.db`.

```bash
career-agent jobs workflow init --source <source> --source-id <id>
career-agent jobs workflow list --source <source> --source-id <id>
career-agent jobs workflow set <source> <id> <step> <state> --note "verifiable note"
```

States: `todo`, `in_progress`, `blocked`, `done`, `skipped`.

## Steps

1. `verify_source`: confirm that the vacancy is active and verify its date, location, schedule and restrictions.
2. `analyze_vacancy`: separate required skills, optional skills, responsibilities and rejection conditions.
3. `evidence_matrix`: map every important requirement to evidence in `../CANDIDATE.md`.
4. `adapt_resume`: write an adapted resume using verified facts only.
5. `ats_review`: run the ATS check and review terminology by hand.
6. `cover_letter`: connect two or three verified facts to the role's work.
7. `style_review`: remove filler and repeated claims without changing facts.
8. `application_kit`: prepare the documents and interview notes requested by the user.
9. `user_review`: show the user the completed files, gaps and uncertain wording.
10. `submit`: proceed only after explicit user approval, then record the date and status.
11. `follow_up`: prepare a short follow-up if the user requests one.
12. `interview_prep`: prepare evidence-based answers and questions.
13. `outcome`: record the result and useful feedback.

Do not mark a step `done` until its file or verifiable result exists.
