"""The presentation layer: table layout, colours, widths and fallbacks."""

import io
import json

from rich.console import Console

from typo_guard.core import Diagnostic
from typo_guard.report import (
    COLUMNS,
    GROUPED_COLUMNS,
    STYLE_KIND,
    STYLE_LOCATION,
    STYLE_MISSPELLED,
    STYLE_SUGGESTIONS,
    build_table,
    minimum_grouped_width,
    minimum_table_width,
    render_json,
    render_table,
    render_text,
    source_fragment,
)
from typo_guard.runner import FileError, ScanResult

EXAMPLE = [
    Diagnostic("examples/example.py", 3, 1, "variable", "recieved_data", "recieved", ("received", "relieved")),
    Diagnostic("examples/example.py", 6, 1, "function", "calculate_avrage", "avrage", ("average",)),
    Diagnostic("examples/example.py", 6, 22, "argument", "innitial_value", "innitial", ("initial",)),
    Diagnostic("examples/example.py", 11, 1, "class", "ReponseFormatter", "reponse", ("response", "repose")),
]


class FakeTerminal(io.StringIO):
    """A StringIO that claims to be an interactive terminal."""

    def isatty(self):
        return True


class LegacyStream(io.StringIO):
    """A non-UTF-8 output stream such as an old Windows console."""

    encoding = "cp1252"


def result(diagnostics=EXAMPLE, files=("examples/example.py",), errors=()):
    return ScanResult(files=list(files), diagnostics=list(diagnostics), errors=list(errors))


def plain_console(width=200, file=None):
    return Console(file=file or io.StringIO(), width=width, color_system=None, highlight=False)


def test_table_has_the_five_columns_in_order():
    table = build_table(EXAMPLE)
    assert tuple(column.header for column in table.columns) == COLUMNS
    assert COLUMNS == ("Location", "Kind", "Identifier", "Misspelled", "Suggestions")


def test_table_column_styles_match_the_design():
    table = build_table(EXAMPLE)
    assert table.columns[0].style == STYLE_LOCATION == "cyan"
    assert table.columns[1].style == STYLE_KIND == "magenta"
    assert table.columns[4].style == STYLE_SUGGESTIONS == "green"
    misspelled_cells = list(table.columns[3].cells)
    assert all(str(cell.style) == STYLE_MISSPELLED == "bold red underline" for cell in misspelled_cells)


def test_table_rows_contain_every_finding():
    console = plain_console()
    render_table(result(), console)
    output = console.file.getvalue()
    for location in ("examples/example.py:3:1", "examples/example.py:6:22", "examples/example.py:11:1"):
        assert location in output
    assert "received, relieved" in output
    assert "Found 4 possible typos in 4 identifiers across 1 file (1 file scanned)." in output


def test_misspelled_column_shows_the_word_as_written_in_source():
    assert source_fragment(EXAMPLE[3]) == "Reponse"
    assert source_fragment(EXAMPLE[0]) == "recieved"
    camel = Diagnostic("x.py", 1, 1, "function", "setInnitialValue", "innitial", ())
    assert source_fragment(camel) == "Innitial"


def test_rows_without_suggestions_show_a_placeholder():
    console = plain_console()
    render_table(result([Diagnostic("x.py", 1, 1, "variable", "zzqx_value", "zzqx", ())]), console)
    assert "(none)" in console.file.getvalue()


def test_coloured_output_uses_ansi_styles():
    console = Console(file=io.StringIO(), width=200, force_terminal=True, color_system="truecolor")
    render_table(result(), console)
    output = console.file.getvalue()
    assert "\x1b[" in output
    assert "\x1b[1;4;31m" in output  # bold + underline + red for the misspelled word


def test_non_interactive_output_is_widened_instead_of_cropped():
    console = plain_console(width=40)
    render_table(result(), console)
    lines = console.file.getvalue().splitlines()
    assert any("examples/example.py:11:1" in line for line in lines)
    assert "\u2026" not in console.file.getvalue()  # no ellipsis anywhere
    assert max(len(line) for line in lines) > 40


def test_narrow_terminal_uses_compact_layout():
    console = Console(file=FakeTerminal(), width=60, color_system=None)
    render_table(result(), console)
    output = console.file.getvalue()
    assert "Location" not in output  # no table header
    assert "examples/example.py:3:1  variable recieved_data" in output
    assert "recieved \u2192 received, relieved" in output


def test_wide_terminal_uses_table_layout():
    console = Console(file=FakeTerminal(), width=minimum_table_width(EXAMPLE), color_system=None)
    render_table(result(), console)
    assert "Location" in console.file.getvalue()


