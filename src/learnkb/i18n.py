"""Interface strings for the learning site, in each supported language.

A knowledge base picks its language in kb/site.json: {"lang": "pl"}. Without it the
site is in English. Only the interface is translated: page content is written in
whatever language the wiki uses, and the section headings and frontmatter keys in kb/
stay English, because the scripts and skills look pages up by them.

Templates use {name} for a value and {word:count} for a word whose form depends on a
count, e.g. "{n} {question:n}". A word is a dict of plural forms (one, few, many,
other); a key missing from a language falls back to English.
"""

import json
import re
import sys

from learnkb.ingest import KB

SITE_CONFIG = KB / "site.json"

EN = {
    # layout and navigation
    "kb_title": "Knowledge base",
    "home": "Home",
    "skip": "Skip to content",
    "open_menu": "Open course menu",
    "course": "Course",
    "glossary": "Glossary",
    "previous": "Previous",
    "next_topic": "Next",
    "sources": "Sources",
    "min": "~{n} min",
    # difficulty chips
    "beginner": "beginner",
    "intermediate": "intermediate",
    "advanced": "advanced",
    # section headings in kb/ pages, keyed by the English heading in lower case
    "heading:overview": "Overview",
    "heading:walkthrough": "Walkthrough",
    "heading:common pitfalls": "Common pitfalls",
    "heading:summary": "Summary",
    "heading:explanation": "Explanation",
    "heading:example": "Example",
    "heading:related": "Related",
    "heading:contents": "Contents",
    "heading:parsing notes": "Parsing notes",
    "heading:source disagreements": "Source disagreements",
    "callout:note": "Note",
    "callout:parsing note": "Parsing note",
    # topic page
    "before_this": "Before this:",
    "imagine": "Imagine this",
    "objectives": "By the end you can…",
    "objectives_hint": "Tick each one off when you feel confident.",
    "try_it": "Try it step by step",
    "step_of": "Step {i} of {n}",
    "show_all": "Show all",
    "one_at_a_time": "One at a time",
    "back": "← Back",
    "next": "Next →",
    "done": "Done ✓",
    "go_to_step": "Go to step {n}",
    "check_yourself": "Check yourself",
    "check_hint": "Answer in your head first, then reveal.",
    "reveal": "Reveal answer",
    "key_concepts": "Key concepts",
    "flashcards_hint": "Recall the definition, then flip the card to check.",
    "open": "Open →",
    "test_yourself": "Test yourself",
    "quiz_cta": "{n} {question:n} · ~{m} min. Find out which objectives you've mastered and which need another look.",
    "take_quiz": "Take the quiz →",
    "mark_complete": "Mark topic as complete",
    "completed_undo": "✓ Completed — click to undo",
    # concept, source, home and glossary pages
    "concept": "Concept",
    "also_called": "Also called:",
    "definition": "Definition",
    "taught_in": "Taught in",
    "related": "Related",
    "source_document": "Source document",
    "original_document": "Original document ↗",
    "learning_path": "Your learning path",
    "home_lead": ("{topics} {topic:topics} in {modules} {module:modules}, {concepts} {concept_w:concepts}, "
                  "built from {sources} source {document:sources}."),
    "start": "Start learning →",
    "search": "Search",
    "search_placeholder": "Search topics and concepts…",
    "search_topic": "Topic · ",
    "search_concept": "Concept · ",
    "no_matches": "No matches",
    "reference": "Reference",
    "glossary_lead": "Every concept in the knowledge base, A–Z.",
    "filter": "Filter…",
    "filter_glossary": "Filter glossary",
    # progress
    "progress": "{done} of {total} topics complete",
    "continue": "Continue: {title} →",
    "all_complete": "All topics complete ✓",
    # quiz page
    "assessment": "Assessment",
    "quiz_title": "Quiz: {title}",
    "quiz_intro": ("{n} {question:n} covering every learning objective. "
                   "Answer them all, then check your answers to see what you've mastered."),
    "n_questions": "{n} {question:n}",
    "back_to_lesson": "Back to the lesson",
    "question_n": "Question {n}",
    "your_answer": "Your answer to question {n}",
    "answer_placeholder": "Answer in your own words…",
    "model_answer": "Model answer",
    "tick_points": "Tick each point your answer covered:",
    "none_of_these": "None of these",
    "select_all": "Select all that apply.",
    "self_note": ("Includes {n} {written_answer:n} you grade yourself: "
                  "tick the points you covered and the score updates."),
    "your_results": "Your results",
    "by_objective": "By learning objective",
    "copy_results": "Copy results for Claude",
    "copy_below": "Copy the text below",
    "copied": "Copied ✓ Paste it into Claude",
    "retake": "Retake",
    "copy_help": ("Paste the results into Claude Code with <code>/assess</code> for feedback on your "
                  "written answers and what to review next."),
    "saved": ("Saved for Claude: run <code>/assess</code> in Claude Code for feedback on your written "
              "answers and what to review next. No copying needed."),
    "results_text": "Results text",
    "check_answers": "Check answers",
    "noscript_quiz": "This quiz needs JavaScript to grade your answers.",
    "last_quiz": "Last quiz: {pct}%",
    "unanswered": "{n} {question:n} unanswered",
    "all_answered": "All questions answered",
    "not_graded_hint": "Not graded yet: tick the points you covered",
    "points_of": "{got} of {n} points",
    "correct": "✓ Correct",
    "not_quite": "✗ Not quite",
    "solid": "Solid",
    "shaky": "Shaky",
    "review": "Review",
    "not_graded": "Not graded yet",
    "not_tested": "Not tested",
    "so_far": ("So far, with {n} {written_answer:n} not graded yet. "
               "Tick the points each answer covered (or None of these) to finish."),
    "verdict_good": "You know this topic well.",
    "verdict_ok": "Good start: a few gaps to close.",
    "verdict_bad": "Worth another pass through the lesson.",
    # words with plural forms
    "question": {"one": "question", "other": "questions"},
    "written_answer": {"one": "written answer", "other": "written answers"},
    "topic": {"one": "topic", "other": "topics"},
    "module": {"one": "module", "other": "modules"},
    "concept_w": {"one": "concept", "other": "concepts"},
    "document": {"one": "document", "other": "documents"},
}

