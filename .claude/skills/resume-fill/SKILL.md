---
name: resume-fill
description: Fill and maintain resume.jsonl from the user's stories, projects, repo links or source files, then export to PDF/Markdown/text via resume.py. Use whenever the user wants to build, update, or regenerate their resume/CV.
---

# resume-fill

Turn what the user tells you (career stories, project descriptions, repo URLs,
existing files) into structured records in `resume.jsonl`, then render the
resume with `resume.py`.

## Workflow

1. **Gather.** Read whatever the user points at: their prose, a repo
   (`git log`, `README`, `pyproject.toml`/`package.json` for the stack),
   linked files, an old resume. Extract concrete facts — titles, companies,
   dates, metrics, tech.
2. **Write records.** Append/update lines in `resume.jsonl` (one JSON object
   per line). Do not rewrite untouched lines. Keep one `profile` line; append
   `experience`/`education`/`project`/`skill` lines in display order.
3. **Validate:** `uv run resume.py validate`
4. **Export:** `uv run resume.py export -f all` (or `-f pdf` / `md` / `txt`).

## JSONL schema

Each line is one object with a `type` discriminator. Blank lines and lines
starting with `#` are ignored. Omit fields you don't have — don't invent them.

```jsonl
{"type": "profile", "name": "...", "title": "Backend Engineer", "email": "...", "phone": "...", "location": "City, Country", "birthdate": "1997-03-15", "links": [{"label": "GitHub", "url": "https://..."}, {"label": "Telegram", "url": "https://t.me/..."}], "summary": "2-3 sentences, key skills + impact."}
{"type": "experience", "title": "Senior Engineer", "company": "Acme", "location": "City", "start": "2023", "end": "present", "highlights": ["Action + metric.", "Action + metric."]}
{"type": "education", "degree": "BSc Computer Science", "institution": "University", "location": "City", "start": "2017", "end": "2021"}
{"type": "project", "name": "rtk", "url": "https://github.com/...", "description": "One line.", "highlights": ["Notable result."]}
{"type": "skill", "category": "Languages", "items": ["Python", "Go", "SQL"]}
```

Field notes:
- `profile`: exactly one line. `summary` is the text under the Summary heading.
  Age: prefer `birthdate` (`YYYY-MM-DD`, computed at render with Russian
  pluralization, never stale); or a literal `age` string if only the number is known.
- `links`: list of `{label, url}` (GitHub, Telegram, LinkedIn, site…). Rendered
  clickable in PDF and Markdown; plain `Label: url` in the text export.
- Header icons (envelope / phone / pin) and the `·` separator are added
  automatically in the PDF — no fields needed.
- A bottom contact block (email · phone · Telegram) is appended automatically
  in all formats; it reuses `email`, `phone`, and any `t.me` link.
- `experience` / `project`: `highlights` is a list of bullet strings.
- `skill`: group by `category`; `items` is a list. Omit `category` for a flat list.
- `start`/`end`: free-form strings (`"2023"`, `"Jan 2023"`, `"present"`).

## Writing rules

- **Bullets = action + result + metric.** "Cut p99 latency 40% by moving to
  async" beats "Worked on performance". Pull numbers from what the user gives;
  never fabricate metrics.
- **Match the user's language** (Russian or English) — the renderer is
  Unicode-safe.
- Keep `summary` to 2-3 sentences. 3-6 highlights per recent role, fewer for old ones.
- Mine repos for the real stack instead of guessing.

## Commands

```bash
uv run resume.py validate                 # check required fields
uv run resume.py export -f all            # pdf + md + txt next to resume.jsonl
uv run resume.py export -f pdf -o cv.pdf  # single format, custom path
uv run resume.py export -i other.jsonl -f md
```

Required fields: `profile.name`; each `experience` needs `title` + `company`;
each `education` needs `degree` or `institution`. `validate` reports the rest.
