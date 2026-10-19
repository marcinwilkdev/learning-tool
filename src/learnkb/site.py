"""Render the wiki under kb/ into a static learning website under site/.

The site works offline straight from disk (file://): no CDN, no fetch(). Shared
data (concept definitions, topic list) is emitted as assets/data.js and loaded
with a plain <script> tag.

Optional lesson files (kb/lessons/<topic>.yaml, written by the learning-page skill)
add a hook, a flow diagram, a step-through walkthrough and self-check questions to
the matching topic page.

Optional quiz files (kb/quizzes/<topic>.yaml, written by the assess skill) become a
graded assessment page under site/quizzes/, linked from the topic page.
"""

import argparse
import html
import json
import re
import shutil
import sys
import webbrowser
from pathlib import Path

import markdown
import yaml
from pygments.formatters import HtmlFormatter

from learnkb.check import (CODE, CURRICULUM, LINK, NO_KB, Page, Report, check, check_links, load_pages,
                           read_json, yaml_error)
from learnkb import i18n
from learnkb.i18n import t
from learnkb.ingest import KB, MANIFEST, ROOT

SITE = ROOT / "site"
ASSETS = Path(__file__).parent / "site_assets"
FOLDER = {"topic": "topics", "concept": "concepts", "source": "sources"}
SECTION_ICONS = {"overview": "◎", "walkthrough": "➜", "common pitfalls": "⚠", "summary": "✓"}


# ---------------------------------------------------------------- markdown


def esc(text) -> str:
    return html.escape(str(text), quote=True)


def resolve_links(md: str, pages: dict[str, Page], prefix: str) -> str:
    """Turn [[slug]] / [[slug|text]] into HTML links before markdown runs."""

    def repl(match: re.Match) -> str:
        inner = match.group(0)[2:-2]
        target, _, label = inner.partition("|")
        target = target.split("#")[0].strip()
        page = pages.get(target)
        if not page:
            return esc(label or target)
        text = label or page.meta.get("title", target)
        cls = f"wl wl-{page.kind}"
        return (f'<a class="{cls}" data-slug="{esc(target)}" '
                f'href="{prefix}{FOLDER[page.kind]}/{target}.html">{esc(text)}</a>')

    return LINK.sub(repl, md)


LIST_ITEM = re.compile(r"^(?:[-*+]|\d+\.)\s")
PLACEHOLDER = re.compile(r"<(/?)([A-Za-z][\w.-]*)((?: [^<>\n]*)?)>")
HTML_TAGS = {"a", "abbr", "b", "br", "code", "div", "em", "i", "img", "kbd", "li", "mark", "ol", "p",
             "pre", "small", "span", "strong", "sub", "sup", "table", "td", "th", "tr", "u", "ul"}


def escape_placeholders(md: str) -> str:
    """Show <commit>, <paths> and the like as text; Markdown would pass them through as HTML tags."""
    def repl(m: re.Match) -> str:
        return m.group(0) if m.group(2).lower() in HTML_TAGS else "&lt;" + m.group(0)[1:-1] + "&gt;"

    out, last = [], 0
    for code in CODE.finditer(md):
        out += [PLACEHOLDER.sub(repl, md[last:code.start()]), code.group(0)]
        last = code.end()
    return "".join(out) + PLACEHOLDER.sub(repl, md[last:])


def separate_lists(md: str) -> str:
    """Python-Markdown needs a blank line before a list that follows a paragraph line."""
    lines, fenced = [], False
    for line in md.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
        prev = lines[-1] if lines else ""
        if (not fenced and LIST_ITEM.match(line) and prev.strip()
                and not LIST_ITEM.match(prev) and not prev[0].isspace()):
            lines.append("")
        lines.append(line)
    return "\n".join(lines)


def render_md(md: str, pages: dict[str, Page], prefix: str) -> str:
    out = markdown.markdown(
        escape_placeholders(resolve_links(separate_lists(md), pages, prefix)),
        extensions=["fenced_code", "tables", "codehilite", "sane_lists"],
        extension_configs={"codehilite": {"guess_lang": False, "css_class": "hl"}},
    )
    # "> Note: ..." callouts and "> Parsing note" get their own styling.
    out = re.sub(r"<blockquote>\s*<p>(Note|Parsing note|Source disagreement[^:]*):",
                 lambda m: f'<blockquote class="callout callout-note"><p><strong>{callout_label(m.group(1))}:</strong>',
                 out)
    return out


def callout_label(label: str) -> str:
    return t(f"callout:{label.lower()}") if f"callout:{label.lower()}" in i18n.strings else label


def heading_label(heading: str) -> str:
    """The display name of a section heading; kb/ pages keep the English one."""
    key = f"heading:{heading.lower()}"
    return t(key) if key in i18n.strings else heading


def localize_headings(md: str) -> str:
    return re.sub(r"^(#{2,3} +)(.+)$", lambda m: m.group(1) + heading_label(m.group(2).strip()), md, flags=re.M)