PL = {
    "kb_title": "Baza wiedzy",
    "home": "Start",
    "skip": "Przejdź do treści",
    "open_menu": "Otwórz menu kursu",
    "course": "Kurs",
    "glossary": "Słowniczek",
    "previous": "Poprzedni",
    "next_topic": "Następny",
    "sources": "Źródła",
    "beginner": "podstawowy",
    "intermediate": "średni",
    "advanced": "zaawansowany",
    "heading:overview": "Wprowadzenie",
    "heading:walkthrough": "Omówienie",
    "heading:common pitfalls": "Częste pułapki",
    "heading:summary": "Podsumowanie",
    "heading:explanation": "Wyjaśnienie",
    "heading:example": "Przykład",
    "heading:related": "Powiązania",
    "heading:contents": "Zawartość",
    "heading:parsing notes": "Uwagi o konwersji",
    "heading:source disagreements": "Rozbieżności między źródłami",
    "callout:note": "Uwaga",
    "callout:parsing note": "Uwaga o konwersji",
    "before_this": "Najpierw:",
    "imagine": "Wyobraź sobie",
    "objectives": "Po tej lekcji potrafisz…",
    "objectives_hint": "Odhacz każdy cel, gdy poczujesz się pewnie.",
    "try_it": "Krok po kroku",
    "step_of": "Krok {i} z {n}",
    "show_all": "Pokaż wszystko",
    "one_at_a_time": "Po jednym kroku",
    "back": "← Wstecz",
    "next": "Dalej →",
    "done": "Gotowe ✓",
    "go_to_step": "Przejdź do kroku {n}",
    "check_yourself": "Sprawdź się",
    "check_hint": "Najpierw odpowiedz w myślach, potem odsłoń odpowiedź.",
    "reveal": "Pokaż odpowiedź",
    "key_concepts": "Kluczowe pojęcia",
    "flashcards_hint": "Przypomnij sobie definicję, potem odwróć kartę, żeby sprawdzić.",
    "open": "Otwórz →",
    "test_yourself": "Sprawdzian",
    "quiz_cta": "{n} {question:n} · ~{m} min. Sprawdź, które cele masz już opanowane, a które trzeba powtórzyć.",
    "take_quiz": "Rozwiąż quiz →",
    "mark_complete": "Oznacz temat jako ukończony",
    "completed_undo": "✓ Ukończony — kliknij, aby cofnąć",
    "concept": "Pojęcie",
    "also_called": "Inne nazwy:",
    "definition": "Definicja",
    "taught_in": "Omawiane w",
    "related": "Powiązane",
    "source_document": "Dokument źródłowy",
    "original_document": "Oryginalny dokument ↗",
    "learning_path": "Twoja ścieżka nauki",
    "home_lead": ("{topics} {topic:topics} w {modules} {module_loc:modules}, {concepts} {concept_w:concepts}, "
                  "na podstawie {sources} {document_gen:sources}."),
    "start": "Zacznij naukę →",
    "search": "Szukaj",
    "search_placeholder": "Szukaj tematów i pojęć…",
    "search_topic": "Temat · ",
    "search_concept": "Pojęcie · ",
    "no_matches": "Brak wyników",
    "reference": "Materiały",
    "glossary_lead": "Wszystkie pojęcia z bazy wiedzy, od A do Z.",
    "filter": "Filtruj…",
    "filter_glossary": "Filtruj słowniczek",
    "progress": "Ukończone tematy: {done} z {total}",
    "continue": "Dalej: {title} →",
    "all_complete": "Wszystkie tematy ukończone ✓",
    "assessment": "Sprawdzian",
    "quiz_intro": ("{n} {question:n} obejmujących wszystkie cele nauki. "
                   "Odpowiedz na wszystkie, a potem sprawdź odpowiedzi, żeby zobaczyć, co już umiesz."),
    "back_to_lesson": "Wróć do lekcji",
    "question_n": "Pytanie {n}",
    "your_answer": "Twoja odpowiedź na pytanie {n}",
    "answer_placeholder": "Odpowiedz własnymi słowami…",
    "model_answer": "Wzorcowa odpowiedź",
    "tick_points": "Zaznacz punkty, które obejmuje twoja odpowiedź:",
    "none_of_these": "Żadne z powyższych",
    "select_all": "Zaznacz wszystkie poprawne.",
    "self_note": ("Zawiera {n} {written_answer_acc:n} do samodzielnej oceny: "
                  "zaznacz punkty, które obejmuje twoja odpowiedź, a wynik się zaktualizuje."),
    "your_results": "Twoje wyniki",
    "by_objective": "Według celów nauki",
    "copy_results": "Kopiuj wyniki dla Claude'a",
    "copy_below": "Skopiuj tekst poniżej",
    "copied": "Skopiowano ✓ Wklej go do Claude'a",
    "retake": "Rozwiąż ponownie",
    "copy_help": ("Wklej wyniki do Claude Code razem z <code>/assess</code>, żeby dostać ocenę "
                  "odpowiedzi pisemnych i wskazówki, co powtórzyć."),
    "saved": ("Zapisano dla Claude'a: wpisz <code>/assess</code> w Claude Code, żeby dostać ocenę "
              "odpowiedzi pisemnych i wskazówki, co powtórzyć. Nie trzeba nic kopiować."),
    "results_text": "Tekst wyników",
    "check_answers": "Sprawdź odpowiedzi",
    "noscript_quiz": "Do oceny odpowiedzi ten quiz potrzebuje JavaScriptu.",
    "last_quiz": "Ostatni quiz: {pct}%",
    "unanswered": "{n} {question:n} bez odpowiedzi",
    "all_answered": "Wszystkie pytania mają odpowiedź",
    "not_graded_hint": "Jeszcze bez oceny: zaznacz punkty, które obejmuje twoja odpowiedź",
    "points_of": "Punkty: {got} z {n}",
    "correct": "✓ Dobrze",
    "not_quite": "✗ Niezupełnie",
    "solid": "Opanowane",
    "shaky": "Niepewne",
    "review": "Do powtórki",
    "not_graded": "Jeszcze bez oceny",
    "not_tested": "Nie sprawdzane",
    "so_far": ("Wynik częściowy: {n} {written_answer:n} bez oceny. Zaznacz punkty, które obejmuje "
               "każda odpowiedź (albo „Żadne z powyższych”), żeby dokończyć."),
    "verdict_good": "Znasz ten temat dobrze.",
    "verdict_ok": "Dobry początek, zostało kilka luk.",
    "verdict_bad": "Warto jeszcze raz przejść przez lekcję.",
    "question": {"one": "pytanie", "few": "pytania", "many": "pytań", "other": "pytania"},
    "written_answer": {"one": "odpowiedź pisemna", "few": "odpowiedzi pisemne",
                       "many": "odpowiedzi pisemnych", "other": "odpowiedzi pisemnej"},
    "written_answer_acc": {"one": "odpowiedź pisemną", "few": "odpowiedzi pisemne",
                           "many": "odpowiedzi pisemnych", "other": "odpowiedzi pisemnej"},
    "topic": {"one": "temat", "few": "tematy", "many": "tematów", "other": "tematu"},
    "module_loc": {"one": "module", "few": "modułach", "many": "modułach", "other": "modułu"},
    "concept_w": {"one": "pojęcie", "few": "pojęcia", "many": "pojęć", "other": "pojęcia"},
    "document_gen": {"one": "dokumentu źródłowego", "few": "dokumentów źródłowych",
                     "many": "dokumentów źródłowych", "other": "dokumentu źródłowego"},
}

