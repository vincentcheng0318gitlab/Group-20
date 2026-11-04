"""Presentation layer: the default table view, legacy text lines and JSON.

Only this module knows about ``rich``; the engine in :mod:`typo_guard.core`
stays dependency-light and returns plain :class:`~typo_guard.core.Diagnostic`
objects that any reporter can format.
"""

from __future__ import annotations

import json
from typing import Optional, Sequence

from rich import box
from rich.cells import cell_len
from rich.console import Console
from rich.table import Table
from rich.text import Text

from .core import Diagnostic
from .runner import FileError, ScanResult

STYLE_LOCATION = "cyan"
STYLE_KIND = "magenta"
STYLE_IDENTIFIER = ""
STYLE_MISSPELLED = "bold red underline"
STYLE_SUGGESTIONS = "green"
STYLE_NONE = "dim italic"

COLUMNS = ("Location", "Kind", "Identifier", "Misspelled", "Suggestions")
# Medium-width terminals (e.g. the classic 80 columns): one table per file,
# with the path printed once as a heading and only "line:col" in the rows.
GROUPED_COLUMNS = ("Line:Col", "Kind", "Identifier", "Misspelled", "Suggestions")
_HUGE_WIDTH = 100_000


def make_console(*, stderr: bool = False, color: str = "auto") -> Console:
    """Create a console for stdout/stderr honouring ``auto|always|never``.

    ``auto`` lets rich decide (colour on a TTY, plain text when piped, and the
    ``NO_COLOR`` / ``FORCE_COLOR`` environment variables are respected).
    """
    options: dict = {"stderr": stderr, "highlight": False, "markup": False, "emoji": False}
    if color == "never":
        options.update(no_color=True, color_system=None)
    elif color == "always":
        options.update(force_terminal=True)
    return Console(**options)


def _is_interactive(console: Console) -> bool:
    try:
        return bool(console.file.isatty())
    except (AttributeError, OSError, ValueError):
        return False


def _plural(count: int, singular: str, plural: Optional[str] = None) -> str:
    return f"{count} {singular if count == 1 else (plural or singular + 's')}"


def _mark(console: Console, fancy: str, plain: str) -> str:
    encoding = (console.encoding or "").lower().replace("-", "")
    return fancy if encoding.startswith("utf") else plain


def source_fragment(diagnostic: Diagnostic) -> str:
    """Return the misspelled word exactly as it is written in the identifier.

    The engine reports words in lower case (``reponse``); the table shows the
    original spelling (``Reponse``) so it can be found in the code at a glance.
    """
    name = diagnostic.identifier
    lowered = name.lower()
    if len(lowered) == len(name):  # lower() can change length for some scripts
        index = lowered.find(diagnostic.word)
        if index >= 0:
            return name[index:index + len(diagnostic.word)]
    return diagnostic.word


def _location_cell(item: Diagnostic, grouped: bool) -> str:
    return f"{item.line}:{item.column}" if grouped else item.location


def build_table(diagnostics: Sequence[Diagnostic], *, grouped: bool = False) -> Table:
    """Build the five-column findings table.

    ``grouped=True`` builds the per-file variant whose first column is
    ``Line:Col`` (the file path is printed once above the table instead).
    """
    headers = GROUPED_COLUMNS if grouped else COLUMNS
    table = Table(box=box.HEAVY_HEAD, header_style="bold", show_edge=True, pad_edge=True)
    # Only Suggestions may wrap (cleanly, after a comma).  A split
    # "file.py:3:1" is no longer clickable and a folded identifier is
    # unreadable, so narrow terminals get the compact layout instead.
    table.add_column(headers[0], style=STYLE_LOCATION, no_wrap=True)
    table.add_column(headers[1], style=STYLE_KIND, no_wrap=True)
    table.add_column(headers[2], style=STYLE_IDENTIFIER, no_wrap=True)
    table.add_column(headers[3], no_wrap=True)
    table.add_column(headers[4], style=STYLE_SUGGESTIONS, overflow="fold")
    for item in diagnostics:
        suggestions = (
            Text(", ".join(item.suggestions))
            if item.suggestions
            else Text("(none)", style=STYLE_NONE)
        )
        # Text(...) everywhere: paths such as "data[1]/x.py" must not be parsed as markup.
        table.add_row(
            Text(_location_cell(item, grouped)),
            Text(item.kind),
            Text(item.identifier),
            Text(source_fragment(item), style=STYLE_MISSPELLED),
            suggestions,
        )
    return table


def _minimum_width(diagnostics: Sequence[Diagnostic], grouped: bool) -> int:
    headers = GROUPED_COLUMNS if grouped else COLUMNS
    fixed = [cell_len(header) for header in headers[:4]]
    suggestion_min = cell_len(headers[4])
    for item in diagnostics:
        values = (_location_cell(item, grouped), item.kind, item.identifier, source_fragment(item))
        fixed = [max(width, cell_len(value)) for width, value in zip(fixed, values)]
        for word in item.suggestions or ("(none)",):
            suggestion_min = max(suggestion_min, cell_len(word) + 1)  # "word,"
    padding_and_borders = len(headers) * 2 + len(headers) + 1
    return sum(fixed) + suggestion_min + padding_and_borders


def minimum_table_width(diagnostics: Sequence[Diagnostic]) -> int:
    """Narrowest width at which the full table renders without breaking a cell."""
    return _minimum_width(diagnostics, grouped=False)