def split_sections(body: str) -> list[tuple[str, str]]:
    """Split a page body on '## ' headings into (heading, markdown) pairs."""
    parts = re.split(r"^## +(.+)$", body, flags=re.M)
    sections = [("", parts[0])] if parts[0].strip() else []
    sections += [(parts[i].strip(), parts[i + 1]) for i in range(1, len(parts), 2)]
    return sections


def list_items(md: str) -> list[str]:
    return [re.sub(r"^\s*[-*]\s+", "", line).strip()
            for line in md.splitlines() if re.match(r"^\s*[-*]\s+", line)]


def inline_md(text: str, pages: dict[str, Page], prefix: str) -> str:
    rendered = render_md(text, pages, prefix).strip()
    return re.sub(r"^<p>(.*)</p>$", r"\1", rendered, flags=re.S)


def objectives(page: Page) -> list[str]:
    return list_items(dict(split_sections(page.body)).get("Learning objectives", ""))


def minutes(page: Page, lesson: dict | None) -> int:
    # Reading time plus time to absorb each concept and work through the lesson.
    words = len(re.findall(r"\w+", page.body))
    lesson = lesson or {}
    steps = len(lesson.get("walkthrough", {}).get("steps", []))
    checks = len(lesson.get("checks", []))
    concepts = len(page.meta.get("concepts") or [])
    return max(5, round(words / 180 + concepts * 1.5 + steps * 1.5 + checks))


# ---------------------------------------------------------------- lessons


def strings(data) -> list[str]:
    """Every string in a parsed YAML document, for link checks."""
    if isinstance(data, dict):
        return [s for v in data.values() for s in strings(v)]
    if isinstance(data, list):
        return [s for v in data for s in strings(v)]
    return [data] if isinstance(data, str) else []


def load_yaml(rel: str, pages: dict[str, Page], report: Report) -> dict | None:
    path = KB / rel
    if not path.exists():
        return None
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        report.error(f"{rel}: {yaml_error(exc)}")
        return None
    check_links(rel, "\n".join(strings(data)), pages, report)
    return data


def load_lesson(slug: str, pages: dict[str, Page], report: Report) -> dict | None:
    rel = f"lessons/{slug}.yaml"
    lesson = load_yaml(rel, pages, report)
    if lesson is None:
        return None
    if lesson.get("topic") != slug:
        report.error(f"{rel}: 'topic' should be '{slug}'")
    flow = lesson.get("flow", {})
    for i, node in enumerate(flow.get("nodes", [])):
        if "label" not in node:
            report.error(f"{rel}: flow node {i} needs a label")
    layout = flow.get("layout", "steps")
    if layout not in ("steps", "choices"):
        report.error(f"{rel}: flow layout must be 'steps' or 'choices', got {layout!r}")
    elif layout == "choices" and (flow.get("arrows") or flow.get("loop")):
        report.warn(f"{rel}: a 'choices' flow has no order, so its arrows and loop aren't shown")
    elif layout == "steps" and any(not str(a).strip() for a in flow.get("arrows", [])):
        report.warn(f"{rel}: flow has empty arrow labels; name each transition, or use "
                    "layout: choices if the nodes are alternatives rather than steps")
    for i, step in enumerate(lesson.get("walkthrough", {}).get("steps", [])):
        if not step.get("explain"):
            report.error(f"{rel}: walkthrough step {i + 1} needs 'explain'")
    for i, chk in enumerate(lesson.get("checks", [])):
        if not chk.get("q") or not chk.get("a"):
            report.error(f"{rel}: check {i + 1} needs 'q' and 'a'")
    return lesson


def render_flow(flow: dict, pages, prefix) -> str:
    if flow.get("layout") == "choices":
        return render_choices(flow, pages, prefix)
    nodes = flow.get("nodes", [])
    arrows = flow.get("arrows", [])
    parts = []
    for i, node in enumerate(nodes):
        note = f'<span class="flow-note">{inline_md(node["note"], pages, prefix)}</span>' if node.get("note") else ""
        parts.append(f'<div class="flow-node"><span class="flow-label">{esc(node["label"])}</span>{note}</div>')
        if i < len(nodes) - 1:
            label = arrows[i] if i < len(arrows) else ""
            parts.append(f'<div class="flow-arrow"><code>{esc(label)}</code><span aria-hidden="true">→</span></div>')
    back = ""
    if flow.get("loop"):
        back = f'<p class="flow-loop">↺ {inline_md(flow["loop"], pages, prefix)}</p>'
    caption = f'<figcaption>{inline_md(flow["caption"], pages, prefix)}</figcaption>' if flow.get("caption") else ""
    return f'<figure class="flow"><div class="flow-row">{"".join(parts)}</div>{back}{caption}</figure>'


