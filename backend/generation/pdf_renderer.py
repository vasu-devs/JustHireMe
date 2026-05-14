from __future__ import annotations

import os
import re

_assets = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
    "JustHireMe", "assets",
)
os.makedirs(_assets, exist_ok=True)


def _clean(text: str) -> str:
    """
    Replace every character that Helvetica (Latin-1) cannot encode,
    then NFKD-normalise and re-encode to latin-1 so nothing slips through.
    """
    import unicodedata
    _subs = {
        "\u2022": "-", "\u2023": "-", "\u25cf": "-", "\u25aa": "-",
        "\u25a0": "-", "\u25ab": "-", "\u25b6": ">",
        "\u2013": "-", "\u2014": "--", "\u2015": "--", "\u2010": "-",
        "\u2011": "-", "\u2012": "-",
        "\u2018": "'", "\u2019": "'", "\u201a": ",",
        "\u201c": '"', "\u201d": '"', "\u201e": '"',
        "\u2192": "->", "\u2190": "<-", "\u2194": "<->",
        "\u2026": "...",
        "\u2713": "(check)", "\u2714": "(check)", "\u2717": "(x)", "\u2718": "(x)",
        "\u2705": "(check)", "\u274c": "(x)",
        "\u00ae": "(R)", "\u00a9": "(C)", "\u2122": "(TM)",
        "\u200b": "", "\u200c": "", "\u200d": "",
        "\u00a0": " ", "\u202f": " ", "\u2009": " ", "\u2008": " ",
        "\u00b7": "-", "\u2605": "*", "\u2606": "*", "\u26a0": "Warning:",
        # Bullets & boxes
        "•": "-", "‣": "-", "●": "-", "▪": "-",
        "■": "-", "▫": "-", "▶": ">",
        # Dashes
        "–": "-", "—": "--", "―": "--", "‐": "-",
        "‑": "-", "‒": "-",
        # Quotes
        "‘": "'", "’": "'", "‚": ",",
        "“": '"', "”": '"', "„": '"',
        # Arrows & misc symbols
        "→": "->", "←": "<-", "↔": "<->",
        "…": "...",
        "✓": "(check)", "✔": "(check)", "✗": "(x)", "✘": "(x)",
        "®": "(R)", "©": "(C)", "™": "(TM)",
        # Zero-width / special spaces
        "​": "", "‌": "", "‍": "",
        " ": " ", " ": " ", " ": " ", " ": " ",
        # Middle dot
        "·": "-",
        # Checkmarks and crosses sometimes used in LLM output
        "✅": "(check)", "❌": "(x)",
    }
    for ch, rep in _subs.items():
        text = text.replace(ch, rep)
    text = re.sub(r"[\U0001F1E6-\U0001FAFF]", "", text)
    text = text.replace("\ufffd", "")
    text = unicodedata.normalize("NFKD", text)
    return text.encode("latin-1", errors="ignore").decode("latin-1")


