"""Core linting logic for typo-guard.

The default detection engine (AST definition visitor, identifier splitter,
built-in allowlist and ``pyspellchecker`` lookup with frequency-ranked
suggestions) preserves the original typo-guard behaviour. Optional dictionary
views add common British-English variants and project vocabulary without
mutating the cached base dictionary. See ``CHANGELOG.md``.
"""

from __future__ import annotations

import ast
import builtins
import fnmatch
import io
import keyword
import os
import re
import tokenize
import warnings
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Iterable, Iterator, Optional, Sequence, Union
from .dictionary import configured_dictionary

if TYPE_CHECKING:  # a real class for type checkers, so "SpellChecker" is usable as one
    from spellchecker import SpellChecker
else:
    try:
        from spellchecker import SpellChecker  # type: ignore[assignment,misc]
    except ImportError:  # pragma: no cover - gives a clearer runtime error
        SpellChecker = None

PathLike = Union[str, "os.PathLike[str]"]

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

#: Directory/file names skipped while *recursing* into a directory.  Paths
#: passed explicitly on the command line are always scanned.
DEFAULT_EXCLUDES = frozenset({
    ".bzr", ".direnv", ".eggs", ".git", ".hg", ".ipynb_checkpoints",
    ".mypy_cache", ".nox", ".pytest_cache", ".ruff_cache", ".svn", ".tox",
    ".venv", "__pycache__", "__pypackages__", "_build", "*.egg-info",
    "buck-out", "build", "dist", "node_modules", "site-packages", "venv",
})

#: Control characters are invisible in a terminal and can be used to fake log
#: lines, so presentation code renders them as visible escapes instead.
_CONTROL_ESCAPES = {chr(code): f"\\x{code:02x}" for code in (*range(0x20), 0x7F)}
_CONTROL_ESCAPES.update({"\n": "\\n", "\r": "\\r", "\t": "\\t"})


def escape_control_chars(text: str) -> str:
    """Replace control characters (newline, ESC, ...) with visible escapes.

    File names are attacker-controlled input: a repository can contain a file
    called ``evil\\nforged.py`` or one with an embedded ANSI sequence, and the
    linter prints such names into terminals and CI logs.  Only presentation is
    affected; ``--format json`` and the Python API keep the real path.
    """
    return "".join(_CONTROL_ESCAPES.get(character, character) for character in text)


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

    @property
    def location(self) -> str:
        """``path:line:column`` - the format editors and terminals hyperlink."""
        return f"{self.path}:{self.line}:{self.column}"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def format_text(self) -> str:
        hint = f" (suggestions: {', '.join(self.suggestions)})" if self.suggestions else ""
        return (
            f"{escape_control_chars(self.path)}:{self.line}:{self.column}: TG001 possible typo "
            f"'{self.word}' in {self.kind} '{self.identifier}'{hint}"
        )


