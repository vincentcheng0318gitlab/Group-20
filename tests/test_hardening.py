"""Regression tests for the robustness fixes listed in CHANGELOG.md (0.2.0).

Each test reproduces an input that crashed, hung, misreported or produced
noise in 0.1.0, and pins the corrected behaviour.
"""

import os
import subprocess
import sys
import time
import warnings
from pathlib import Path

import pytest

from typo_guard import cli
from typo_guard.cli import main
from typo_guard.core import (
    _get_spellchecker,
    extract_identifiers,
    iter_python_files,
    lint_file,
    lint_paths,
    lint_source,
)
from typo_guard.runner import FileError, describe_error, scan_paths

POSIX_ONLY = pytest.mark.skipif(os.name == "nt", reason="POSIX-only file-system behaviour")


def run_module(*args, env=None, **kwargs):
    environment = dict(os.environ, **(env or {}))
    src = str(Path(__file__).resolve().parents[1] / "src")
    environment["PYTHONPATH"] = src + os.pathsep + environment.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "typo_guard", *map(str, args)],
        capture_output=True, env=environment, **kwargs,
    )


# --- 1. file decoding ----------------------------------------------------------

def test_utf8_bom_file_is_linted(tmp_path):
    path = tmp_path / "bom.py"
    path.write_bytes("\ufeffrecieved_data = 1\n".encode("utf-8"))
    [diagnostic] = lint_file(path)
    assert (diagnostic.word, diagnostic.line, diagnostic.column) == ("recieved", 1, 1)


def test_bom_in_source_string_is_accepted():
    assert [d.word for d in lint_source("\ufeffrecieved_data = 1\n")] == ["recieved"]


def test_pep263_encoding_declaration_is_respected(tmp_path):
    path = tmp_path / "latin.py"
    path.write_bytes(b"# -*- coding: latin-1 -*-\nrecieved_name = 'caf\xe9'\n")
    assert [d.word for d in lint_file(path)] == ["recieved"]


@pytest.mark.parametrize(
    "content",
    [
        b"name_value = '\x93quoted\x94'\n",                 # bad byte in line 1: tokenize's cookie check
        b"a = 1\nb = 2\nc = 3\nname_value = '\x93q\x94'\n",  # bad byte later: UnicodeDecodeError
    ],
    ids=["first-lines", "later-line"],
)
def test_undecodable_file_is_reported_not_raised(tmp_path, capsys, content):
    path = tmp_path / "cp1252.py"
    path.write_bytes(content)
    assert main(["lint", str(path)]) == 2
    err = capsys.readouterr().err
    assert "cannot decode file" in err
    assert "save it as UTF-8" in err
    assert "syntax error" not in err
    assert err.count(str(path)) == 1  # the path is not repeated inside the message


def test_unknown_encoding_declaration_is_reported(tmp_path, capsys):
    path = tmp_path / "odd.py"
    path.write_bytes(b"# -*- coding: klingon -*-\nx = 1\n")
    assert main(["lint", str(path)]) == 2
    assert "cannot decode file: unknown encoding" in capsys.readouterr().err


def test_source_bytes_are_accepted():
    assert [d.word for d in lint_source(b"recieved_data = 1\n")] == ["recieved"]


# --- 2. pathological sources --------------------------------------------------

def test_null_bytes_raise_syntax_error_on_every_python_version():
    with pytest.raises(SyntaxError):
        lint_source("x = 1\x00\n")


@pytest.mark.parametrize(
    "source",
    [
        "value = " + "-" * 50000 + "1\n",                 # MemoryError in the parser
        "value = " + "+".join(["1"] * 100000) + "\n",     # RecursionError
    ],
    ids=["deep-unary", "long-expression"],
)
def test_too_complex_source_becomes_syntax_error(source):
    with pytest.raises(SyntaxError):
        extract_identifiers(source, "deep.py")


def test_too_complex_file_exits_2_without_traceback(tmp_path):
    path = tmp_path / "deep.py"
    path.write_text("value = " + "-" * 50000 + "1\n", encoding="utf-8")
    proc = run_module("lint", path, text=True)
    assert proc.returncode == 2
    assert "Traceback" not in proc.stderr
    assert "deep.py" in proc.stderr


def test_scanned_files_warnings_are_not_printed():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert lint_source('pattern_value = "\\d+"\n') == []
    assert caught == []


def test_warnings_as_errors_do_not_break_linting():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert lint_source('pattern_value = "\\d+"\n') == []


def test_empty_and_comment_only_files_are_clean(tmp_path, capsys):
    (tmp_path / "empty.py").write_text("", encoding="utf-8")
    (tmp_path / "comment.py").write_text("# recieved\n", encoding="utf-8")
    assert main(["lint", str(tmp_path)]) == 0
    assert "No possible typos found (2 files scanned)" in capsys.readouterr().out


def test_crlf_line_endings(tmp_path):
    path = tmp_path / "crlf.py"
    path.write_bytes(b"x = 1\r\nrecieved_data = 2\r\n")
    assert [(d.word, d.line) for d in lint_file(path)] == [("recieved", 2)]


