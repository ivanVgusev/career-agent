# Interview coach

The interview workflow stores recordings, transcripts and analyses locally. Git ignores every generated artifact.

## Transcription

Install local speech support if you do not run a compatible remote endpoint:

```bash
python -m pip install -e '.[speech]'
```

Run:

```bash
career-agent interviews transcribe interview.m4a 2026-01-15_example
```

Career Agent tries the endpoint in `config/career.json`. If its health check fails, it uses local `faster-whisper`.

The raw transcript appears in `interview-coach/transcripts/raw/`.

## Dialogue format

Create a reviewed Markdown dialogue in `interview-coach/transcripts/`:

```markdown
**Candidate:** First answer.

**Interviewer:** Next question.
```

## Speech metrics

```bash
career-agent interviews metrics interview-coach/transcripts/2026-01-15_example.md
```

The script measures word share, answer length and configured filler phrases. These are text metrics, not acoustic measurements.

By default, the script treats the first speaker as the candidate. Pass `--speaker Candidate` when the dialogue order or labels require an explicit choice.

Use `--raw` to count filler phrases in the raw transcript:

```bash
career-agent interviews metrics interview-coach/transcripts/2026-01-15_example.md --raw interview-coach/transcripts/raw/2026-01-15_example.txt
```
