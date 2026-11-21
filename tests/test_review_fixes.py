"""Regression tests for the independent code review of 0.2.3 (shipped in 0.2.4).

Every test reproduces one reported defect so that it cannot come back.  The
review items that were deliberately left open (L-2, L-3, L-6, L-7) are listed
in CHANGELOG.md and are not pinned here.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from typo_guard.cli import _silence_stdout, main
from typo_guard.core import escape_control_chars, lint_paths, lint_source

POSIX_ONLY = pytest.mark.skipif(os.name == "nt", reason="POSIX-only file-system behaviour")

ROOT = Path(__file__).resolve().parents[1]
SRC = str(ROOT / "src")


# --- H-1: allow_words iterables must survive the first file -------------------


def test_allow_words_generator_is_used_for_every_file(tmp_path):
    first = tmp_path / "a.py"
    second = tmp_path / "b.py"
    first.write_text("zzquux = 1\n", encoding="utf-8")
    second.write_text("zzquux = 1\n", encoding="utf-8")
    allowed = (word for word in ["zzquux"])

    assert lint_paths([first, second], allow_words=allowed) == []


def test_dictionary_words_generator_is_used_for_every_file(tmp_path):
    first = tmp_path / "a.py"
    second = tmp_path / "b.py"
    first.write_text("zzquux = 1\n", encoding="utf-8")
    second.write_text("zzquux = 1\n", encoding="utf-8")
    added = (word for word in ["zzquux"])

    assert lint_paths([first, second], dictionary_words=added) == []


# --- H-2: file names must not inject control characters ----------------------
#
# Windows rejects both 0x0A and 0x1B in a file name (OSError: [Errno 22]), so these
# three cases can only be created, and therefore only be tested, on POSIX.


@POSIX_ONLY
def test_line_break_in_a_file_name_is_escaped_in_text_output(tmp_path, capsys):
    path = tmp_path / "evil\nnewline.py"
    path.write_text("recieved_data = 1\n", encoding="utf-8")

    assert main(["lint", str(path), "--format", "text"]) == 1

    out = capsys.readouterr().out
    assert out.startswith(f"{escape_control_chars(str(path))}:1:1:")
    assert "\\n" in out
    assert out.count("\n") == 2  # one finding line plus the summary line


@POSIX_ONLY
def test_escape_sequence_in_a_file_name_never_reaches_the_terminal(tmp_path, capsys):
    path = tmp_path / "esc\x1b[31mred\x1b[0m.py"
    path.write_text("recieved_data = 1\n", encoding="utf-8")

    assert main(["lint", str(path)]) == 1

    out = capsys.readouterr().out
    assert "\x1b" not in out
    assert "\\x1b" in out


@POSIX_ONLY
def test_json_output_still_carries_the_real_path(tmp_path, capsys):
    path = tmp_path / "esc\x1b[31mred.py"
    path.write_text("recieved_data = 1\n", encoding="utf-8")

    assert main(["lint", str(path), "--format", "json"]) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["path"] == str(path)


# --- M-1: columns are characters, not UTF-8 bytes ----------------------------


def test_non_ascii_text_does_not_shift_the_reported_column():
    accented = lint_source("\u00e9 = 1; recieved_data = 2\n")
    assert [(item.line, item.column) for item in accented] == [(1, 8)]

    astral = lint_source("s = '\U0001f600'; recieved = 1\n")
    assert [(item.line, item.column) for item in astral] == [(1, 10)]


def test_byte_source_reports_the_same_character_column():
    assert [
        (item.line, item.column)
        for item in lint_source(b"\xc3\xa9 = 1; recieved_data = 2\n")
    ] == [(1, 8)]


def test_ascii_columns_are_unchanged():
    assert [(item.line, item.column) for item in lint_source("recieved_data = 2\n")] == [(1, 1)]


# --- M-2: a symlinked file must not pull in code from outside the tree ------


@POSIX_ONLY
def test_link_to_a_file_outside_the_tree_is_not_scanned(tmp_path):
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "inside.py").write_text("good_name = 1\n", encoding="utf-8")
    outside = tmp_path / "outside.py"
    outside.write_text("recieved_data = 1\n", encoding="utf-8")
    os.symlink(outside, tree / "linked.py")

    assert lint_paths([tree]) == []


@POSIX_ONLY
def test_a_symlink_named_on_the_command_line_is_still_scanned(tmp_path):
    outside = tmp_path / "outside.py"
    outside.write_text("recieved_data = 1\n", encoding="utf-8")
    link = tmp_path / "linked.py"
    os.symlink(outside, link)

    assert [item.word for item in lint_paths([link])] == ["recieved"]


# --- M-3: a closed pipe is not the same as "typos found" --------------------


@POSIX_ONLY
def test_closed_output_pipe_exits_with_141(tmp_path):
    path = tmp_path / "clean.py"
    path.write_text("good_name = 1\n", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-m", "typo_guard", "lint", "--format", "text", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=dict(os.environ, PYTHONPATH=SRC),
    )
    proc.stdout.close()

    assert proc.wait() == 141


# --- M-4: one finding per identifier and word -------------------------------


def test_repeated_word_in_one_identifier_is_reported_once():
    findings = lint_source("Reponse_reponse = 1\n")

    assert [(item.identifier, item.word) for item in findings] == [("Reponse_reponse", "reponse")]


# --- L-4: invalid bytes are not blamed on a missing declaration -------------


def test_invalid_utf8_names_the_bytes_not_a_missing_declaration(tmp_path, capsys):
    path = tmp_path / "bad.py"
    path.write_bytes(b"name_value = '\x93quoted\x94'\n")

    assert main(["lint", str(path)]) == 2

    err = capsys.readouterr().err
    assert "cannot decode file" in err
    assert "save it as UTF-8" in err
    assert "not valid UTF-8" in err
    assert "missing encoding declaration" not in err


# --- L-5: silencing a broken pipe must not leak a descriptor ----------------


def test_silencing_a_broken_pipe_closes_the_devnull_descriptor(monkeypatch):
    opened = []
    real_open = os.open

    def tracking_open(*args, **kwargs):
        descriptor = real_open(*args, **kwargs)
        opened.append(descriptor)
        return descriptor

    stand_in = os.open(os.devnull, os.O_WRONLY)

    class Stream:
        def fileno(self):
            return stand_in

    monkeypatch.setattr(sys, "stdout", Stream())
    monkeypatch.setattr(os, "open", tracking_open)
    try:
        _silence_stdout()
        assert opened, "_silence_stdout did not open /dev/null"
        with pytest.raises(OSError):
            os.fstat(opened[-1])  # already closed, so the descriptor is free
    finally:
        os.close(stand_in)