def test_classic_80_column_terminal_gets_per_file_tables():
    assert minimum_grouped_width(EXAMPLE) <= 80 < minimum_table_width(EXAMPLE)
    console = Console(file=FakeTerminal(), width=80, color_system=None)
    render_table(result(), console)
    output = console.file.getvalue()
    lines = output.splitlines()
    assert lines[0] == "examples/example.py  4 possible typos"
    assert "Line:Col" in output and "Location" not in output
    assert "\u2502 11:1     \u2502 class    \u2502 ReponseFormatter \u2502 Reponse    \u2502 response, repose" in output
    assert max(len(line) for line in lines) <= 80


def test_per_file_tables_have_one_heading_per_file():
    two_files = [*EXAMPLE, Diagnostic("pkg/other.py", 2, 5, "argument", "totl", "totl", ("total",))]
    width = minimum_table_width(two_files) - 1
    assert width >= minimum_grouped_width(two_files)
    console = Console(file=FakeTerminal(), width=width, color_system=None)
    render_table(result(two_files, files=["examples/example.py", "pkg/other.py"]), console)
    output = console.file.getvalue()
    assert "examples/example.py  4 possible typos" in output
    assert "pkg/other.py  1 possible typo\n" in output
    assert output.count("Line:Col") == 2


def test_layout_tiers_switch_exactly_at_the_minimum_widths():
    def layout(width):
        console = Console(file=FakeTerminal(), width=width, color_system=None)
        render_table(result(), console)
        output = console.file.getvalue()
        return "full" if "Location" in output else "grouped" if "Line:Col" in output else "compact"

    full, grouped = minimum_table_width(EXAMPLE), minimum_grouped_width(EXAMPLE)
    assert [layout(full), layout(full - 1), layout(grouped), layout(grouped - 1)] == [
        "full", "grouped", "grouped", "compact",
    ]


def test_grouped_table_columns():
    table = build_table(EXAMPLE, grouped=True)
    assert tuple(column.header for column in table.columns) == GROUPED_COLUMNS
    assert [cell.plain for cell in table.columns[0].cells] == ["3:1", "6:1", "6:22", "11:1"]


def test_minimum_width_grows_with_content():
    longer = [*EXAMPLE, Diagnostic("a/very/long/path/to/module.py", 1, 1, "variable", "x_recieved", "recieved", ())]
    assert minimum_table_width(longer) > minimum_table_width(EXAMPLE)


def test_paths_with_brackets_are_not_treated_as_markup():
    diagnostic = Diagnostic("data[bold]/x.py", 1, 1, "variable", "recieved", "recieved", ())
    console = Console(file=io.StringIO(), width=200, force_terminal=True, color_system="truecolor")
    render_table(result([diagnostic], files=["data[bold]/x.py"]), console)
    assert "data[bold]/x.py:1:1" in console.file.getvalue()


def test_legacy_encoding_falls_back_to_ascii_symbols():
    console = Console(file=LegacyStream(), width=200, color_system=None)
    render_table(result(), console)
    output = console.file.getvalue()
    output.encode("cp1252")  # must not raise
    assert output.lstrip().startswith("+")  # ASCII box
    assert "x Found 4 possible typos" in output


def test_clean_summary_and_error_notice():
    console = plain_console()
    errors = [FileError("bad.py", "syntax error: invalid syntax", 1, 12)]
    render_table(result([], files=["ok.py", "bad.py"], errors=errors), console)
    output = console.file.getvalue()
    assert "\u2714" not in output  # never a green check mark when a file failed
    assert "No possible typos found in the files that could be analysed (2 files scanned)" in output
    assert "1 file could not be analysed" in output


def test_clean_summary_without_errors():
    console = plain_console()
    render_table(result([], files=["ok.py"]), console)
    assert console.file.getvalue().strip() == "\u2714 No possible typos found (1 file scanned)."


def test_summary_is_never_hard_wrapped():
    console = plain_console(width=30)
    errors = [FileError("bad.py", "syntax error: invalid syntax", 1, 12)]
    render_table(result([], files=["ok.py", "bad.py"], errors=errors), console)
    assert len(console.file.getvalue().strip().splitlines()) == 1


def test_render_text_is_the_legacy_line_format():
    text = render_text(result())
    lines = text.splitlines()
    assert lines[0] == (
        "examples/example.py:3:1: TG001 possible typo 'recieved' in variable "
        "'recieved_data' (suggestions: received, relieved)"
    )
    assert lines[-1] == "Found 4 possible typo(s)."


def test_render_json_keeps_the_original_schema():
    payload = json.loads(render_json(result()))
    assert isinstance(payload, list) and len(payload) == 4
    assert set(payload[0]) == {"path", "line", "column", "kind", "identifier", "word", "suggestions"}
    assert payload[3]["word"] == "reponse"
    assert json.loads(render_json(result([]))) == []
