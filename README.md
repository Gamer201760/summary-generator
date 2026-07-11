# resume

JSONL-driven генератор резюме. Данные — в `resume.jsonl`, экспорт в PDF / Markdown / текст одной командой.

## Установка

Нужен [uv](https://docs.astral.sh/uv/). Зависимости и Python (3.13) он подтянет сам.

```bash
git clone https://github.com/<you>/resume-generator.git
cd resume-generator
uv run resume.py validate
```

## Использование

```bash
uv run resume.py validate              # проверить обязательные поля
uv run resume.py export -f all         # pdf + md + txt рядом с resume.jsonl
uv run resume.py export -f pdf -o cv.pdf
uv run resume.py export -i other.jsonl -f md
```

## Данные

В репозитории `resume.jsonl` — **пример с вымышленными данными**. Замени его на свои.

Формат: один JSON-объект на строку, дискриминатор `type`:
`profile`, `experience`, `education`, `project`, `skill`.
Строки с `#` и пустые игнорируются. Полная схема — в `.claude/skills/resume-fill/SKILL.md`.

## Заполнение через ИИ-агента

Skill `resume-fill` (`.claude/skills/resume-fill/SKILL.md`) учит агента (Claude Code и совместимые)
собирать факты из рассказов, проектов, ссылок на репо и файлов и писать их в `resume.jsonl`.

## PDF и шрифты

PDF рендерится через `fpdf2`. Для кириллицы нужен Unicode TTF — скрипт сам
находит Arial (macOS) / DejaVu / Liberation (Linux). Если ничего нет, падает
на Helvetica (только латиница) с предупреждением.