def render_choices(flow: dict, pages, prefix) -> str:
    """Alternatives that branch from one starting point, with no order between them."""
    cards = "".join(
        f'<div class="flow-node"><span class="flow-label">{esc(node["label"])}</span>'
        + (f'<span class="flow-note">{inline_md(node["note"], pages, prefix)}</span>' if node.get("note") else "")
        + "</div>" for node in flow.get("nodes", []))
    prompt = f'<div class="flow-prompt">{inline_md(flow["prompt"], pages, prefix)}</div>' if flow.get("prompt") else ""
    caption = f'<figcaption>{inline_md(flow["caption"], pages, prefix)}</figcaption>' if flow.get("caption") else ""
    return f'<figure class="flow flow-choices">{prompt}<div class="flow-options">{cards}</div>{caption}</figure>'


def render_steps(walk: dict, pages, prefix) -> str:
    steps = walk.get("steps", [])
    items = []
    for i, step in enumerate(steps, 1):
        term = ""
        if step.get("command") or step.get("output"):
            cmd = "".join(f'<div class="t-cmd"><span class="t-prompt">$</span> {esc(c)}</div>'
                          for c in str(step.get("command", "")).strip().splitlines() if c.strip())
            out = f'<pre class="t-out">{esc(str(step["output"]).rstrip())}</pre>' if step.get("output") else ""
            term = f'<div class="terminal" aria-label="Terminal">{cmd}{out}</div>'
        items.append(
            f'<li class="step" data-step="{i}"><div class="step-head"><span class="step-num">{t("step_of", i=i, n=len(steps))}</span>'
            f'<span class="step-title">{esc(step.get("title", ""))}</span></div>{term}'
            f'<div class="step-explain">{render_md(step["explain"], pages, prefix)}</div></li>')
    intro = f'<p class="steps-intro">{inline_md(walk["intro"], pages, prefix)}</p>' if walk.get("intro") else ""
    return (f'<section class="steps" data-steps><div class="steps-top"><h2 id="try-it">'
            f'<span class="sec-icon">▶</span>{esc(walk.get("title", t("try_it")))}</h2>'
            f'<button class="btn-ghost" data-show-all>{t("show_all")}</button></div>{intro}'
            f'<ol class="step-list">{"".join(items)}</ol>'
            f'<div class="step-nav"><button class="btn" data-prev>{t("back")}</button>'
            f'<div class="step-dots" aria-hidden="true"></div>'
            f'<button class="btn btn-primary" data-next>{t("next")}</button></div></section>')


def render_checks(checks: list, pages, prefix) -> str:
    items = "".join(
        f'<details class="check"><summary><span class="check-q">{inline_md(c["q"], pages, prefix)}</span>'
        f'<span class="check-reveal">{t("reveal")}</span></summary>'
        f'<div class="check-a">{render_md(c["a"], pages, prefix)}</div></details>'
        for c in checks)
    return (f'<section class="checks"><h2 id="check-yourself"><span class="sec-icon">?</span>{t("check_yourself")}</h2>'
            f'<p class="muted">{t("check_hint")}</p>{items}</section>')


# ---------------------------------------------------------------- quizzes


def load_quiz(slug: str, n_objectives: int, pages: dict[str, Page], report: Report) -> dict | None:
    rel = f"quizzes/{slug}.yaml"
    quiz = load_yaml(rel, pages, report)
    if quiz is None:
        return None
    if quiz.get("topic") != slug:
        report.error(f"{rel}: 'topic' should be '{slug}'")
    questions = quiz.get("questions") or []
    if not questions:
        report.error(f"{rel}: no questions")
    covered = set()
    for i, q in enumerate(questions, 1):
        where = f"{rel}: question {i}"
        obj = q.get("objective")
        if not isinstance(obj, int) or not 1 <= obj <= n_objectives:
            report.error(f"{where}: 'objective' must be a number from 1 to {n_objectives}")
        else:
            covered.add(obj)
        if not q.get("q"):
            report.error(f"{where} needs 'q'")
        kind = q.get("type", "choice")
        if kind == "choice":
            opts = q.get("options") or []
            if len(opts) < 2 or any(not isinstance(o, dict) or o.get("text") in (None, "") for o in opts):
                report.error(f"{where}: needs at least two options, each with 'text'")
            elif not any(o.get("correct") for o in opts):
                report.error(f"{where}: no option is marked 'correct: true'")
        elif kind == "open":
            if not q.get("answer") or not q.get("points"):
                report.error(f"{where}: open questions need 'answer' and 'points'")
        else:
            report.error(f"{where}: unknown type '{kind}' (use choice or open)")
    missing = [str(n) for n in range(1, n_objectives + 1) if n not in covered]
    if missing:
        report.warn(f"{rel}: no question tests objective(s) {', '.join(missing)}")
    return quiz


def quiz_minutes(quiz: dict) -> int:
    return max(3, round(sum(2.5 if q.get("type") == "open" else 1 for q in quiz["questions"])))


