"""Packaging metadata stays consistent with the code."""

import importlib
import re
import sys
from pathlib import Path

import typo_guard

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = (ROOT / "pyproject.toml").read_text(encoding="utf-8")


def test_version_is_single_sourced_from_the_package():
    assert 'dynamic = ["version"]' in PYPROJECT
    assert 'path = "src/typo_guard/__init__.py"' in PYPROJECT
    assert re.fullmatch(r"\d+\.\d+\.\d+", typo_guard.__version__)


def test_changelog_mentions_current_version():
    assert f"## [{typo_guard.__version__}]" in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")


def test_console_script_and_dependencies_are_declared():
    assert 'typo-guard = "typo_guard.cli:main"' in PYPROJECT
    assert "pyspellchecker" in PYPROJECT
    assert "rich" in PYPROJECT


def test_public_api_is_importable():
    for name in typo_guard.__all__:
        assert hasattr(typo_guard, name), name


def test_importing_dunder_main_does_not_run_the_cli():
    sys.modules.pop("typo_guard.__main__", None)
    module = importlib.import_module("typo_guard.__main__")
    assert callable(module.main)


def test_typed_marker_and_pre_commit_hook_exist():
    assert (ROOT / "src" / "typo_guard" / "py.typed").exists()
    hook = (ROOT / ".pre-commit-hooks.yaml").read_text(encoding="utf-8")
    assert "id: typo-guard" in hook and "entry: typo-guard lint" in hook


def test_own_source_code_has_no_typos(capsys):
    """Dogfooding: the project's own vocabulary file keeps src/ and tests/ clean."""
    from typo_guard.cli import main

    vocabulary = ROOT / ".typo-guard-words"
    assert vocabulary.is_file(), ".typo-guard-words must ship with the sources"
    args = ["lint", str(ROOT / "src"), str(ROOT / "tests"), "--allowlist", str(vocabulary), "--format", "text"]
    assert main(args) == 0, capsys.readouterr().out