def minimum_grouped_width(diagnostics: Sequence[Diagnostic]) -> int:
    """Narrowest width for the per-file tables (path shown once as a heading)."""
    return _minimum_width(diagnostics, grouped=True)


def _render_grouped(diagnostics: Sequence[Diagnostic], console: Console) -> None:
    """One table per file for medium-width terminals (e.g. 80 columns)."""
    groups: dict[str, list[Diagnostic]] = {}
    for item in diagnostics:
        groups.setdefault(item.path, []).append(item)
    for index, (path, items) in enumerate(groups.items()):
        if index:
            console.print()
        console.print(
            Text.assemble(
                (path, f"bold {STYLE_LOCATION}"),
                (f"  {_plural(len(items), 'possible typo')}", "dim"),
            ),
            soft_wrap=True,
        )
        console.print(build_table(items, grouped=True))


def _render_compact(diagnostics: Sequence[Diagnostic], console: Console) -> None:
    """Stacked layout for terminals too narrow for the table."""
    arrow = _mark(console, " \u2192 ", " -> ")
    for item in diagnostics:
        console.print(
            Text.assemble(
                (item.location, STYLE_LOCATION), "  ", (item.kind, STYLE_KIND), " ", item.identifier,
            )
        )
        suggestions = (
            (", ".join(item.suggestions), STYLE_SUGGESTIONS)
            if item.suggestions
            else ("(no suggestions)", STYLE_NONE)
        )
        console.print(Text.assemble("  ", (source_fragment(item), STYLE_MISSPELLED), arrow, suggestions))


def _fit_width(console: Console, table: Table) -> None:
    """Never crop cells when output goes to a file, pipe or CI log."""
    if _is_interactive(console):
        return
    needed = console.measure(table, options=console.options.update_width(_HUGE_WIDTH)).maximum
    if needed > console.width:
        console.width = needed


def summary_text(result: ScanResult, console: Console) -> Text:
    """One-line verdict printed under the table."""
    scanned = _plural(len(result.files), "file")
    if result.diagnostics:
        verdict = Text.assemble(
            (_mark(console, "\u2716 ", "x "), "bold red"),
            (f"Found {_plural(len(result.diagnostics), 'possible typo')}", "bold red"),
            f" in {_plural(result.affected_identifiers, 'identifier')}"
            f" across {_plural(result.affected_files, 'file')}",
            (f" ({scanned} scanned)", "dim"),
        )
    elif result.errors:
        verdict = Text.assemble(
            (_mark(console, "\u26a0 ", "! "), "bold yellow"),
            ("No possible typos found in the files that could be analysed", "bold yellow"),
            (f" ({scanned} scanned)", "dim"),
        )
    else:
        verdict = Text.assemble(
            (_mark(console, "\u2714 ", "ok "), "bold green"),
            ("No possible typos found", "bold green"),
            (f" ({scanned} scanned)", "dim"),
        )
    if result.errors:
        verdict.append(
            f"; {_plural(len(result.errors), 'file')} could not be analysed (see errors above)",
            style="bold yellow",
        )
    verdict.append(".")
    return verdict


def render_table(result: ScanResult, console: Optional[Console] = None, *, hint: bool = True) -> None:
    """Print the table view (default output format).

    Layout adapts to the terminal: the full five-column table when it fits,
    per-file tables when only the long ``path:line:col`` cells do not fit, and
    a compact two-line-per-finding list on very narrow terminals.  Output that
    is piped or redirected always gets the full table at its natural width.
    """
    console = console or make_console()
    # Logs and pipes get one unbroken line per message; terminals word-wrap.
    soft = not _is_interactive(console)
    if result.diagnostics:
        table = build_table(result.diagnostics)
        _fit_width(console, table)
        if console.width >= minimum_table_width(result.diagnostics):
            console.print(table)
        elif console.width >= minimum_grouped_width(result.diagnostics):
            _render_grouped(result.diagnostics, console)
        else:
            _render_compact(result.diagnostics, console)
        console.print()
    console.print(summary_text(result, console), soft_wrap=soft)
    if hint and result.diagnostics:
        console.print(
            Text(
                "Tip: accept project-specific words with --allow WORD or --allowlist FILE.",
                style="dim",
            ),
            soft_wrap=soft,
        )


def render_text(result: ScanResult) -> str:
    """Legacy 0.1.x format: one ``path:line:col: TG001 ...`` line per finding."""
    lines = [item.format_text() for item in result.diagnostics]
    lines.append(f"Found {len(result.diagnostics)} possible typo(s).")
    return "\n".join(lines)


def render_json(result: ScanResult) -> str:
    """Machine-readable list of findings (same schema as 0.1.x)."""
    return json.dumps([item.to_dict() for item in result.diagnostics], indent=2)


def render_message(console: Console, level: str, message: str) -> None:
    """Print ``typo-guard: <level>: <message>`` (used for stderr notices)."""
    style = {"error": "bold red", "warning": "yellow"}.get(level, "")
    console.print(
        Text.assemble("typo-guard: ", (f"{level}:", style), " ", message),
        soft_wrap=True,
    )


def render_errors(errors: Sequence[FileError], console: Console) -> None:
    for error in errors:
        render_message(console, "error", error.format_text())