def render_question(n: int, q: dict, pages, prefix) -> str:
    kind = q.get("type", "choice")
    head = (f'<div class="q-head"><span class="q-num">{t("question_n", n=n)}</span>'
            f'<span class="q-verdict" aria-live="polite"></span></div>'
            f'<div class="q-text">{render_md(str(q["q"]), pages, prefix)}</div>')
    if kind == "open":
        points = "".join(f'<li><label><input type="checkbox" data-point>'
                         f'<span>{inline_md(str(p), pages, prefix)}</span></label></li>' for p in q["points"])
        body = (f'<textarea class="q-answer" rows="4" aria-label="{t("your_answer", n=n)}" '
                f'placeholder="{t("answer_placeholder")}"></textarea>'
                f'<div class="q-model"><h3>{t("model_answer")}</h3>{render_md(str(q["answer"]), pages, prefix)}'
                f'<p class="q-hint">{t("tick_points")}</p><ul class="points">{points}'
                f'<li class="point-none"><label><input type="checkbox" data-none>'
                f'<span data-en="{i18n.EN["none_of_these"]}">{t("none_of_these")}</span></label></li></ul></div>')
    else:
        multi = sum(bool(o.get("correct")) for o in q["options"]) > 1
        itype = "checkbox" if multi else "radio"
        opts = []
        for o in q["options"]:
            why = f'<div class="opt-why">{inline_md(str(o["why"]), pages, prefix)}</div>' if o.get("why") else ""
            opts.append(f'<li class="opt" data-correct="{int(bool(o.get("correct")))}"><label>'
                        f'<input type="{itype}" name="q{n}"><span class="opt-text">'
                        f'{inline_md(str(o["text"]), pages, prefix)}</span></label>{why}</li>')
        hint = f'<p class="q-hint">{t("select_all")}</p>' if multi else ""
        body = f'{hint}<ul class="opts">{"".join(opts)}</ul>'
    explain = f'<div class="q-explain">{render_md(str(q["explain"]), pages, prefix)}</div>' if q.get("explain") else ""
    return (f'<li class="question" data-type="{esc(kind)}" data-objective="{q["objective"]}">'
            f'{head}{body}{explain}</li>')


def quiz_page(page: Page, quiz: dict, pages, curriculum) -> str:
    prefix = "../"
    slug = page.slug
    title = page.meta["title"]
    questions = quiz["questions"]
    n_open = sum(q.get("type") == "open" for q in questions)
    intro = quiz.get("intro") or t("quiz_intro", n=len(questions))
    topic_href = f"{prefix}topics/{slug}.html"
    head = (f'<header class="page-head"><p class="eyebrow">{t("assessment")}</p><h1>{esc(title)}</h1>'
            f'<p class="lead">{inline_md(intro, pages, prefix)}</p>'
            f'<div class="chips"><span class="chip">{t("n_questions", n=len(questions))}</span>'
            f'<span class="chip">{t("min", n=quiz_minutes(quiz))}</span>'
            f'<span class="chip chip-plain"><a href="{topic_href}">← {t("back_to_lesson")}</a></span>'
            f'<span class="chip chip-score" data-quiz-score="{slug}" hidden></span></div></header>')
    rows = "".join(
        f'<li data-obj="{i}"><div class="or-top"><span class="or-text">{inline_md(text, pages, prefix)}</span>'
        f'<span class="or-status"></span></div><div class="bar"><span></span></div></li>'
        for i, text in enumerate(objectives(page), 1))
    self_note = f'<p class="muted" data-self-note>{t("self_note", n=n_open)}</p>' if n_open else ""
    results = (f'<section class="results" data-results hidden><h2 id="results">{t("your_results")}</h2>'
               f'<div class="score"><span class="score-num" data-score></span><span class="score-label" data-score-label></span></div>'
               f'{self_note}<h3>{t("by_objective")}</h3><ol class="obj-results">{rows}</ol>'
               f'<div class="results-actions"><button type="button" class="btn btn-primary" data-copy>{t("copy_results")}</button>'
               f'<button type="button" class="btn" data-retake>{t("retake")}</button>'
               f'<a class="btn" href="{topic_href}">{t("back_to_lesson")}</a></div>'
               f'<p class="muted copy-help" data-copy-help>{t("copy_help")}</p>'
               f'<p class="saved-note" data-saved hidden>✓ {t("saved")}</p>'
               f'<textarea class="copy-fallback" readonly hidden aria-label="{t("results_text")}"></textarea></section>')
    form = (f'<form class="quiz" data-quiz="{slug}" data-title="{esc(title)}" novalidate>'
            f'<ol class="questions">{"".join(render_question(i, q, pages, prefix) for i, q in enumerate(questions, 1))}</ol>'
            f'<div class="quiz-submit"><button class="btn btn-primary btn-lg" type="submit">{t("check_answers")}</button>'
            f'<p class="muted" data-unanswered></p></div></form>'
            f'<noscript><p class="callout-note">{t("noscript_quiz")}</p></noscript>')
    body = f'<article class="quiz-page">{head}{results}{form}{sources_footer(page, pages, prefix)}</article>'
    return layout(t("quiz_title", title=title), body, curriculum, pages, prefix, current=slug)