# --- 3. discovery ---------------------------------------------------------------

def test_directory_named_like_a_python_file_is_skipped(tmp_path):
    (tmp_path / "weird.py").mkdir()
    (tmp_path / "real.py").write_text("recieved = 1\n", encoding="utf-8")
    assert [path.name for path in iter_python_files([tmp_path])] == ["real.py"]
    assert [d.word for d in lint_paths([tmp_path])] == ["recieved"]


def test_virtualenvs_and_caches_are_skipped_by_default(tmp_path):
    (tmp_path / "main.py").write_text("received = 1\n", encoding="utf-8")
    for ignored in (".venv", "venv", "__pycache__", "node_modules", ".git", "build", "pkg.egg-info"):
        directory = tmp_path / ignored / "lib"
        directory.mkdir(parents=True)
        (directory / "py2.py").write_text("print 'python 2 syntax'\n", encoding="utf-8")
    found = {path.relative_to(tmp_path).as_posix() for path in iter_python_files([tmp_path])}
    assert found == {"main.py"}


def test_explicit_path_inside_excluded_directory_is_still_scanned(tmp_path):
    build = tmp_path / "build"
    build.mkdir()
    (build / "gen.py").write_text("recieved = 1\n", encoding="utf-8")
    assert [d.word for d in lint_paths([build])] == ["recieved"]
    assert [d.word for d in lint_paths([build / "gen.py"])] == ["recieved"]


