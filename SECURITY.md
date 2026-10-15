# Security and privacy

Career Agent processes employment history, contact details, applications and interview recordings. Keep those artifacts on your machine.

## Before publishing

Run `git status --short` and inspect every untracked file. The public repository should contain code, documentation and empty templates only.

Do not commit:

- `CANDIDATE.md` or completed profile templates
- resumes, cover letters and application kits
- SQLite databases, Excel trackers or exported vacancy cards
- recordings, transcripts, interview analyses or scoreboards
- `.env` files, credentials, private endpoints or network addresses

If private data enters Git history, removing the current file is insufficient. Rewrite the history before publishing and rotate any exposed credential.

## Reporting a vulnerability

Open a private security advisory in the repository hosting service. Do not include personal candidate data in a public issue.