# ---------------------------------------------------------------- layout


def sidebar(curriculum: dict, pages, prefix: str, current: str | None) -> str:
    mods = []
    for n, module in enumerate(curriculum.get("modules", []), 1):
        links = "".join(
            f'<li><a href="{prefix}topics/{t}.html" data-topic="{t}"'
            f'{" aria-current=page" if t == current else ""}>'
            f'<span class="done-dot" aria-hidden="true"></span>{esc(pages[t].meta["title"])}</a></li>'
            for t in module["topics"] if t in pages)
        open_ = " open" if current in module["topics"] or current is None else ""
        mods.append(f'<details class="nav-module"{open_}><summary><span class="mod-num">{n}</span>'
                    f'{esc(module["title"])}</summary><ul>{links}</ul></details>')
    return (f'<nav class="sidebar" aria-label="{t("course")}"><a class="brand" href="{prefix}index.html">'
            f'{esc(curriculum.get("title", t("kb_title")))}</a>'
            f'<div class="progress-mini"><div class="bar"><span data-progress-bar></span></div>'
            f'<span data-progress-text></span></div>{"".join(mods)}'
            f'<a class="nav-extra" href="{prefix}glossary.html">{t("glossary")}</a>'
            f'<a class="nav-extra" href="{prefix}admin/" target="learnkb-admin" data-admin-link hidden>'
            f'{t("admin_panel")}</a></nav>')


def layout(title: str, body: str, curriculum: dict, pages, prefix: str,
           current: str | None = None, body_class: str = "") -> str:
    site_title = curriculum.get("title", t("kb_title"))
    return f"""<!doctype html>
<html lang="{i18n.lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} · {esc(site_title)}</title>
<link rel="stylesheet" href="{prefix}assets/style.css">
<link rel="stylesheet" href="{prefix}assets/code.css">
</head>
<body class="{body_class}">
<a class="skip" href="#main">{t("skip")}</a>
<button class="menu-btn" aria-label="{t("open_menu")}" data-menu>☰</button>
<div class="shell">
{sidebar(curriculum, pages, prefix, current)}
<main id="main">{body}</main>
</div>
<div class="tooltip" role="tooltip" hidden></div>
<script>window.KB_PREFIX = {json.dumps(prefix)};</script>
<script src="{prefix}assets/data.js"></script>
<script src="{prefix}assets/app.js"></script>
</body>
</html>
"""


def chips(page: Page, lesson, pages, prefix) -> str:
    diff = page.meta.get("difficulty", "")
    prereqs = [p for p in page.meta.get("prerequisites") or [] if p in pages]
    pre = ""
    if prereqs:
        links = ", ".join(f'<a href="{prefix}topics/{p}.html">{esc(pages[p].meta["title"])}</a>' for p in prereqs)
        pre = f'<span class="chip chip-plain">{t("before_this")} {links}</span>'
    return (f'<div class="chips">{difficulty_chip(diff)}'
            f'<span class="chip">{t("min", n=minutes(page, lesson))}</span>{pre}</div>')


def difficulty_chip(diff: str) -> str:
    # The class keeps the English level, which the stylesheet colours by.
    return f'<span class="chip chip-{esc(diff)}">{esc(t(diff) if diff else "")}</span>'


# ---------------------------------------------------------------- pages


