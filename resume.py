"""JSONL-driven resume generator.

Read resume data from a JSONL file (one record per line, discriminated by
the ``type`` field) and export it to PDF, Markdown or plain text.

Usage:
    uv run resume.py export --input resume.jsonl --format all
    uv run resume.py export -f pdf -o out/cv.pdf
    uv run resume.py validate

The JSONL schema is documented in .claude/skills/resume-fill/SKILL.md or .pi/skills/resume-fill/SKILL.md
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

# --- font discovery (need a Cyrillic-capable TTF for the PDF) ----------------

# (regular, bold, italic) candidates, first existing wins.
_FONT_CANDIDATES = [
    (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Italic.ttf",
    ),
    (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
    ),
    (
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf",
    ),
]

# Palette pulled from the reference template.
NAVY = (31, 45, 77)
GRAY = (107, 114, 128)
RULE = (160, 174, 192)
BLACK = (33, 37, 41)


# --- data loading ------------------------------------------------------------


class ResumeData:
    """Records grouped by ``type``, preserving file order within each group."""

    def __init__(self) -> None:
        self.profile: dict = {}
        self.experience: list[dict] = []
        self.education: list[dict] = []
        self.projects: list[dict] = []
        self.skills: list[dict] = []


def load(path: Path) -> ResumeData:
    if not path.exists():
        raise SystemExit(f"Input not found: {path}")

    data = ResumeData()
    bucket = {
        "experience": data.experience,
        "education": data.education,
        "project": data.projects,
        "skill": data.skills,
    }

    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as e:
            raise SystemExit(f"{path}:{n}: invalid JSON: {e}")
        rtype = rec.get("type")
        if rtype == "profile":
            data.profile = rec
        elif rtype in bucket:
            bucket[rtype].append(rec)
        else:
            raise SystemExit(f"{path}:{n}: unknown type {rtype!r}")

    return data


def validate(path: Path) -> list[str]:
    """Return a list of human-readable problems (empty == valid)."""
    data = load(path)
    problems: list[str] = []
    if not data.profile:
        problems.append("missing 'profile' record")
    elif not data.profile.get("name"):
        problems.append("profile has no 'name'")
    for i, e in enumerate(data.experience):
        if not e.get("title") or not e.get("company"):
            problems.append(f"experience #{i + 1}: needs 'title' and 'company'")
    for i, e in enumerate(data.education):
        if not e.get("degree") and not e.get("institution"):
            problems.append(f"education #{i + 1}: needs 'degree' or 'institution'")
    return problems


# --- shared formatting helpers ----------------------------------------------


def _dates(rec: dict) -> str:
    start, end = rec.get("start"), rec.get("end")
    if start and end:
        return f"{start} - {end}"
    return start or end or ""


def _meta_line(rec: dict) -> str:
    """'Location / Start - End' style subtitle."""
    parts = [rec.get("location"), _dates(rec)]
    return " / ".join(p for p in parts if p)


def _ru_years(n: int) -> str:
    """Russian plural for 'год/года/лет'."""
    if 11 <= n % 100 <= 14:
        word = "лет"
    elif n % 10 == 1:
        word = "год"
    elif 2 <= n % 10 <= 4:
        word = "года"
    else:
        word = "лет"
    return f"{n} {word}"


def _age(profile: dict) -> str:
    """Resolve age: literal 'age', else computed from 'birthdate' (YYYY-MM-DD)."""
    if profile.get("age"):
        return str(profile["age"])
    bd = profile.get("birthdate")
    if not bd:
        return ""
    try:
        b = date.fromisoformat(bd)
    except ValueError:
        return ""
    today = date.today()
    years = today.year - b.year - ((today.month, today.day) < (b.month, b.day))
    return _ru_years(years)


def _contact_plain(profile: dict) -> list[str]:
    """Non-link contact items (email, phone, location, age)."""
    items = [
        profile.get("email"),
        profile.get("phone"),
        profile.get("location"),
        _age(profile),
    ]
    return [i for i in items if i]


def _links(profile: dict) -> list[tuple[str, str]]:
    """(label, url) pairs from profile.links, e.g. GitHub, Telegram."""
    out = []
    for link in profile.get("links", []):
        url = link.get("url")
        if url:
            out.append((link.get("label") or url, url))
    return out


def _contacts(profile: dict) -> list[str]:
    """Flat plain-text contact line (used by the txt renderer)."""
    items = list(_contact_plain(profile))
    for label, url in _links(profile):
        items.append(f"{label}: {url}" if label != url else url)
    return items


def _footer_items(profile: dict) -> list[tuple[str | None, str, str | None]]:
    """Reachable contacts repeated at the bottom: (icon, text, url).

    email + phone + Telegram (any t.me link).
    """
    items: list[tuple[str | None, str, str | None]] = []
    if profile.get("email"):
        items.append(("email", profile["email"], None))
    if profile.get("phone"):
        items.append(("phone", profile["phone"], None))
    for label, url in _links(profile):
        if label.lower() == "telegram" or "t.me/" in url:
            items.append((None, label, url))
    return items


# --- plain text renderer -----------------------------------------------------


def render_text(d: ResumeData) -> str:
    out: list[str] = []
    p = d.profile
    name = p.get("name", "Full name")
    out.append(name)
    if p.get("title"):
        out.append(p["title"])
    contacts = _contacts(p)
    if contacts:
        out.append("   ".join(contacts))

    def section(title: str) -> None:
        out.append("")
        out.append(f"{title}:")

    if p.get("summary"):
        section("О себе")
        out.append(p["summary"])

    if d.experience:
        section("Опыт работы")
        for e in d.experience:
            out.append("")
            out.append(f"{e.get('title', '')} / {e.get('company', '')}".strip(" /"))
            meta = _meta_line(e)
            if meta:
                out.append(meta)
            for h in e.get("highlights", []):
                out.append(f"  - {h}")

    if d.projects:
        section("Проекты")
        for pr in d.projects:
            out.append("")
            head = pr.get("name", "")
            if pr.get("url"):
                head = f"{head} ({pr['url']})"
            out.append(head)
            meta = _meta_line(pr)
            if meta:
                out.append(meta)
            if pr.get("description"):
                out.append(pr["description"])
            for h in pr.get("highlights", []):
                out.append(f"  - {h}")

    if d.education:
        section("Образование")
        for e in d.education:
            out.append("")
            out.append(
                f"{e.get('degree', '')} / {e.get('institution', '')}".strip(" /")
            )
            meta = _meta_line(e)
            if meta:
                out.append(meta)

    if d.skills:
        section("Навыки")
        for s in d.skills:
            items = ", ".join(s.get("items", []))
            if s.get("category"):
                out.append(f"{s['category']}: {items}")
            else:
                out.append(items)

    footer = _footer_items(p)
    if footer:
        section("Контакты")
        parts = [f"{text}: {url}" if url else text for _, text, url in footer]
        out.append("   ".join(parts))

    return "\n".join(out).rstrip() + "\n"


# --- markdown renderer -------------------------------------------------------


def render_markdown(d: ResumeData) -> str:
    out: list[str] = []
    p = d.profile
    out.append(f"# {p.get('name', 'Full name')}")
    if p.get("title"):
        out.append(f"**{p['title']}**")
    contacts = _contact_plain(p) + [f"[{label}]({url})" for label, url in _links(p)]
    if contacts:
        out.append("")
        out.append("   ".join(contacts))

    if p.get("summary"):
        out.append("\n## О себе\n")
        out.append(p["summary"])

    if d.experience:
        out.append("\n## Опыт работы")
        for e in d.experience:
            out.append(
                f"\n### {e.get('title', '')} / {e.get('company', '')}".rstrip(" /")
            )
            meta = _meta_line(e)
            if meta:
                out.append(f"*{meta}*")
            for h in e.get("highlights", []):
                out.append(f"- {h}")

    if d.projects:
        out.append("\n## Проекты")
        for pr in d.projects:
            name = pr.get("name", "")
            head = f"[{name}]({pr['url']})" if pr.get("url") else name
            out.append(f"\n### {head}")
            meta = _meta_line(pr)
            if meta:
                out.append(f"*{meta}*")
            if pr.get("description"):
                out.append(pr["description"])
            for h in pr.get("highlights", []):
                out.append(f"- {h}")

    if d.education:
        out.append("\n## Образование")
        for e in d.education:
            out.append(
                f"\n### {e.get('degree', '')} / {e.get('institution', '')}".rstrip(" /")
            )
            meta = _meta_line(e)
            if meta:
                out.append(f"*{meta}*")

    if d.skills:
        out.append("\n## Навыки\n")
        for s in d.skills:
            items = ", ".join(s.get("items", []))
            if s.get("category"):
                out.append(f"- **{s['category']}:** {items}")
            else:
                out.append(f"- {items}")

    footer = _footer_items(p)
    if footer:
        out.append("\n---\n")
        parts = [f"[{text}]({url})" if url else text for _, text, url in footer]
        out.append("**Контакты:** " + "   ".join(parts))

    return "\n".join(out).rstrip() + "\n"


# --- pdf renderer ------------------------------------------------------------


def _setup_font(pdf) -> str:
    """Register a Unicode TTF; return its family name. Fall back to Helvetica."""
    for regular, bold, italic in _FONT_CANDIDATES:
        if Path(regular).exists():
            pdf.add_font("body", "", regular)
            if Path(bold).exists():
                pdf.add_font("body", "B", bold)
            if Path(italic).exists():
                pdf.add_font("body", "I", italic)
            return "body"
    sys.stderr.write(
        "warning: no Unicode TTF found, falling back to Helvetica "
        "(Cyrillic will not render in the PDF)\n"
    )
    return "Helvetica"


# Material Design icon outlines (viewBox 0 0 24 24), rendered as scalable SVG.
ICON_PATHS = {
    "email": "M20 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z",
    "phone": "M6.62 10.79c1.44 2.83 3.76 5.14 6.59 6.59l2.2-2.2c.27-.27.67-.36 1.02-.24 1.12.37 2.33.57 3.57.57.55 0 1 .45 1 1V20c0 .55-.45 1-1 1-9.39 0-17-7.61-17-17 0-.55.45-1 1-1h3.5c.55 0 1 .45 1 1 0 1.25.2 2.45.57 3.57.11.35.03.74-.25 1.02l-2.2 2.2z",
    "location": "M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z",
}
# Icons are square (24x24 viewBox), so width == height == size.
ICON_W = {k: 1.0 for k in ICON_PATHS}
# Per-glyph horizontal nudge (mm) so each visible left edge lands on the text
# column — the email envelope fills its viewBox and would otherwise protrude.
ICON_DX = {"email": 0.9, "phone": -0.2, "location": 0.9}


def _draw_icon(pdf, kind: str, x: float, y: float, size: float, color) -> float:
    """Draw a navy Material contact glyph at top-left (x, y); return its width (mm)."""
    from fpdf.svg import SVGObject

    hexcol = "#%02X%02X%02X" % tuple(color)
    # SVG width/height are unitless (parsed as px = 1/72"); scale by pdf.k to get mm.
    px = size * pdf.k
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{px}" height="{px}" '
        f'viewBox="0 0 24 24"><path fill="{hexcol}" d="{ICON_PATHS[kind]}"/></svg>'
    )
    sx, sy = pdf.x, pdf.y
    SVGObject(svg).draw_to_page(pdf, x=x, y=y)
    pdf.set_xy(sx, sy)  # SVG drawing may move the cursor; restore it
    return size


def render_pdf(d: ResumeData, path: Path) -> None:
    from fpdf import FPDF
    from fpdf.enums import MethodReturnValue

    pdf = FPDF(format="A4", unit="mm")
    pdf.set_margins(18, 16, 18)
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.add_page()
    font = _setup_font(pdf)
    width = pdf.epw  # effective page width

    def heading(title: str) -> None:
        pdf.ln(3)
        pdf.set_font(font, "B", 14)
        pdf.set_text_color(*NAVY)
        pdf.cell(0, 7, title, new_x="LMARGIN", new_y="NEXT")
        y = pdf.get_y()
        pdf.set_draw_color(*RULE)
        pdf.set_line_width(0.3)
        pdf.line(pdf.l_margin, y, pdf.l_margin + width, y)
        pdf.ln(2)

    p = d.profile

    # Header: name + contacts.
    pdf.set_font(font, "B", 26)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 12, p.get("name", "Full name"), new_x="LMARGIN", new_y="NEXT")
    if p.get("title"):
        pdf.set_font(font, "", 12)
        pdf.set_text_color(*GRAY)
        pdf.cell(0, 6, p["title"], new_x="LMARGIN", new_y="NEXT")
    icon_size, gap, line_h, sep = 3.2, 1.0, 5.2, "      "
    right = pdf.l_margin + width

    def _item_w(kind: str | None, text: str) -> float:
        w = pdf.get_string_width(text)
        return w + icon_size * ICON_W[kind] + gap if kind else w

    def contact_row(
        items: list[tuple[str | None, str, str | None]], *, center: bool = False
    ) -> None:
        """Render 'icon text · icon text · …'; wrap when left-aligned, no wrap when centered."""
        pdf.set_font(font, "", 10)
        sep_w = pdf.get_string_width(sep)
        sep_w = 4
        if center:
            total = sum(_item_w(k, t) for k, t, _ in items) + sep_w * (len(items) - 1)
            pdf.set_x(pdf.l_margin + max(0, (width - total) / 2))
        for i, (kind, text, url) in enumerate(items):
            if i:
                if not center and pdf.get_x() + sep_w + _item_w(kind, text) > right:
                    pdf.ln(line_h)
                else:
                    pdf.set_text_color(*GRAY)
                    pdf.cell(sep_w, line_h, sep, align="C")
            if kind:
                _draw_icon(
                    pdf,
                    kind,
                    pdf.get_x() + ICON_DX.get(kind, 0),
                    pdf.get_y() + (line_h - icon_size) / 2 - 0.1,
                    icon_size,
                    NAVY,
                )
                pdf.set_x(pdf.get_x() + icon_size * ICON_W[kind] + gap)
            tw = pdf.get_string_width(text)
            if url:
                pdf.set_text_color(*NAVY)
                pdf.set_font(font, "U", 10)
                pdf.cell(tw, line_h, text, link=url)
                pdf.set_font(font, "", 10)
            else:
                pdf.set_text_color(*GRAY)
                pdf.cell(tw, line_h, text)

    # Line 1: reachable contacts (email, phone, links). Line 2: age + geo.
    line1: list[tuple[str | None, str, str | None]] = []
    if p.get("email"):
        line1.append(("email", p["email"], None))
    if p.get("phone"):
        line1.append(("phone", p["phone"], None))
    for label, url in _links(p):
        line1.append((None, label, url))

    line2: list[tuple[str | None, str, str | None]] = []
    if p.get("location"):
        line2.append(("location", p["location"], None))
    if _age(p):
        line2.append((None, _age(p), None))

    for row in (line1, line2):
        if row:
            pdf.ln(1)
            contact_row(row)
            pdf.ln(line_h)
            pdf.set_x(pdf.l_margin)

    if p.get("summary"):
        heading("О себе")
        pdf.set_font(font, "", 10.5)
        pdf.set_text_color(*GRAY)
        pdf.multi_cell(0, 5.2, p["summary"], new_x="LMARGIN", new_y="NEXT")

    def _bullet_text_x() -> float:
        """Left edge of the bullet text column (hanging-indent origin)."""
        pdf.set_font(font, "", 10.5)
        return pdf.l_margin + 2 + pdf.get_string_width("•  ")

    def _measure(text: str, style: str, size: float, line_h: float, left: float) -> float:
        """Height (mm) that multi_cell would consume for ``text`` at column ``left``."""
        x0 = pdf.get_x()
        pdf.set_x(left)
        pdf.set_font(font, style, size)
        lines = pdf.multi_cell(
            0, line_h, text, dry_run=True, output=MethodReturnValue.LINES
        )
        pdf.set_x(x0)
        return max(1, len(lines)) * line_h

    def entry(title_bold: str, meta: str) -> None:
        pdf.ln(1.5)
        pdf.set_font(font, "B", 11.5)
        pdf.set_text_color(*NAVY)
        pdf.multi_cell(0, 5.5, title_bold, new_x="LMARGIN", new_y="NEXT")
        if meta:
            pdf.set_font(font, "", 10)
            pdf.set_text_color(*GRAY)
            pdf.multi_cell(0, 5, meta, new_x="LMARGIN", new_y="NEXT")

    def keep_block(
        title_bold: str, meta: str, description: str, highlights: list[str]
    ) -> None:
        """Break to a new page if the header + first content line won't fit here.

        Prevents an orphaned header: if all highlights (or the description) would
        land on the next page, push the whole block there instead.
        """
        head = highlights[0] if highlights else description
        if not head:
            return
        left = pdf.l_margin
        need = 1.5  # entry()'s leading ln
        need += _measure(title_bold, "B", 11.5, 5.5, left)
        if meta:
            need += _measure(meta, "", 10, 5, left)
        if description:
            need += _measure(description, "", 10.5, 5, left)
        if highlights:
            need += _measure(highlights[0], "", 10.5, 5, _bullet_text_x())
        if pdf.will_page_break(need):
            pdf.add_page()

    def bullets(items: list[str]) -> None:
        line_h = 5
        pdf.set_font(font, "", 10.5)
        pdf.set_text_color(*BLACK)
        base_margin = pdf.l_margin
        bullet_x = base_margin + 2
        text_x = _bullet_text_x()
        for h in items:
            # Measure the bullet height at the text column, then keep it whole:
            # if it would straddle the page break, push the entire item to the
            # next page instead of splitting it (e.g. an orphaned last line).
            pdf.set_xy(text_x, pdf.get_y())
            lines = pdf.multi_cell(
                0, line_h, h, dry_run=True, output=MethodReturnValue.LINES
            )
            block_h = max(1, len(lines)) * line_h
            if pdf.will_page_break(block_h):
                pdf.add_page()

            y = pdf.get_y()
            pdf.set_xy(bullet_x, y)
            pdf.cell(text_x - bullet_x, line_h, "•")
            # Hanging indent: pin the left margin to the text column so wrapped
            # lines align under the first line instead of the bullet.
            pdf.set_left_margin(text_x)
            pdf.set_xy(text_x, y)
            pdf.multi_cell(0, line_h, h, new_x="LMARGIN", new_y="NEXT")
            pdf.set_left_margin(base_margin)
        pdf.set_x(base_margin)

    if d.experience:
        heading("Опыт работы")
        for e in d.experience:
            title = f"{e.get('title', '')} / {e.get('company', '')}".strip(" /")
            keep_block(title, _meta_line(e), "", e.get("highlights", []))
            entry(title, _meta_line(e))
            bullets(e.get("highlights", []))

    if d.projects:
        heading("Проекты")
        for pr in d.projects:
            name = pr.get("name", "")
            if pr.get("url"):
                name = f"{name}  ({pr['url']})"
            keep_block(
                name, _meta_line(pr), pr.get("description", ""), pr.get("highlights", [])
            )
            entry(name, _meta_line(pr))
            if pr.get("description"):
                pdf.set_font(font, "", 10.5)
                pdf.set_text_color(*GRAY)
                pdf.multi_cell(0, 5, pr["description"], new_x="LMARGIN", new_y="NEXT")
            bullets(pr.get("highlights", []))

    if d.education:
        heading("Образование")
        for e in d.education:
            entry(
                f"{e.get('degree', '')} / {e.get('institution', '')}".strip(" /"),
                _meta_line(e),
            )

    if d.skills:
        heading("Навыки")
        for s in d.skills:
            items = ", ".join(s.get("items", []))
            pdf.set_x(pdf.l_margin)
            if s.get("category"):
                pdf.set_font(font, "B", 10.5)
                pdf.set_text_color(*NAVY)
                pdf.cell(
                    pdf.get_string_width(s["category"] + ":  "),
                    5.4,
                    f"{s['category']}:  ",
                )
                pdf.set_font(font, "", 10.5)
                pdf.set_text_color(*BLACK)
                pdf.multi_cell(0, 5.4, items, new_x="LMARGIN", new_y="NEXT")
            else:
                pdf.set_font(font, "", 10.5)
                pdf.set_text_color(*BLACK)
                pdf.multi_cell(0, 5.4, items, new_x="LMARGIN", new_y="NEXT")

    footer = _footer_items(p)
    if footer:
        foot_y = pdf.h - pdf.b_margin - line_h
        if foot_y > pdf.get_y() + 4:  # only if it doesn't collide with content
            pdf.set_draw_color(*RULE)
            pdf.set_line_width(0.3)
            pdf.line(pdf.l_margin, foot_y - 2, pdf.l_margin + width, foot_y - 2)
            pdf.set_y(foot_y)
            contact_row(footer, center=True)

    path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(path))


# --- cli ---------------------------------------------------------------------

RENDERERS = {
    "txt": (render_text, ".txt"),
    "md": (render_markdown, ".md"),
}


def _export(args) -> int:
    inp = Path(args.input)
    data = load(inp)

    fmts = ["pdf", "md", "txt"] if args.format == "all" else [args.format]
    stem = Path(args.output) if args.output else inp.with_suffix("")

    for fmt in fmts:
        if fmt == "pdf":
            out = (
                stem.with_suffix(".pdf")
                if not args.output or len(fmts) > 1
                else Path(args.output)
            )
            render_pdf(data, out)
        else:
            render, ext = RENDERERS[fmt]
            out = (
                stem.with_suffix(ext)
                if not args.output or len(fmts) > 1
                else Path(args.output)
            )
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(render(data), encoding="utf-8")
        print(f"wrote {out}")
    return 0


def _validate(args) -> int:
    problems = validate(Path(args.input))
    if problems:
        print("invalid:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("ok")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="JSONL-driven resume generator")
    sub = parser.add_subparsers(dest="cmd", required=True)

    ex = sub.add_parser("export", help="render the resume")
    ex.add_argument("-i", "--input", default="resume.jsonl")
    ex.add_argument(
        "-f", "--format", choices=["pdf", "md", "txt", "all"], default="all"
    )
    ex.add_argument("-o", "--output", help="output path (or stem); default: input name")
    ex.set_defaults(func=_export)

    va = sub.add_parser("validate", help="check the JSONL for required fields")
    va.add_argument("-i", "--input", default="resume.jsonl")
    va.set_defaults(func=_validate)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