def _strip_inline(text: str) -> str:
    """Remove **bold**, *italic*, `code`, and [link](url) inline markers."""
    import re
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*',     r'\1', text)
    text = re.sub(r'`(.+?)`',       r'\1', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    return text.strip()


def _shorten_text(text: str, limit: int) -> str:
    clean = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(clean) <= limit:
        return clean
    return clean[: max(0, limit - 1)].rstrip(" ,.;:-") + "."


def _render_resume_template(md_text: str, filename: str) -> str:
    """Render a one-page, recruiter-friendly resume template from constrained Markdown."""
    from fpdf import FPDF

    text = _clean(md_text)
    lines = [line.rstrip() for line in text.splitlines()]

    name = "Candidate"
    contact_lines: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    current_heading = ""
    current_lines: list[str] = []
    in_sections = False

    for raw in lines:
        line = raw.strip()
        if not line:
            if in_sections and current_heading:
                current_lines.append("")
            continue
        if line.startswith("# ") and name == "Candidate":
            name = _strip_inline(line[2:]) or name
            continue
        if line.startswith("## "):
            if current_heading:
                sections.append((current_heading, current_lines))
            current_heading = _strip_inline(line[3:]).upper()
            current_lines = []
            in_sections = True
            continue
        if in_sections:
            current_lines.append(line)
        else:
            contact_lines.append(_strip_inline(line))

    if current_heading:
        sections.append((current_heading, current_lines))

    def normalize_sections(source: list[tuple[str, list[str]]]) -> list[tuple[str, list[str]]]:
        normalized: list[tuple[str, list[str]]] = []
        budgets = {
            "SUMMARY": {"entries": 2, "bullets": 0, "chars": 430},
            "SKILLS": {"entries": 6, "bullets": 0, "chars": 128},
            "PROJECTS": {"entries": 3, "bullets": 3, "chars": 155},
            "EXPERIENCE": {"entries": 2, "bullets": 2, "chars": 155},
            "CERTIFICATES": {"entries": 3, "bullets": 0, "chars": 120},
            "CERTS": {"entries": 3, "bullets": 0, "chars": 120},
            "ACHIEVEMENTS": {"entries": 3, "bullets": 0, "chars": 130},
            "EDUCATION": {"entries": 3, "bullets": 0, "chars": 130},
        }
        for heading, body in source:
            budget = budgets.get(heading, {"entries": 4, "bullets": 2, "chars": 145})
            entry_count = 0
            bullet_count = 0
            out: list[str] = []
            for raw_item in body:
                stripped = raw_item.strip()
                if not stripped:
                    if out and out[-1] != "":
                        out.append("")
                    continue
                if stripped.startswith("### "):
                    if entry_count >= int(budget["entries"]):
                        continue
                    entry_count += 1
                    bullet_count = 0
                    out.append("### " + _shorten_text(stripped[4:], 95))
                    continue
                if re.match(r"^[-*+]\s+", stripped):
                    if int(budget["bullets"]) and bullet_count >= int(budget["bullets"]):
                        continue
                    bullet_count += 1
                    prefix = re.match(r"^[-*+]\s+", stripped).group(0)
                    out.append(prefix + _shorten_text(re.sub(r"^[-*+]\s+", "", stripped), int(budget["chars"])))
                    continue
                if heading in {"SUMMARY", "SKILLS", "CERTIFICATES", "CERTS", "ACHIEVEMENTS", "EDUCATION"}:
                    if entry_count >= int(budget["entries"]):
                        continue
                    entry_count += 1
                out.append(_shorten_text(stripped, int(budget["chars"])))
            normalized.append((heading, out))
        return normalized

    sections = normalize_sections(sections)

    def build_pdf(scale: float, spread: float = 1.0) -> tuple[FPDF, bool, float]:
        pdf = FPDF(format="Letter", unit="mm")
        margin_x = 11 * scale
        margin_y = 10 * scale
        pdf.set_margins(margin_x, margin_y, margin_x)
        pdf.set_auto_page_break(auto=False)
        pdf.add_page()

        page_w = pdf.w
        page_h = pdf.h
        eff_w = page_w - (2 * margin_x)
        bottom = page_h - margin_y
        accent = (31, 78, 121)
        ink = (28, 31, 35)
        muted = (92, 98, 108)
        rule = (183, 194, 207)
        overflow = False

        def fs(value: float) -> float:
            return max(6.2, value * scale)

        def lh(value: float) -> float:
            return max(3.35, value * 0.48 * min(spread, 1.45))

        def ensure(height: float) -> bool:
            nonlocal overflow
            if pdf.get_y() + height > bottom:
                overflow = True
                return False
            return True

        def set_font(size: float, style: str = "", color=ink):
            pdf.set_text_color(*color)
            pdf.set_font("Helvetica", style=style, size=fs(size))

        def write_block(text_value: str, size: float = 8.0, style: str = "", indent: float = 0, after: float = 0.2):
            clean = _strip_inline(text_value)
            if not clean:
                return
            set_font(size, style)
            line_h = lh(fs(size))
            width = eff_w - indent
            estimated = max(1, int((pdf.get_string_width(clean) / max(width, 1)) + 1.25)) * line_h + (after * spread)
            if not ensure(estimated):
                return
            pdf.set_x(margin_x + indent)
            pdf.multi_cell(width, line_h, clean, align="L")
            if after:
                pdf.ln(after * spread)

        def write_bullet(text_value: str):
            clean = _strip_inline(text_value)
            if not clean:
                return
            set_font(7.8)
            line_h = lh(fs(7.8))
            bullet_indent = 4.0 * scale
            text_indent = 7.0 * scale
            width = eff_w - text_indent
            estimated = max(1, int((pdf.get_string_width(clean) / max(width, 1)) + 1.25)) * line_h + (0.25 * spread)
            if not ensure(estimated):
                return
            y = pdf.get_y()
            pdf.set_text_color(*accent)
            pdf.set_font("Helvetica", "B", fs(8.0))
            pdf.set_xy(margin_x + bullet_indent, y)
            pdf.cell(2.5 * scale, line_h, "-")
            set_font(7.8)
            pdf.set_xy(margin_x + text_indent, y)
            pdf.multi_cell(width, line_h, clean, align="L")
            pdf.ln(0.25 * spread)

        def split_title_meta(title: str) -> tuple[str, str]:
            clean = _strip_inline(title)
            patterns = (
                r"\s((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[A-Za-z]*'?\s*\d{2,4}(?:\s*[-]\s*(?:Present|Current|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[A-Za-z]*'?\s*\d{2,4}))?)$",
                r"\s(\d{4}\s*[-]\s*(?:Present|Current|\d{4}))$",
                r"\s(\d{4})$",
            )
            for pattern in patterns:
                match = re.search(pattern, clean, flags=re.I)
                if match:
                    return clean[:match.start()].strip(" -:"), match.group(1).strip()
            return clean, ""

        def write_entry_title(title: str):
            left, right = split_title_meta(_shorten_text(title, 105))
            if not ensure(5.2 * scale):
                return
            set_font(8.6, "B")
            y = pdf.get_y()
            pdf.set_xy(margin_x, y)
            if right:
                right_w = min(42 * scale, pdf.get_string_width(right) + 2)
                line_h = lh(fs(8.6))
                pdf.multi_cell(eff_w - right_w - 3, line_h, left, align="L")
                left_bottom = pdf.get_y()
                set_font(7.8, "", muted)
                pdf.set_xy(page_w - margin_x - right_w, y)
                pdf.cell(right_w, line_h, right, align="R")
                pdf.set_y(max(left_bottom, y + line_h) + (0.6 * spread))
            else:
                pdf.multi_cell(eff_w, lh(fs(8.6)), left, align="L")
                pdf.ln(0.3 * spread)

        def write_section(heading: str, body: list[str]):
            if not ensure(7.0 * scale):
                return
            pdf.ln(1.0 * scale * spread)
            set_font(8.4, "B", accent)
            pdf.set_x(margin_x)
            pdf.cell(eff_w, lh(fs(8.4)), heading)
            pdf.ln(lh(fs(8.4)) + (0.35 * spread))
            pdf.set_draw_color(*rule)
            pdf.set_line_width(0.25)
            pdf.line(margin_x, pdf.get_y(), page_w - margin_x, pdf.get_y())
            pdf.ln(1.1 * scale * spread)

            previous_blank = False
            for item in body:
                stripped = item.strip()
                if not stripped:
                    if not previous_blank and ensure(1.0 * scale * spread):
                        pdf.ln(0.6 * scale * spread)
                    previous_blank = True
                    continue
                previous_blank = False
                if stripped.startswith("### "):
                    write_entry_title(stripped[4:])
                elif re.match(r"^[-*+]\s+", stripped):
                    write_bullet(re.sub(r"^[-*+]\s+", "", stripped))
                else:
                    write_block(stripped, size=7.8, after=0.35)

        set_font(19.0, "B", accent)
        pdf.set_xy(margin_x, margin_y)
        pdf.cell(eff_w, lh(fs(19.0)), name, align="C")
        pdf.ln(lh(fs(19.0)) + (0.6 * spread))

        if contact_lines:
            contact = "  |  ".join(part for part in contact_lines if part)
            set_font(7.8, "", muted)
            pdf.set_x(margin_x)
            pdf.multi_cell(eff_w, lh(fs(7.8)), contact, align="C")
            pdf.ln(1.2 * scale * spread)

        pdf.set_draw_color(*accent)
        pdf.set_line_width(0.55)
        pdf.line(margin_x + 10 * scale, pdf.get_y(), page_w - margin_x - 10 * scale, pdf.get_y())
        pdf.ln(2.3 * scale * spread)

        for heading, body in sections:
            write_section(heading, body)
            if overflow:
                break

        used_ratio = (pdf.get_y() - margin_y) / max(1.0, bottom - margin_y)
        return pdf, overflow, used_ratio

    out = os.path.join(_assets, filename)
    chosen_pdf = None
    chosen_ratio = 0.0
    for scale in (1.28, 1.22, 1.16, 1.10, 1.04, 0.98, 0.92, 0.86, 0.80, 0.76):
        pdf, overflow, used_ratio = build_pdf(scale)
        chosen_pdf = pdf
        chosen_ratio = used_ratio
        if not overflow:
            break
    if chosen_ratio < 0.90:
        spread = min(2.20, 1.0 + (0.90 - chosen_ratio) * 2.2)
        filled_pdf, overflow, used_ratio = build_pdf(scale, spread=spread)
        if not overflow:
            chosen_pdf = filled_pdf
            chosen_ratio = used_ratio
    chosen_pdf.output(out)
    return out


def _render(md_text: str, filename: str, kind: str = "resume") -> str:
    """
    Convert Markdown to PDF using direct multi_cell() calls with inline
    bold/italic support via write() for mixed-style lines.

    Matches a professional resume layout: large bold name, section headings
    with horizontal rules, categorised skill rows with bold labels,
    compact project/experience blocks with bullet indentation.
    """
    import re
    from fpdf import FPDF

    if kind == "resume":
        return _render_resume_template(md_text, filename)

    text = _clean(md_text)
    lines = text.splitlines()

    base_margin = 11 if kind == "resume" else 15
    base_sizes = {
        "h1": 16.0 if kind == "resume" else 15.0,
        "h2": 10.8 if kind == "resume" else 12.0,
        "h3": 9.4 if kind == "resume" else 10.5,
        "h4": 8.8 if kind == "resume" else 10.0,
        "body": 8.4 if kind == "resume" else 10.0,
        "quote": 8.0 if kind == "resume" else 9.4,
    }

    def build_pdf(scale: float) -> tuple[FPDF, bool]:
        pdf = FPDF()
        margin = max(8.0, base_margin * scale)
        pdf.set_margins(margin, margin, margin)
        pdf.set_auto_page_break(auto=False)
        pdf.add_page()
        eff_w = pdf.w - pdf.l_margin - pdf.r_margin
        bottom = pdf.h - margin
        truncated = False

        def size(name: str) -> float:
            return max(6.0, base_sizes[name] * scale)

        def line_height(font_size: float) -> float:
            return max(2.8, font_size * 0.42)

        def wrapped_lines_plain(txt: str, width: float, font_size: float, bold: bool = False) -> int:
            pdf.set_font("Helvetica", style="B" if bold else "", size=font_size)
            words = str(txt or "").split()
            if not words:
                return 1
            count = 1
            current = ""
            for word in words:
                candidate = word if not current else f"{current} {word}"
                if pdf.get_string_width(candidate) <= width:
                    current = candidate
                    continue
                if current:
                    count += 1
                current = word
                if pdf.get_string_width(word) > width:
                    count += max(0, int(pdf.get_string_width(word) // max(width, 1)))
            return count

        def _has_inline_bold(txt: str) -> bool:
            return "**" in txt

        def _emit_rich_line(txt: str, font_size: float, indent: float = 0):
            """Render a line with inline **bold** segments using write()."""
            nonlocal truncated
            if truncated:
                return
            lh = line_height(font_size)
            # Strip link markdown but keep text
            txt = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', txt)
            txt = re.sub(r'`(.+?)`', r'\1', txt)
            pdf.set_x(pdf.l_margin + indent)
            # Split on **bold** markers
            parts = re.split(r'(\*\*.*?\*\*)', txt)
            for part in parts:
                if part.startswith("**") and part.endswith("**"):
                    pdf.set_font("Helvetica", style="B", size=font_size)
                    pdf.write(lh, part[2:-2])
                else:
                    # Handle *italic* inside non-bold parts
                    italic_parts = re.split(r'(\*[^*]+?\*)', part)
                    for ip in italic_parts:
                        if ip.startswith("*") and ip.endswith("*") and len(ip) > 2:
                            pdf.set_font("Helvetica", style="I", size=font_size)
                            pdf.write(lh, ip[1:-1])
                        else:
                            pdf.set_font("Helvetica", style="", size=font_size)
                            pdf.write(lh, ip)
            pdf.ln(lh)

        def emit(txt: str, font_size: float, bold: bool = False, indent: float = 0, before: float = 0, after: float = 0):
            nonlocal truncated
            if truncated:
                return
            clean_for_height = _strip_inline(txt)
            width = max(24.0, eff_w - indent)
            lh = line_height(font_size)
            height = before + wrapped_lines_plain(clean_for_height, width, font_size, bold) * lh + after
            if pdf.get_y() + height > bottom:
                truncated = True
                return
            if before:
                pdf.ln(before)
            # If the line has inline **bold** markers, render with mixed styles
            if not bold and _has_inline_bold(txt):
                _emit_rich_line(txt, font_size, indent)
            else:
                clean = _strip_inline(txt)
                pdf.set_font("Helvetica", style="B" if bold else "", size=font_size)
                pdf.set_x(pdf.l_margin + indent)
                pdf.multi_cell(width, lh, clean)
            if after:
                pdf.ln(after)

        def emit_blank(amount: float):
            if not truncated and pdf.get_y() + amount <= bottom:
                pdf.ln(amount)

        def emit_rule(before: float = 1.0, after: float = 1.0):
            nonlocal truncated
            if truncated:
                return
            if pdf.get_y() + before + after + 0.3 > bottom:
                truncated = True
                return
            if before:
                pdf.ln(before)
            pdf.set_draw_color(135, 135, 135)
            pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
            if after:
                pdf.ln(after)

        i = 0
        while i < len(lines):
            raw = lines[i]
            stripped = raw.strip()
            i += 1

            if not stripped:
                emit_blank(0.9 if kind == "resume" else 1.4)
                continue

            if re.match(r'^[-*]{3,}$', stripped):
                emit_rule()
                continue

            if stripped.startswith("#### "):
                emit(stripped[5:], size("h4"), bold=True, after=0.4)
                continue
            if stripped.startswith("### "):
                emit(stripped[4:], size("h3"), bold=True, before=0.8, after=0.4)
                continue
            if stripped.startswith("## "):
                emit(stripped[3:], size("h2"), bold=True, before=1.2, after=0.6)
                emit_rule(before=0, after=0.8)
                continue
            if stripped.startswith("# "):
                emit(stripped[2:], size("h1"), bold=True, before=0.4, after=1.0)
                continue

            if stripped.startswith("> "):
                emit(stripped[2:], size("quote"), indent=7)
                continue

            m = re.match(r'^[-*+]\s+(.*)', stripped)
            if m:
                bullet_content = m.group(1)
                # Check for Tech: prefix — render with bold label
                tech_m = re.match(r'^(Tech:\s*)(.*)', bullet_content)
                if tech_m:
                    emit("- **Tech:** " + tech_m.group(2), size("body"), indent=5)
                else:
                    emit("- " + bullet_content, size("body"), indent=5)
                continue

            m = re.match(r'^\d+\.\s+(.*)', stripped)
            if m:
                emit(stripped, size("body"), indent=5)
                continue

            emit(stripped, size("body"))
        return pdf, truncated

    out = os.path.join(_assets, filename)
    chosen_pdf = None
    for scale in (1.0, 0.94, 0.88, 0.82, 0.76, 0.70):
        pdf, truncated = build_pdf(scale)
        chosen_pdf = pdf
        if not truncated:
            break
    pdf = chosen_pdf
    pdf.output(out)
    return out


def render_resume_template(md_text: str, filename: str) -> str:
    return _render_resume_template(md_text, filename)


def render(md_text: str, filename: str, kind: str = "resume") -> str:
    return _render(md_text, filename, kind=kind)