def topic_page(page: Page, pages, curriculum, lessons, quizzes, order: list[str]) -> str:
    prefix = "../"
    slug = page.slug
    lesson = lessons.get(slug)
    module = next((m for m in curriculum["modules"] if slug in m["topics"]), {})
    out = [f'<header class="page-head"><p class="eyebrow">{esc(module.get("title", ""))}</p>'
           f'<h1>{esc(page.meta["title"])}</h1>'
           f'<p class="lead">{inline_md(page.meta.get("summary", ""), pages, prefix)}</p>'
           f'{chips(page, lesson, pages, prefix)}</header>']
    if lesson and lesson.get("hook"):
        out.append(f'<aside class="hook"><span class="hook-label">{t("imagine")}</span>'
                   f'{render_md(lesson["hook"], pages, prefix)}</aside>')

    for heading, md in split_sections(page.body):
        key = heading.lower()
        anchor = re.sub(r"[^a-z0-9]+", "-", key).strip("-")
        if key == "learning objectives":
            items = "".join(
                f'<li><label><input type="checkbox" data-objective="{slug}:{i}">'
                f'<span>{inline_md(item, pages, prefix)}</span></label></li>'
                for i, item in enumerate(list_items(md)))
            out.append(f'<section class="objectives" id="{anchor}"><h2>{t("objectives")}</h2>'
                       f'<p class="muted">{t("objectives_hint")}</p>'
                       f'<ul class="checklist">{items}</ul></section>')
            continue
        icon = SECTION_ICONS.get(key, "")
        icon_html = f'<span class="sec-icon">{icon}</span>' if icon else ""
        cls = "pitfalls" if key == "common pitfalls" else "summary" if key == "summary" else ""
        out.append(f'<section class="prose {cls}" id="{anchor}"><h2>{icon_html}{esc(heading_label(heading))}</h2>'
                   f'{render_md(localize_headings(md), pages, prefix)}</section>')
        if key == "overview" and lesson and lesson.get("flow"):
            out.append(render_flow(lesson["flow"], pages, prefix))
        if key == "walkthrough" and lesson and lesson.get("walkthrough"):
            out.append(render_steps(lesson["walkthrough"], pages, prefix))

    if lesson and lesson.get("checks"):
        out.append(render_checks(lesson["checks"], pages, prefix))

    concepts = [c for c in page.meta.get("concepts", []) if c in pages]
    cards = "".join(
        f'<button class="card" aria-pressed="false"><span class="card-front">{esc(pages[c].meta["title"])}</span>'
        f'<span class="card-back">{esc(pages[c].meta.get("definition", ""))}'
        f'<a href="{prefix}concepts/{c}.html">{t("open")}</a></span></button>'
        for c in concepts)
    out.append(f'<section class="flashcards"><h2 id="key-concepts">{t("key_concepts")}</h2>'
               f'<p class="muted">{t("flashcards_hint")}</p>'
               f'<div class="cards">{cards}</div></section>')

    if slug in quizzes:
        quiz = quizzes[slug]
        out.append(f'<section class="quiz-cta"><div><h2 id="quiz"><span class="sec-icon">★</span>{t("test_yourself")}</h2>'
                   f'<p class="muted">{t("quiz_cta", n=len(quiz["questions"]), m=quiz_minutes(quiz))}</p>'
                   f'<span class="chip chip-score" data-quiz-score="{slug}" hidden></span></div>'
                   f'<a class="btn btn-primary btn-lg" href="{prefix}quizzes/{slug}.html">{t("take_quiz")}</a></section>')

    i = order.index(slug)
    prev_ = f'<a class="pn prev" href="{order[i - 1]}.html"><small>{t("previous")}</small>{esc(pages[order[i - 1]].meta["title"])}</a>' if i > 0 else "<span></span>"
    next_ = f'<a class="pn next" href="{order[i + 1]}.html"><small>{t("next_topic")}</small>{esc(pages[order[i + 1]].meta["title"])}</a>' if i < len(order) - 1 else "<span></span>"
    out.append(f'<div class="complete"><button class="btn btn-primary btn-lg" data-complete="{slug}">'
               f'{t("mark_complete")}</button></div><nav class="prevnext">{prev_}{next_}</nav>')
    out.append(sources_footer(page, pages, prefix))
    return layout(page.meta["title"], f'<article class="topic">{"".join(out)}</article>',
                  curriculum, pages, prefix, current=slug)


def sources_footer(page: Page, pages, prefix) -> str:
    rows = []
    for s in page.meta.get("sources") or []:
        doc = s["doc"] if isinstance(s, dict) else s
        title = pages[doc].meta["title"] if doc in pages else doc
        section = f' — {esc(s["section"])}' if isinstance(s, dict) and s.get("section") else ""
        rows.append(f'<li><a href="{prefix}sources/{doc}.html">{esc(title)}</a>{section}</li>')
    return f'<footer class="sources"><h2>{t("sources")}</h2><ul>{"".join(rows)}</ul></footer>' if rows else ""


def concept_page(page: Page, pages, curriculum, backlinks) -> str:
    prefix = "../"
    used_in = [s for s in backlinks.get(page.slug, []) if pages[s].kind == "topic"]
    related = [r for r in page.meta.get("related") or [] if r in pages]
    aliases = page.meta.get("aliases") or []
    aka = f'<p class="aka">{t("also_called")} {", ".join(esc(a) for a in aliases)}</p>' if aliases else ""
    side = ""
    if used_in:
        side += f'<h3>{t("taught_in")}</h3><ul>' + "".join(
            f'<li><a href="{prefix}topics/{t}.html">{esc(pages[t].meta["title"])}</a></li>' for t in used_in) + "</ul>"
    if related:
        side += f'<h3>{t("related")}</h3><ul>' + "".join(
            f'<li><a class="wl wl-concept" data-slug="{r}" href="{prefix}{FOLDER[pages[r].kind]}/{r}.html">'
            f'{esc(pages[r].meta["title"])}</a></li>' for r in related) + "</ul>"
    body = (f'<article class="concept"><header class="page-head"><p class="eyebrow">{t("concept")}</p>'
            f'<h1>{esc(page.meta["title"])}</h1>{aka}</header>'
            f'<div class="definition"><span>{t("definition")}</span><p>{esc(page.meta.get("definition", ""))}</p></div>'
            f'<div class="concept-grid"><div class="prose">{render_md(localize_headings(page.body), pages, prefix)}</div>'
            f'<aside class="concept-side">{side}</aside></div>{sources_footer(page, pages, prefix)}</article>')
    return layout(page.meta["title"], body, curriculum, pages, prefix)