LANGUAGES = {"en": EN, "pl": PL}

# The strings in use, set by use(). English until then.
lang = "en"
strings = EN


def plural_category(n: int, language: str) -> str:
    """The CLDR plural category of a whole number, matching Intl.PluralRules in app.js."""
    if language == "pl":
        if n == 1:
            return "one"
        if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
            return "few"
        return "many"
    return "one" if n == 1 else "other"


def fmt(template: str, words: dict, language: str, **values) -> str:
    def repl(m: re.Match) -> str:
        name, count = m.group(1), m.group(2)
        if count is None:
            return str(values[name])
        forms = words.get(name) or EN[name]
        return forms.get(plural_category(int(values[count]), language), forms["other"])
    return re.sub(r"\{(\w+)(?::(\w+))?\}", repl, template)


def t(key: str, **values) -> str:
    """The interface string `key` in the current language, filled in with `values`."""
    template = strings.get(key, EN.get(key, key))
    return fmt(template, strings, lang, **values) if values else template


def use(language: str | None = None) -> str:
    """Switch to `language`, or to the one kb/site.json names."""
    global lang, strings
    if language is None:
        try:
            language = json.loads(SITE_CONFIG.read_text()).get("lang", "en") if SITE_CONFIG.exists() else "en"
        except json.JSONDecodeError as exc:
            print(f"WARN   site.json: {exc}; using English", file=sys.stderr)
            language = "en"
    if language not in LANGUAGES:
        print(f"WARN   site.json: no interface strings for '{language}' "
              f"(have: {', '.join(LANGUAGES)}); using English", file=sys.stderr)
        language = "en"
    lang, strings = language, {**EN, **LANGUAGES[language]}
    return lang


def js_strings() -> dict:
    """The strings app.js needs: the current language, plus English for the results export."""
    return {"lang": lang, "strings": strings, "en": EN}
