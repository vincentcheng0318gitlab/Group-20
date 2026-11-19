"""Command-line behaviour: output formats, options and exit codes.

The first seven tests are the original 0.1.x CLI tests.  Because the default
output is now the table, the two tests that check the legacy one-line format
pass ``--format text`` explicitly; their assertions are unchanged.
"""

import json

import pytest

from typo_guard import __version__
from typo_guard.cli import main


# --- original 0.1.x tests ----------------------------------------------------

def test_cli_text_output_and_finding_exit_code(tmp_path, capsys):
    sample = tmp_path / "sample.py"
    sample.write_text("recieved_data = 1\n", encoding="utf-8")
    assert main(["lint", str(sample), "--format", "text"]) == 1
    output = capsys.readouterr().out
    assert "TG001" in output
    assert "recieved" in output


def test_cli_clean_exit_code(tmp_path, capsys):
    sample = tmp_path / "clean.py"
    sample.write_text("received_data = 1\n", encoding="utf-8")
    assert main(["lint", str(sample), "--format", "text"]) == 0
    assert "Found 0 possible typo(s)." in capsys.readouterr().out


def test_cli_json_output(tmp_path, capsys):
    sample = tmp_path / "sample.py"
    sample.write_text("innitial_value = 1\n", encoding="utf-8")
    assert main(["lint", str(sample), "--format", "json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["word"] == "innitial"
    assert payload[0]["identifier"] == "innitial_value"


def test_cli_inline_allow_word(tmp_path, capsys):
    sample = tmp_path / "sample.py"
    sample.write_text("frobnicator_value = 1\n", encoding="utf-8")
    assert main(["lint", str(sample), "--allow", "frobnicator"]) == 0
    capsys.readouterr()


def test_cli_allowlist_file(tmp_path, capsys):
    sample = tmp_path / "sample.py"
    sample.write_text("frobnicator_value = 1\n", encoding="utf-8")
    allowlist = tmp_path / "words.txt"
    allowlist.write_text("# project vocabulary\nfrobnicator\n", encoding="utf-8")
    assert main(["lint", str(sample), "--allowlist", str(allowlist)]) == 0
    capsys.readouterr()


def test_cli_british_english_option(tmp_path, capsys):
    sample = tmp_path / "british.py"
    sample.write_text(
        "colour_value = 1\nfavourite_colour = 1\norganise_centre = 1\ntravelling_data = 1\n",
        encoding="utf-8",
    )
    assert main(["lint", str(sample), "--language", "en-GB", "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_cli_custom_dictionary_file_applies_to_every_file(tmp_path, capsys):
    first = tmp_path / "first.py"
    second = tmp_path / "second.py"
    first.write_text("frobnicator_value = 1\n", encoding="utf-8")
    second.write_text("frobnicator_count = 2\n", encoding="utf-8")
    dictionary = tmp_path / "project-words.txt"
    dictionary.write_text("# product vocabulary\nfrobnicator,\n", encoding="utf-8")
    assert main([
        "lint", str(first), str(second), "--dictionary", str(dictionary), "--format", "json"
    ]) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_cli_missing_dictionary_file_is_a_user_error(tmp_path, capsys):
    sample = tmp_path / "sample.py"
    sample.write_text("received_value = 1\n", encoding="utf-8")
    assert main(["lint", str(sample), "--dictionary", str(tmp_path / "missing.txt")]) == 2
    assert "dictionary file not found" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("make_dictionary", "expected"),
    [
        ("directory", "dictionary is not a regular file"),
        ("binary", "dictionary must be UTF-8 text"),
    ],
)
def test_cli_invalid_dictionary_file_is_a_user_error(tmp_path, capsys, make_dictionary, expected):
    sample = tmp_path / "sample.py"
    sample.write_text("received_value = 1\n", encoding="utf-8")
    dictionary = tmp_path / "words.txt"
    if make_dictionary == "directory":
        dictionary.mkdir()
    else:
        dictionary.write_bytes(b"\xff\xfe")
    assert main(["lint", str(sample), "--dictionary", str(dictionary)]) == 2
    assert expected in capsys.readouterr().err


def test_cli_missing_path_is_usage_error(capsys):
    assert main(["lint", "does-not-exist.py"]) == 2
    assert "path not found" in capsys.readouterr().err


def test_cli_syntax_error_is_usage_error(tmp_path, capsys):
    sample = tmp_path / "broken.py"
    sample.write_text("def broken(:\n", encoding="utf-8")
    assert main(["lint", str(sample)]) == 2
    assert "invalid syntax" in capsys.readouterr().err


# --- 0.2.0: table view (default) --------------------------------------------

def test_default_output_is_a_table(tmp_path, capsys):
    sample = tmp_path / "sample.py"
    sample.write_text("recieved_data = 1\n", encoding="utf-8")
    assert main(["lint", str(sample)]) == 1
    output = capsys.readouterr().out
    header = next(line for line in output.splitlines() if "Location" in line)
    for column in ("Location", "Kind", "Identifier", "Misspelled", "Suggestions"):
        assert column in header
    assert header.index("Location") < header.index("Kind") < header.index("Identifier")
    assert header.index("Identifier") < header.index("Misspelled") < header.index("Suggestions")
    assert f"{sample}:1:1" in output  # never cropped, even though capsys is not a TTY
    assert "received" in output
    assert "Found 1 possible typo in 1 identifier across 1 file" in output
    assert "TG001" not in output


def test_table_reports_clean_run(tmp_path, capsys):
    sample = tmp_path / "clean.py"
    sample.write_text("received_data = 1\n", encoding="utf-8")
    assert main(["lint", str(sample)]) == 0
    output = capsys.readouterr().out
    assert "No possible typos found (1 file scanned)." in output
    assert "Location" not in output


def test_no_color_output_has_no_escape_codes(tmp_path, capsys):
    sample = tmp_path / "sample.py"
    sample.write_text("recieved_data = 1\n", encoding="utf-8")
    assert main(["lint", str(sample), "--no-color"]) == 1
    assert "\x1b[" not in capsys.readouterr().out


def test_color_always_emits_ansi_styles(tmp_path, capsys):
    sample = tmp_path / "sample.py"
    sample.write_text("recieved_data = 1\n", encoding="utf-8")
    assert main(["lint", str(sample), "--color", "always"]) == 1
    assert "\x1b[" in capsys.readouterr().out


def test_exit_zero_reports_but_does_not_fail(tmp_path, capsys):
    sample = tmp_path / "sample.py"
    sample.write_text("recieved_data = 1\n", encoding="utf-8")
    assert main(["lint", str(sample), "--exit-zero"]) == 0
    assert "recieved" in capsys.readouterr().out


def test_max_suggestions_zero_hides_suggestions(tmp_path, capsys):
    sample = tmp_path / "sample.py"
    sample.write_text("recieved_data = 1\n", encoding="utf-8")
    assert main(["lint", str(sample), "--format", "json", "--max-suggestions", "0"]) == 1
    assert json.loads(capsys.readouterr().out)[0]["suggestions"] == []


@pytest.mark.parametrize("value", ["-1", "three"])
def test_invalid_max_suggestions_is_usage_error(tmp_path, value, capsys):
    sample = tmp_path / "sample.py"
    sample.write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exit_info:
        main(["lint", str(sample), "--max-suggestions", value])
    assert exit_info.value.code == 2
    capsys.readouterr()


def test_all_missing_paths_are_listed(capsys):
    assert main(["lint", "missing_one.py", "missing_two.py"]) == 2
    err = capsys.readouterr().err
    assert "missing_one.py" in err and "missing_two.py" in err


def test_multiple_paths_and_comma_separated_allow(tmp_path, capsys):
    (tmp_path / "a.py").write_text("frobnicator_value = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("quuxify_value = 1\n", encoding="utf-8")
    args = ["lint", str(tmp_path / "a.py"), str(tmp_path / "b.py"), "--allow", "frobnicator,quuxify"]
    assert main(args) == 0
    capsys.readouterr()


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"typo-guard {__version__}"


def test_missing_subcommand_is_usage_error(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main([])
    assert exit_info.value.code == 2
    capsys.readouterr()