def source_page(page: Page, pages, curriculum) -> str:
    prefix = "../"
    meta = page.meta
    by = ", ".join(meta.get("authors") or [])
    extra = " · ".join(esc(x) for x in [by, meta.get("year"), meta.get("published")] if x)
    url = f'<p><a href="{esc(meta["url"])}">{t("original_document")}</a></p>' if meta.get("url") else ""
    body = (f'<article class="source"><header class="page-head"><p class="eyebrow">{t("source_document")}</p>'
            f'<h1>{esc(meta["title"])}</h1><p class="muted">{extra}</p>{url}</header>'
            f'<div class="prose">{render_md(localize_headings(page.body), pages, prefix)}</div></article>')
    return layout(meta["title"], body, curriculum, pages, prefix)


def index_page(pages, curriculum, lessons, quizzes) -> str:
    prefix = ""
    mods = []
    for n, module in enumerate(curriculum["modules"], 1):
        items = []
        for slug in module["topics"]:
            p = pages[slug]
            score = f'<span class="chip chip-score" data-quiz-score="{slug}" hidden></span>' if slug in quizzes else ""
            items.append(
                f'<li><a class="topic-row" href="topics/{slug}.html" data-topic="{slug}">'
                f'<span class="done-dot" aria-hidden="true"></span><span class="tr-main">'
                f'<span class="tr-title">{esc(p.meta["title"])}</span>'
                f'<span class="tr-sum">{esc(p.meta.get("summary", ""))}</span></span>'
                f'<span class="tr-meta">{difficulty_chip(p.meta.get("difficulty", ""))}'
                f'<span class="chip">{t("min", n=minutes(p, lessons.get(slug)))}</span>'
                f'{score}</span></a></li>')
        mods.append(f'<section class="module-card"><div class="module-head"><span class="mod-num">{n}</span>'
                    f'<div><h2>{esc(module["title"])}</h2><p class="muted">{esc(module.get("summary", ""))}</p>'
                    f'</div></div><ul class="topic-list">{"".join(items)}</ul></section>')
    counts = {k: sum(p.kind == k for p in pages.values()) for k in FOLDER}
    first = curriculum["modules"][0]["topics"][0]
    body = (f'<div class="home"><header class="hero"><p class="eyebrow">{t("learning_path")}</p>'
            f'<h1>{esc(curriculum.get("title", t("kb_title")))}</h1>'
            f'<p class="lead">{t("home_lead", topics=counts["topic"], modules=len(curriculum["modules"]), concepts=counts["concept"], sources=counts["source"])}</p>'
            f'<div class="hero-progress"><div class="bar bar-lg"><span data-progress-bar></span></div>'
            f'<span data-progress-text></span></div>'
            f'<a class="btn btn-primary btn-lg" data-continue href="topics/{first}.html">{t("start")}</a>'
            f'</header><div class="search"><input type="search" placeholder="{t("search_placeholder")}" '
            f'aria-label="{t("search")}" data-search><ul class="search-results" hidden></ul></div>'
            f'{"".join(mods)}</div>')
    return layout(curriculum.get("title", t("home")), body, curriculum, pages, prefix, body_class="is-home")


def glossary_page(pages, curriculum) -> str:
    prefix = ""
    concepts = sorted((p for p in pages.values() if p.kind == "concept"),
                      key=lambda p: p.meta["title"].lstrip(".").lower())
    rows = "".join(
        f'<li data-filter="{esc((p.meta["title"] + " " + " ".join(p.meta.get("aliases") or [])).lower())}">'
        f'<a href="concepts/{p.slug}.html">{esc(p.meta["title"])}</a>'
        f'<p>{esc(p.meta.get("definition", ""))}</p></li>' for p in concepts)
    body = (f'<article class="glossary"><header class="page-head"><p class="eyebrow">{t("reference")}</p>'
            f'<h1>{t("glossary")}</h1><p class="lead">{t("glossary_lead")}</p></header>'
            f'<input type="search" class="filter" placeholder="{t("filter")}" aria-label="{t("filter_glossary")}" data-filter-input>'
            f'<ul class="gloss-list">{rows}</ul></article>')
    return layout(t("glossary"), body, curriculum, pages, prefix)


# ---------------------------------------------------------------- build


