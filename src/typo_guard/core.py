"""Core linting logic for typo-guard."""
from __future__ import annotations

import ast
import builtins
import keyword
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Iterator, Sequence

try:
    from spellchecker import SpellChecker
except ImportError:  # pragma: no cover - gives a clearer runtime error
    SpellChecker = None  # type: ignore[assignment]

_CAMEL_BOUNDARY_1 = re.compile(r"([a-z0-9])([A-Z])")
_CAMEL_BOUNDARY_2 = re.compile(r"([A-Z]+)([A-Z][a-z])")
_NON_LETTERS = re.compile(r"[^A-Za-z]+")

DEFAULT_ALLOWLIST = frozenset({
    "api", "args", "argv", "async", "auth", "bool", "cli", "cls", "config",
    "csv", "ctx", "cwd", "db", "dict", "docstring", "dtype", "env", "func",
    "github", "html", "http", "https", "id", "idx", "init", "int", "io",
    "ip", "json", "kwargs", "len", "linter", "metadata", "numpy", "oauth",
    "os", "param", "params", "pdf", "py", "pytest", "regex", "repo", "repr",
    "sdk", "sql", "stderr", "stdin", "stdout", "str", "sys", "tmp", "tuple",
    "txt", "uri", "url", "utf", "uuid", "var", "whitelist", "xml", "yaml",
}) | frozenset(keyword.kwlist) | frozenset(dir(builtins))


@dataclass(frozen=True, order=True)
class Identifier:
    """A Python identifier definition found in source code."""

    line: int
    column: int
    name: str
    kind: str


@dataclass(frozen=True)
class Diagnostic:
    """A suspected misspelling associated with an identifier."""

    path: str
    line: int
    column: int
    kind: str
    identifier: str
    word: str
    suggestions: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def format_text(self) -> str:
        hint = f" (suggestions: {', '.join(self.suggestions)})" if self.suggestions else ""
        return (
            f"{self.path}:{self.line}:{self.column}: TG001 possible typo "
            f"'{self.word}' in {self.kind} '{self.identifier}'{hint}"
        )


class _DefinitionVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.identifiers: list[Identifier] = []

    def _add(self, name: str, node: ast.AST, kind: str) -> None:
        if name and not name.startswith("__"):
            self.identifiers.append(
                Identifier(node.lineno, node.col_offset + 1, name, kind)
            )

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._add(node.name, node, "function")
        self._add_arguments(node.args)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._add(node.name, node, "function")
        self._add_arguments(node.args)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._add(node.name, node, "class")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self._add(node.id, node, "variable")

    def visit_arg(self, node: ast.arg) -> None:
        # Arguments are collected by their parent function to avoid duplicates.
        return

    def _add_arguments(self, args: ast.arguments) -> None:
        all_args = [*args.posonlyargs, *args.args, *args.kwonlyargs]
        if args.vararg:
            all_args.append(args.vararg)
        if args.kwarg:
            all_args.append(args.kwarg)
        for argument in all_args:
            self._add(argument.arg, argument, "argument")


def extract_identifiers(source: str, filename: str = "<unknown>") -> list[Identifier]:
    """Parse source and return definitions, never strings/comments or attribute uses."""
    tree = ast.parse(source, filename=filename)
    visitor = _DefinitionVisitor()
    visitor.visit(tree)
    return sorted(set(visitor.identifiers))


def split_identifier(name: str) -> list[str]:
    """Split snake_case, camelCase, PascalCase and acronym boundaries into words."""
    normalized = _CAMEL_BOUNDARY_2.sub(r"\1_\2", name)
    normalized = _CAMEL_BOUNDARY_1.sub(r"\1_\2", normalized)
    return [part.lower() for part in _NON_LETTERS.split(normalized) if part]


def _iter_python_files(paths: Sequence[str | Path]) -> Iterator[Path]:
    seen: set[Path] = set()
    for raw_path in paths:
        path = Path(raw_path)
        candidates = path.rglob("*.py") if path.is_dir() else (path,)
        for candidate in candidates:
            resolved = candidate.resolve()
            if candidate.suffix == ".py" and resolved not in seen:
                seen.add(resolved)
                yield candidate


def lint_source(
    source: str,
    *,
    filename: str = "<unknown>",
    allow_words: Iterable[str] = (),
    max_suggestions: int = 3,
) -> list[Diagnostic]:
    """Lint Python source and return suspected identifier spelling mistakes."""
    if SpellChecker is None:
        raise RuntimeError("pyspellchecker is required; install typo-guard normally")

    spell = SpellChecker(distance=1)
    allowed = DEFAULT_ALLOWLIST | {word.strip().lower() for word in allow_words if word.strip()}
    diagnostics: list[Diagnostic] = []

    for identifier in extract_identifiers(source, filename):
        for word in split_identifier(identifier.name):
            if len(word) < 3 or word in allowed or word.isdigit():
                continue
            if word not in spell:
                candidates = sorted(
                    spell.candidates(word) or (),
                    key=lambda item: (-spell.word_usage_frequency(item), item),
                )
                diagnostics.append(
                    Diagnostic(
                        path=filename,
                        line=identifier.line,
                        column=identifier.column,
                        kind=identifier.kind,
                        identifier=identifier.name,
                        word=word,
                        suggestions=tuple(candidates[:max_suggestions]),
                    )
                )
    return diagnostics


def lint_file(path: str | Path, **kwargs: object) -> list[Diagnostic]:
    """Read and lint one UTF-8 Python file."""
    source_path = Path(path)
    source = source_path.read_text(encoding="utf-8")
    return lint_source(source, filename=str(source_path), **kwargs)


def lint_paths(paths: Sequence[str | Path], **kwargs: object) -> list[Diagnostic]:
    """Lint files or recursively lint directories in deterministic order."""
    diagnostics: list[Diagnostic] = []
    for path in sorted(_iter_python_files(paths), key=lambda item: str(item)):
        diagnostics.extend(lint_file(path, **kwargs))
    return diagnostics
