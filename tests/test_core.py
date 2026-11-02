import ast

import pytest

from typo_guard.core import extract_identifiers, lint_paths, lint_source, split_identifier


def test_split_identifier_supports_common_python_styles():
    assert split_identifier("received_data") == ["received", "data"]
    assert split_identifier("initialValue") == ["initial", "value"]
    assert split_identifier("HTTPResponseCode") == ["http", "response", "code"]


def test_extracts_definitions_and_ignores_strings_comments_and_attribute_names():
    source = '''
# recieved_comment should not be inspected
message = "innitial_string"

def calculate_total(recieved_amount):
    local_value = object.innitial_attribute
    return recieved_amount
'''
    found = {(item.name, item.kind) for item in extract_identifiers(source)}
    assert ("calculate_total", "function") in found
    assert ("recieved_amount", "argument") in found
    assert ("local_value", "variable") in found
    assert all("comment" not in name and "string" not in name for name, _ in found)
    assert all(name != "innitial_attribute" for name, _ in found)


def test_lint_source_reports_misspelled_snake_and_camel_identifiers():
    source = "recieved_data = 1\ndef setInnitialValue():\n    pass\n"
    diagnostics = lint_source(source, filename="sample.py")
    words = {item.word for item in diagnostics}
    assert {"recieved", "innitial"} <= words
    assert all(item.path == "sample.py" for item in diagnostics)


def test_valid_identifiers_are_not_reported():
    source = "received_data = 1\ndef calculate_total(initial_value):\n    return initial_value\n"
    assert lint_source(source) == []


def test_custom_allowlist_suppresses_domain_terms():
    source = "frobnicator_value = 1\n"
    assert any(item.word == "frobnicator" for item in lint_source(source))
    assert lint_source(source, allow_words={"frobnicator"}) == []


def test_lint_paths_recurses_and_ignores_non_python_files(tmp_path):
    (tmp_path / "good.py").write_text("received_data = 1\n", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "bad.py").write_text("recieved_data = 1\n", encoding="utf-8")
    (nested / "notes.txt").write_text("innitial_value = 1\n", encoding="utf-8")
    results = lint_paths([tmp_path])
    assert len(results) == 1
    assert results[0].word == "recieved"


def test_syntax_error_is_preserved_for_callers():
    with pytest.raises(SyntaxError):
        lint_source("def broken(:\n")