def data_js(pages, curriculum) -> str:
    data = {
        "topics": [{"slug": t, "title": pages[t].meta["title"], "summary": pages[t].meta.get("summary", ""),
                    "objectives": len(objectives(pages[t]))}
                   for m in curriculum["modules"] for t in m["topics"]],
        "concepts": {s: {"title": p.meta["title"], "definition": p.meta.get("definition", ""),
                         "aliases": p.meta.get("aliases") or []}
                     for s, p in pages.items() if p.kind == "concept"},
        **i18n.js_strings(),
    }
    return "window.KB = " + json.dumps(data, ensure_ascii=False) + ";\n"


def code_css() -> str:
    light = HtmlFormatter(style="friendly").get_style_defs(".hl")
    dark = HtmlFormatter(style="github-dark").get_style_defs(".hl")
    return (f"{light}\n@media (prefers-color-scheme: dark) {{\n{dark}\n}}\n"
            ".hl, .hl pre { background: transparent !important; }\n")


def load_extras(pages: dict[str, Page], order: list[str], report: Report) -> tuple[dict, dict]:
    """Load and validate every topic's lesson and quiz files."""
    lessons = {t: lesson for t in order if (lesson := load_lesson(t, pages, report))}
    quizzes = {t: quiz for t in order if t in pages
               and (quiz := load_quiz(t, len(objectives(pages[t])), pages, report))}
    return lessons, quizzes


def build(only: list[str] | None = None) -> int:
    if not CURRICULUM.exists():
        print(NO_KB)
        return 1
    i18n.use()
    report = Report()
    pages = load_pages(report)
    curriculum = read_json(CURRICULUM)
    check(pages, read_json(MANIFEST), curriculum, report)
    order = [t for m in curriculum.get("modules", []) for t in m["topics"]]
    lessons, quizzes = load_extras(pages, order, report)
    for slug in only or []:
        if slug not in order:
            report.error(f"unknown topic '{slug}'")
    if report.errors:
        for msg in report.errors:
            print(f"ERROR  {msg}")
        print("site not built; fix the errors above (see `uv run learnkb-check`)")
        return 1

    backlinks: dict[str, list[str]] = {}
    for p in pages.values():
        for target in p.links:
            backlinks.setdefault(target, []).append(p.slug)

    for msg in report.warnings:
        if msg.startswith(("quizzes/", "lessons/")):
            print(f"WARN   {msg}")

    if not only:
        # A full build starts clean, so pages from another knowledge base (e.g. after
        # switching learning branches) or from removed pages don't linger.
        for folder in ["topics", "concepts", "sources", "quizzes"]:
            shutil.rmtree(SITE / folder, ignore_errors=True)
    for folder in ["topics", "concepts", "sources", "quizzes", "assets"]:
        (SITE / folder).mkdir(parents=True, exist_ok=True)
    for asset in ASSETS.iterdir():
        shutil.copy(asset, SITE / "assets" / asset.name)
    (SITE / "assets" / "code.css").write_text(code_css())
    (SITE / "assets" / "data.js").write_text(data_js(pages, curriculum))
    (SITE / "index.html").write_text(index_page(pages, curriculum, lessons, quizzes))
    (SITE / "glossary.html").write_text(glossary_page(pages, curriculum))

    topics = only or order
    for slug in topics:
        (SITE / "topics" / f"{slug}.html").write_text(
            topic_page(pages[slug], pages, curriculum, lessons, quizzes, order))
        if slug in quizzes:
            (SITE / "quizzes" / f"{slug}.html").write_text(quiz_page(pages[slug], quizzes[slug], pages, curriculum))
    # Concept and source pages are cheap and linked from everywhere: always rebuild them.
    for p in pages.values():
        if p.kind == "concept":
            (SITE / "concepts" / f"{p.slug}.html").write_text(concept_page(p, pages, curriculum, backlinks))
        elif p.kind == "source":
            (SITE / "sources" / f"{p.slug}.html").write_text(source_page(p, pages, curriculum))

    with_lessons = [t for t in topics if t in lessons]
    print(f"built {len(topics)} topic page(s) ({len(with_lessons)} with lessons, "
          f"{sum(t in quizzes for t in topics)} with quizzes), "
          f"{sum(p.kind == 'concept' for p in pages.values())} concept pages -> {SITE.relative_to(ROOT)}/")
    without = [t for t in order if t not in lessons]
    if without:
        print(f"topics without a lesson file: {', '.join(without)}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("topics", nargs="*", help="only rebuild these topic pages (default: all)")
    parser.add_argument("--open", action="store_true", help="open the result in a browser")
    args = parser.parse_args()
    code = build(args.topics or None)
    if code == 0 and args.open:
        target = SITE / ("topics/" + args.topics[0] + ".html" if args.topics else "index.html")
        webbrowser.open(target.as_uri())
    sys.exit(code)


if __name__ == "__main__":
    main()
