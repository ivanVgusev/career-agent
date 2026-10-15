# ATS review guide

Use this guide after selecting one vacancy and reading `../CANDIDATE.md`.

## Evidence first

Build a matrix with four columns:

```text
vacancy requirement | candidate evidence | resume section | decision
```

Use a requirement in the resume only when the profile contains direct evidence. Mark missing evidence as a gap.

## Resume adaptation

1. Put the target role and the most relevant verified experience near the top.
2. Reuse the vacancy's technical terms when they describe real candidate experience.
3. Move relevant projects and skills above unrelated material.
4. Keep dates, employers, titles and measured results unchanged.
5. Use plain headings such as Profile, Experience, Projects, Education and Skills.
6. Avoid tables, text boxes and information stored only in images.

Run the heuristic check:

```bash
python job-search/ats_check.py <vacancy.md> <resume.md>
```

Review every missing term by hand. A missing term is not permission to add an unsupported skill.