def test_custom_exclude_patterns(tmp_path, capsys):
    (tmp_path / "migrations").mkdir()
    (tmp_path / "migrations" / "0001.py").write_text("recieved = 1\n", encoding="utf-8")
    (tmp_path / "api_pb2.py").write_text("recieved = 1\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("received = 1\n", encoding="utf-8")
    args = ["lint", str(tmp_path), "--exclude", "migrations", "--exclude", "*_pb2.py"]
    assert main(args) == 0
    assert "(1 file scanned)" in capsys.readouterr().out


def test_same_file_given_twice_is_linted_once(tmp_path):
    path = tmp_path / "a.py"
    path.write_text("recieved = 1\n", encoding="utf-8")
    assert len(lint_paths([path, path, tmp_path])) == 1


@POSIX_ONLY
def test_symlink_loop_does_not_hang(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text("recieved = 1\n", encoding="utf-8")
    os.symlink(tmp_path, tmp_path / "pkg" / "loop")
    started = time.monotonic()
    files = list(iter_python_files([tmp_path]))
    assert time.monotonic() - started < 5
    assert [path.name for path in files] == ["mod.py"]


def test_explicit_non_python_file_is_reported_as_skipped(tmp_path, capsys):
    notes = tmp_path / "notes.txt"
    notes.write_text("recieved = 1\n", encoding="utf-8")
    assert main(["lint", str(notes)]) == 0
    err = capsys.readouterr().err
    assert "skipped" in err and "not a .py file" in err
    assert "no Python files found" in err


# --- 4. one bad file must not hide the others ----------------------------------

def test_syntax_error_in_one_file_still_reports_other_files(tmp_path, capsys):
    (tmp_path / "a_bad.py").write_text("def broken(:\n", encoding="utf-8")
    (tmp_path / "b_typo.py").write_text("recieved = 1\n", encoding="utf-8")
    assert main(["lint", str(tmp_path)]) == 2
    captured = capsys.readouterr()
    assert "recieved" in captured.out
    assert "a_bad.py:1" in captured.err
    assert "1 file could not be analysed" in captured.out


def test_scan_paths_collects_errors_and_findings(tmp_path):
    (tmp_path / "bad.py").write_text("def broken(:\n", encoding="utf-8")
    (tmp_path / "good.py").write_text("recieved = 1\n", encoding="utf-8")
    result = scan_paths([tmp_path])
    assert len(result.files) == 2
    assert [d.word for d in result.diagnostics] == ["recieved"]
    assert [Path(e.path).name for e in result.errors] == ["bad.py"]
    assert result.errors[0].line == 1


@POSIX_ONLY
@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root can read anything")
def test_unreadable_file_is_reported(tmp_path, capsys):
    path = tmp_path / "locked.py"
    path.write_text("x = 1\n", encoding="utf-8")
    path.chmod(0)
    try:
        assert main(["lint", str(path)]) == 2
        assert "Permission denied" in capsys.readouterr().err
    finally:
        path.chmod(0o644)


def test_describe_error_variants():
    syntax = describe_error("a.py", SyntaxError("bad", ("a.py", 3, 7, "x")))
    assert syntax == FileError("a.py", "syntax error: bad", 3, 7)
    assert syntax.format_text() == "a.py:3:7: syntax error: bad"
    missing = describe_error("b.py", FileNotFoundError(2, "No such file or directory", "b.py"))
    assert missing.format_text() == "b.py: No such file or directory"
    assert describe_error("c.py", ValueError("odd")).message == "odd"
    no_line = describe_error("d.py", SyntaxError("bad"))
    assert no_line.location == "d.py"


# --- 5. API guards --------------------------------------------------------------

def test_spellchecker_is_loaded_once():
    assert _get_spellchecker() is _get_spellchecker()


def test_many_files_are_fast(tmp_path):
    for index in range(40):
        (tmp_path / f"m{index}.py").write_text("received_value = 1\n", encoding="utf-8")
    lint_source("warm_up = 1")
    started = time.monotonic()
    assert lint_paths([tmp_path]) == []
    assert time.monotonic() - started < 5  # 0.1.0 needed ~9 s (dictionary per file)


def test_negative_max_suggestions_means_none():
    [diagnostic] = lint_source("recieved_data = 1", max_suggestions=-1)
    assert diagnostic.suggestions == ()


def test_single_string_allow_word_is_one_word():
    assert lint_source("numpyy_value = 1", allow_words="numpyy") == []


def test_lint_file_accepts_a_display_filename(tmp_path):
    path = tmp_path / "x.py"
    path.write_text("recieved = 1\n", encoding="utf-8")
    assert lint_file(path, filename="shown.py")[0].path == "shown.py"


# --- 6. allowlist handling ---------------------------------------------------------

@pytest.mark.parametrize(
    ("make", "message"),
    [
        (lambda d: d / "missing.txt", "allowlist file not found"),
        (lambda d: d, "allowlist is not a regular file"),
    ],
    ids=["missing", "directory"],
)
def test_bad_allowlist_paths(tmp_path, capsys, make, message):
    sample = tmp_path / "s.py"
    sample.write_text("x = 1\n", encoding="utf-8")
    assert main(["lint", str(sample), "--allowlist", str(make(tmp_path))]) == 2
    assert message in capsys.readouterr().err


def test_binary_allowlist_is_rejected(tmp_path, capsys):
    sample = tmp_path / "s.py"
    sample.write_text("x = 1\n", encoding="utf-8")
    words = tmp_path / "words.bin"
    words.write_bytes(b"\xff\xfe\x00bad")
    assert main(["lint", str(sample), "--allowlist", str(words)]) == 2
    assert "must be UTF-8 text" in capsys.readouterr().err


def test_allowlist_supports_bom_inline_comments_and_several_words_per_line(tmp_path, capsys):
    sample = tmp_path / "s.py"
    sample.write_text("frobnicator_quuxify_zorble = 1\n", encoding="utf-8")
    words = tmp_path / "words.txt"
    words.write_bytes("\ufeff# vocabulary\nFrobnicator  # product name\nquuxify, zorble\n\n".encode("utf-8"))
    assert main(["lint", str(sample), "--allowlist", str(words)]) == 0
    capsys.readouterr()


# --- 7. process-level robustness -----------------------------------------------------

def test_keyboard_interrupt_exits_130(tmp_path, monkeypatch, capsys):
    sample = tmp_path / "s.py"
    sample.write_text("x = 1\n", encoding="utf-8")

    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "scan_paths", interrupted)
    assert main(["lint", str(sample)]) == 130
    assert "interrupted" in capsys.readouterr().err


def test_unexpected_error_is_reported_without_traceback(tmp_path, monkeypatch, capsys):
    sample = tmp_path / "s.py"
    sample.write_text("x = 1\n", encoding="utf-8")

    def broken(*args, **kwargs):
        raise LookupError("boom")

    monkeypatch.setattr(cli, "scan_paths", broken)
    monkeypatch.delenv("TYPO_GUARD_DEBUG", raising=False)
    assert main(["lint", str(sample)]) == 2
    assert "internal error: LookupError: boom" in capsys.readouterr().err
    monkeypatch.setenv("TYPO_GUARD_DEBUG", "1")
    with pytest.raises(LookupError):
        main(["lint", str(sample)])


@POSIX_ONLY
def test_broken_pipe_is_silent(tmp_path):
    path = tmp_path / "many.py"
    path.write_text("\n".join(f"recieved_{index} = 1" for index in range(3000)) + "\n", encoding="utf-8")
    src = str(Path(__file__).resolve().parents[1] / "src")
    command = f'"{sys.executable}" -m typo_guard lint "{path}" --format text | head -n 1'
    proc = subprocess.run(
        command, shell=True, capture_output=True, text=True,
        env=dict(os.environ, PYTHONPATH=src),
    )
    assert proc.stdout.startswith(str(path))
    assert "BrokenPipeError" not in proc.stderr
    assert "Traceback" not in proc.stderr


def test_non_utf8_stdout_does_not_crash(tmp_path):
    path = tmp_path / "unicode_names.py"
    path.write_text("数据_recieved = 1\n", encoding="utf-8")
    proc = run_module("lint", path, env={"PYTHONIOENCODING": "cp1252"})
    assert proc.returncode == 1
    assert b"Traceback" not in proc.stderr
    assert b"recieved" in proc.stdout


def test_python_dash_m_entry_point(tmp_path):
    path = tmp_path / "s.py"
    path.write_text("recieved = 1\n", encoding="utf-8")
    proc = run_module("lint", path, "--format", "json", text=True)
    assert proc.returncode == 1
    assert '"word": "recieved"' in proc.stdout