class _DefinitionVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.identifiers: list[Identifier] = []

    def _add(self, name: str, node: ast.AST, kind: str) -> None:
        if name and not name.startswith("__"):
            self.identifiers.append(
                Identifier(node.lineno, node.col_offset + 1, name, kind)  # type: ignore[attr-defined]
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


def _too_complex(filename: str, error: BaseException) -> SyntaxError:
    detail = str(error) or type(error).__name__
    return SyntaxError(
        f"source too complex to analyse ({detail})", (filename, 1, 1, None)
    )


def _decode_text(source: bytes) -> str:
    """Decode bytes the way :func:`ast.parse` does (BOM and PEP 263 aware)."""
    try:
        encoding, _ = tokenize.detect_encoding(io.BytesIO(source).readline)
        return source.decode(encoding)
    except (SyntaxError, UnicodeDecodeError, LookupError):  # pragma: no cover - defensive
        return source.decode("utf-8", "replace")


def _character_lines(source: str | bytes) -> list[str]:
    """Split source into lines exactly as ``ast`` counts them."""
    text = source if isinstance(source, str) else _decode_text(source)
    return re.split(r"\r\n|\r|\n", text)


def _char_column(line_text: str, byte_column: int) -> int:
    """Convert an ``ast`` UTF-8 byte offset into a 1-based character column."""
    prefix = line_text.encode("utf-8", "surrogatepass")[:byte_column]
    return len(prefix.decode("utf-8", "replace")) + 1


def extract_identifiers(source: str | bytes, filename: str = "<unknown>") -> list[Identifier]:
    """Parse source and return definitions, never strings/comments or attribute uses.

    Every "this is not analysable Python" condition is raised as
    :class:`SyntaxError`, on every supported Python version.
    """
    if isinstance(source, str) and source.startswith("\ufeff"):
        source = source[1:]  # a UTF-8 BOM is not part of the program text
    try:
        with warnings.catch_warnings():
            # e.g. "invalid escape sequence" belongs to the scanned file, not to us.
            warnings.simplefilter("ignore")
            tree = ast.parse(source, filename=filename)
        visitor = _DefinitionVisitor()
        visitor.visit(tree)
    except SyntaxError:
        raise
    except ValueError as error:  # Python < 3.12 reports NUL bytes as ValueError
        raise SyntaxError(str(error), (filename, 1, 1, None)) from error
    except (RecursionError, MemoryError) as error:  # pathologically deep nesting
        raise _too_complex(filename, error) from error
    # ast reports col_offset in UTF-8 *bytes*; publishers expect characters, so
    # that "file:line:col" stays clickable on a non-ASCII line.
    lines = _character_lines(source)

    def _column(item: Identifier) -> int:
        index = item.line - 1
        line_text = lines[index] if 0 <= index < len(lines) else ""
        return _char_column(line_text, item.column - 1)

    return sorted(
        {
            Identifier(item.line, _column(item), item.name, item.kind)
            for item in visitor.identifiers
        }
    )


def split_identifier(name: str) -> list[str]:
    """Split snake_case, camelCase, PascalCase and acronym boundaries into words."""
    normalized = _CAMEL_BOUNDARY_2.sub(r"\1_\2", name)
    normalized = _CAMEL_BOUNDARY_1.sub(r"\1_\2", normalized)
    return [part.lower() for part in _NON_LETTERS.split(normalized) if part]


def _is_excluded(name: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns)


def iter_python_files(
    paths: Sequence[PathLike],
    *,
    exclude: Optional[Iterable[str]] = None,
    on_error: Optional[Callable[[OSError], None]] = None,
) -> Iterator[Path]:
    """Yield ``.py`` files from files/directories, each real file only once.

    Directories are walked without following symlinks (no infinite loops) and
    names matching ``exclude`` (default: :data:`DEFAULT_EXCLUDES`) are pruned.
    Directory-walk errors (e.g. permission denied) are passed to ``on_error``.
    """
    patterns = tuple(DEFAULT_EXCLUDES if exclude is None else exclude)
    seen: set[str] = set()

    def _unique(candidate: Path) -> bool:
        try:
            key = os.path.realpath(candidate)
        except (OSError, ValueError):  # pragma: no cover - exotic paths
            key = str(candidate)
        if key in seen:
            return False
        seen.add(key)
        return True

    for raw_path in paths:
        path = Path(raw_path)
        if path.is_dir():
            for root, dirs, files in os.walk(path, onerror=on_error):
                dirs[:] = sorted(d for d in dirs if not _is_excluded(d, patterns))
                for file_name in sorted(files):
                    candidate = Path(root, file_name)
                    if (
                        candidate.suffix == ".py"
                        and not _is_excluded(file_name, patterns)
                        # a symlinked file would read outside the scanned tree
                        and not candidate.is_symlink()
                        and candidate.is_file()
                        and _unique(candidate)
                    ):
                        yield candidate
        elif path.suffix == ".py" and path.is_file() and _unique(path):
            yield path


def _iter_python_files(paths: Sequence[PathLike]) -> Iterator[Path]:
    """Backward-compatible alias of :func:`iter_python_files` (0.1.x name)."""
    return iter_python_files(paths)


@lru_cache(maxsize=1)
def _get_spellchecker() -> "SpellChecker":
    """Load the English dictionary once per process (it is the slow part)."""
    if SpellChecker is None:
        raise RuntimeError("pyspellchecker is required; install typo-guard normally")
    return SpellChecker(distance=1)


def _as_word_tuple(words: Iterable[str]) -> tuple[str, ...]:
    """Normalise a word iterable once, before any file is scanned."""
    if isinstance(words, str):  # a single word, not an iterable of letters
        return (words,)
    return tuple(words)


def lint_source(
    source: str | bytes,
    *,
    filename: str = "<unknown>",
    allow_words: Iterable[str] = (),
    max_suggestions: int = 3,
    language: str = "en-US",
    dictionary_words: Iterable[str] = (),
) -> list[Diagnostic]:
    """Lint Python source and return suspected identifier spelling mistakes."""
    spell = configured_dictionary(
        _get_spellchecker(), language=language, additional_words=dictionary_words
    )
    allowed = DEFAULT_ALLOWLIST | {
        word.strip().lower() for word in _as_word_tuple(allow_words) if word.strip()
    }
    limit = max(0, int(max_suggestions))
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
                        suggestions=tuple(candidates[:limit]),
                    )
                )
    # One finding per (file, position, identifier, word): a name such as
    # "Reponse_reponse" splits into the same word twice at the same place.
    unique: dict[tuple[str, int, int, str, str], Diagnostic] = {}
    for item in diagnostics:
        unique.setdefault(
            (item.path, item.line, item.column, item.identifier, item.word), item
        )
    return list(unique.values())


def read_source(path: PathLike) -> str:
    """Read a Python file the way the interpreter does.

    Honours a UTF-8 BOM and PEP 263 ``# -*- coding: ... -*-`` declarations and
    falls back to UTF-8.  Raises :class:`OSError`, :class:`UnicodeDecodeError`
    or :class:`SyntaxError` (unknown/invalid encoding declaration).
    """
    with tokenize.open(os.fspath(path)) as handle:
        return handle.read()


def lint_file(path: PathLike, **kwargs: object) -> list[Diagnostic]:
    """Read and lint one Python file (UTF-8 unless the file declares otherwise)."""
    source_path = Path(path)
    source = read_source(source_path)
    filename = str(kwargs.pop("filename", source_path))
    return lint_source(source, filename=filename, **kwargs)  # type: ignore[arg-type]


def lint_paths(
    paths: Sequence[PathLike],
    *,
    exclude: Optional[Iterable[str]] = None,
    **kwargs: object,
) -> list[Diagnostic]:
    """Lint files or recursively lint directories in deterministic order.

    This strict API raises on the first unreadable/invalid file.  Use
    :func:`typo_guard.runner.scan_paths` to collect per-file errors instead.
    """
    # Normalise both word lists once: a one-shot iterable (generator) would
    # otherwise be consumed by the first file and silently allow nothing later.
    for name in ("allow_words", "dictionary_words"):
        if name in kwargs:
            kwargs[name] = _as_word_tuple(kwargs[name])  # type: ignore[arg-type]
    diagnostics: list[Diagnostic] = []
    files = iter_python_files(paths, exclude=exclude)
    for path in sorted(files, key=lambda item: str(item)):
        diagnostics.extend(lint_file(path, **kwargs))
    return diagnostics
