"""Acceptance tests: the demo files and the ten documented acceptance cases.

These are the scenarios described in README.md / docs/MANUAL.md, so the
documentation and the behaviour cannot drift apart.
"""

import json
from pathlib import Path

import pytest

from typo_guard import lint_paths, lint_source
from typo_guard.cli import main
from typo_guard.report import source_fragment

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def test_demo_file_produces_the_documented_table_rows():
    rows = [
        (d.line, d.column, d.kind, d.identifier, source_fragment(d), d.suggestions)
        for d in lint_paths([EXAMPLES / "example.py"])
    ]
    assert rows == [
        (3, 1, "variable", "recieved_data", "recieved", ("received", "relieved")),
        (6, 1, "function", "calculate_avrage", "avrage", ("average",)),
        (6, 22, "argument", "innitial_value", "innitial", ("initial",)),
        (11, 1, "class", "ReponseFormatter", "Reponse", ("response", "repose")),
    ]


def test_clean_demo_file_has_no_findings():
    assert lint_paths([EXAMPLES / "clean_example.py"]) == []


def test_demo_allowlist_suppresses_the_listed_word(capsys):
    args = [
        "lint",
        str(EXAMPLES / "example.py"),
        str(EXAMPLES / "clean_example.py"),
        "--allowlist",
        str(EXAMPLES / ".typo-guard-words"),
        "--format",
        "json",
    ]
    assert main(args) == 1
    words = {item["word"] for item in json.loads(capsys.readouterr().out)}
    assert words == {"recieved", "avrage", "innitial"}


# The ten manual acceptance cases from the 0.1.x README, now automated.

@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("recieved_data = 1\n", {"recieved"}),                                  # 1 snake_case variable
        ("def setInnitialValue():\n    pass\n", {"innitial"}),                  # 2 camelCase function
        ("received_data = 1\n", set()),                                         # 3 correct spelling
        ('message = "innitial value"\n', set()),                                # 4 strings ignored
        ("# recieved data\n", set()),                                           # 5 comments ignored
        ("client.recieved_data\n", set()),                                      # 6a attribute use ignored
        ("client.recieved_data = 1\n", set()),                                  # 6b attribute store ignored
        ("recieved_data = client.value\n", {"recieved"}),                       # 6c real definition flagged
    ],
    ids=["1-variable", "2-camel-function", "3-correct", "4-string", "5-comment",
         "6a-attribute-load", "6b-attribute-store", "6c-definition"],
)
def test_acceptance_cases_1_to_6(source, expected):
    assert {d.word for d in lint_source(source)} == expected


def test_acceptance_case_7_custom_vocabulary():
    source = "frobnicator_value = 1\n"
    assert {d.word for d in lint_source(source)} == {"frobnicator"}
    assert lint_source(source, allow_words={"frobnicator"}) == []


def test_acceptance_case_8_recursive_scan_ignores_non_python(tmp_path):
    (tmp_path / "pkg" / "sub").mkdir(parents=True)
    (tmp_path / "pkg" / "sub" / "deep.py").write_text("recieved = 1\n", encoding="utf-8")
    (tmp_path / "pkg" / "notes.txt").write_text("innitial = 1\n", encoding="utf-8")
    assert [d.word for d in lint_paths([tmp_path])] == ["recieved"]


def test_acceptance_case_9_json_and_exit_code(tmp_path, capsys):
    sample = tmp_path / "s.py"
    sample.write_text("recieved = 1\n", encoding="utf-8")
    assert main(["lint", str(sample), "--format", "json"]) == 1
    assert json.loads(capsys.readouterr().out)[0]["word"] == "recieved"


def test_acceptance_case_10_invalid_python_exits_2(tmp_path, capsys):
    sample = tmp_path / "broken.py"
    sample.write_text("def broken(:\n", encoding="utf-8")
    assert main(["lint", str(sample)]) == 2
    assert "syntax error" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("source", "kind"),
    [
        ("recieved = 1\n", "variable"),
        ("for recieved in []: pass\n", "variable"),
        ("with open('f') as recieved: pass\n", "variable"),
        ("[recieved for recieved in []]\n", "variable"),
        ("(recieved := 1)\n", "variable"),
        ("def recieved(): pass\n", "function"),
        ("async def recieved(): pass\n", "function"),
        ("def f(recieved): pass\n", "argument"),
        ("def f(*recieved, **recieved_more): pass\n", "argument"),
        ("class Recieved: pass\n", "class"),
    ],
)
def test_supported_definition_kinds(source, kind):
    kinds = {d.kind for d in lint_source(source)}
    assert kinds == {kind}
