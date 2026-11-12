"""Proof that 0.2.0 preserves the original 0.1.0 detection engine.

``tests/fixtures/original_core_0_1_0.py`` is a verbatim copy of the 0.1.0
``core.py``.  These tests check that (1) the parsing/splitting/allowlist code
is structurally identical and (2) both engines return identical diagnostics
for a corpus of ordinary Python sources.
"""

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

from typo_guard import core

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL_PATH = ROOT / "tests" / "fixtures" / "original_core_0_1_0.py"

ENGINE_PARTS = (
    "_CAMEL_BOUNDARY_1",
    "_CAMEL_BOUNDARY_2",
    "_NON_LETTERS",
    "DEFAULT_ALLOWLIST",
    "Identifier",
    "_DefinitionVisitor",
    "split_identifier",
)


def _load_original():
    spec = importlib.util.spec_from_file_location("typo_guard_original_core", ORIGINAL_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve string annotations via sys.modules
    spec.loader.exec_module(module)
    return module


ORIGINAL = _load_original()


def _top_level(path):
    found = {}
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            found[node.name] = ast.dump(node)
        elif isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            found[node.targets[0].id] = ast.dump(node.value)
    return found


@pytest.mark.parametrize("name", ENGINE_PARTS)
def test_engine_component_is_structurally_identical(name):
    original = _top_level(ORIGINAL_PATH)
    current = _top_level(ROOT / "src" / "typo_guard" / "core.py")
    assert current[name] == original[name], f"{name} differs from the 0.1.0 engine"


def test_word_check_rules_are_unchanged():
    """The per-word rules inside lint_source (length, allowlist, digits, lookup, ranking)."""
    def rule_lines(path):
        source = path.read_text(encoding="utf-8")
        start = source.index("for word in split_identifier(identifier.name):")
        end = source.index("diagnostics.append(", start)
        return [line.strip() for line in source[start:end].splitlines() if line.strip()]

    assert rule_lines(ROOT / "src" / "typo_guard" / "core.py") == rule_lines(ORIGINAL_PATH)


def test_default_settings_are_unchanged():
    assert core.DEFAULT_ALLOWLIST == ORIGINAL.DEFAULT_ALLOWLIST
    assert core._get_spellchecker()._distance == 1  # SpellChecker(distance=1), as in 0.1.0


CORPUS = sorted(
    [*(ROOT / "examples").glob("*.py"), *(ROOT / "src" / "typo_guard").glob("*.py"), *(ROOT / "tests").glob("test_*.py")]
)

SYNTHETIC = '''
import os as operating_system
from typing import List

GLOBAL_LIMIT = 10
first_valeu, (second_valeu, *rest_valeus) = 1, (2, 3)

class HTTPResponseParsr(object):
    """Docstrings are ignored: recieved, innitial."""
    statuss_code = 200

    def __init__(self, raw_byts: bytes, *extra_argz, verbos=False, **kw_optionz):
        self.recieved = raw_byts            # attribute: ignored
        for indx, chunk_dataa in enumerate(extra_argz):
            totl = indx
        with open(os.devnull) as handel:
            pass
        squares_lisst = [numbr * numbr for numbr in range(3)]
        if (matchd := len(squares_lisst)) > 1:
            del matchd

    async def fetch_remot(self, *, timout=5):
        return "innitial string"

def parseJSONPayloadd(payload_textt):
    return payload_textt
'''


@pytest.mark.parametrize("path", CORPUS, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_same_diagnostics_as_original_engine_on_corpus(path):
    source = path.read_text(encoding="utf-8")
    expected = [d.to_dict() for d in ORIGINAL.lint_source(source, filename=path.name)]
    actual = [d.to_dict() for d in core.lint_source(source, filename=path.name)]
    assert actual == expected


@pytest.mark.parametrize("allow", [(), ("parsr", "verbos")])
@pytest.mark.parametrize("limit", [0, 1, 3, 5])
def test_same_diagnostics_as_original_engine_on_synthetic_source(allow, limit):
    expected = [d.to_dict() for d in ORIGINAL.lint_source(SYNTHETIC, allow_words=allow, max_suggestions=limit)]
    actual = [d.to_dict() for d in core.lint_source(SYNTHETIC, allow_words=allow, max_suggestions=limit)]
    assert actual == expected
    assert len(actual) >= 15  # the synthetic source really exercises the engine


def test_same_text_format_as_original():
    item = core.Diagnostic("a.py", 1, 2, "variable", "recieved_x", "recieved", ("received",))
    legacy = ORIGINAL.Diagnostic("a.py", 1, 2, "variable", "recieved_x", "recieved", ("received",))
    assert item.format_text() == legacy.format_text()
    assert item.to_dict() == legacy.to_dict()
