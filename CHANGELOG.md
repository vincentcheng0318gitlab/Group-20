# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.4] - 2026-11-21

This release fixes every defect that the independent review of the published
0.2.3 artifact reported, except the four that are listed under *Known
limitations* below. 0.2.3 itself was built from uncommitted local edits and its
console script could not be imported (`_version__` instead of `__version__`), so
0.2.4 supersedes it and is the first release that can be reproduced from this
repository.

The detection engine (`_DefinitionVisitor`, `split_identifier`,
`DEFAULT_ALLOWLIST`) is still the untouched 0.1.0 engine; see *Known
limitations*.

### Added
- `--language en-GB` and the Python API's `language="en-GB"` option accept common British-English spelling variants while keeping American English as the default.
- `--dictionary FILE` and the Python API's `dictionary_words` parameter add reusable, UTF-8 supplemental vocabulary without mutating the cached base dictionary.
- Fourteen regression tests, one per review defect, in `tests/test_review_fixes.py`.

### Fixed
- `lint_paths()` dropped a one-shot `allow_words` iterable after the first file, so a generator-built allowlist silently stopped allowing anything from file two onwards. Both word parameters are now normalised once, in one shared helper, and `runner.scan_paths()` reuses it.
- A file name containing `\n` or an ANSI escape sequence (`0x1b`) was printed verbatim by `--format text`, `--format table` and the error lines, splitting records and allowing terminal or CI-log injection. Control characters are now rendered as visible escapes (`\n`, `\x1b`); `--format json` and the Python API keep the real path.
- Reported columns were UTF-8 *byte* offsets published as character columns, so any non-ASCII character earlier on the line moved the position further away. Columns are now character based, for `str` and `bytes` input alike.
- Recursive scans followed `.py` symlinks and linted files outside the requested tree, contradicting the documented "symbolic links are not followed". Links found while walking a directory are skipped; a path named explicitly on the command line is still scanned.
- A closed output pipe (`typo-guard lint . | head`) returned `1`, which is indistinguishable from "typos found". It now returns `141` (128 + SIGPIPE), meaning the run was cut short and reached no verdict.
- An identifier such as `Reponse_reponse` produced the same finding twice and a self-contradictory summary ("2 possible typos in 1 identifier"). Findings are now deduplicated per file, position, identifier and word.
- pyright reported `reportInvalidTypeForm` for `SpellChecker` used as a type expression in `core.py`, which `py.typed` shipped to every downstream user. The name is now imported for type checking only.
- A file containing invalid UTF-8 was reported as "invalid or missing encoding declaration", although the file had nothing wrong with its declaration. The message now says the bytes are not valid UTF-8.
- `_silence_stdout()` leaked the file descriptor it opened on `/dev/null`.
- The compare links at the end of this changelog still pointed at the `your-org` placeholder.

### Changed
- The exit-code table in `README.md` and `docs/MANUAL.md` documents the new `141` code.

### Known limitations

Deliberately left open: the project pins the detection engine to a verbatim copy
of 0.1.0 (`tests/test_engine_preserved.py`), so these behave exactly as they did
in 0.1.0 and are documented rather than changed.

- Function and class findings point at the `def`/`class` keyword, not at the name (four to six columns earlier).
- Non-ASCII identifiers are split on ASCII letters only, so `naïve_data` is not analysed and `café_data` reports the meaningless fragment `caf`.
- `lambda` parameters, `match` captures, `import ... as ...`, `except ... as ...` and PEP 695 type parameters are not collected as definitions.
- Suggestions are ordered by English word frequency with alphabetical ties, as before; the review could not reproduce the claim that this degrades to plain alphabetical order.

## [0.2.0] - 2026-11-04

This release keeps the 0.1.0 detection engine exactly as it was and rebuilds
everything around it: the output, the error handling, the documentation and the
test-suite.

### Preserved (unchanged from 0.1.0)

The following parts of `typo_guard/core.py` are structurally identical to 0.1.0.
`tests/test_engine_preserved.py` checks this against a verbatim copy of the 0.1.0
file (`tests/fixtures/original_core_0_1_0.py`). It also checks that both engines
return identical diagnostics on every example, source and test file in the repository.

- `_DefinitionVisitor`: which AST nodes count as variables, arguments, functions and classes.
- `split_identifier` and its three regular expressions (snake_case, camelCase, PascalCase, acronyms).
- `DEFAULT_ALLOWLIST`: the built-in programming vocabulary, Python keywords and built-in names.
- The word rules: skip words shorter than 3 letters, allowlisted words and digits, then look the word up in `pyspellchecker` with `distance=1`.
- Suggestion ranking: by dictionary word frequency, ties alphabetical, at most 3 by default.
- The `Diagnostic` record, the `TG001` text line format and the JSON schema.
- The public API (`lint_source`, `lint_file`, `lint_paths`, `split_identifier`, `extract_identifiers`) and the exit codes 0/1/2.

### Added

- **Table output (new default).** Findings are shown in a five-column table: Location, Kind, Identifier, Misspelled, Suggestions. Each column has its own colour, and the misspelled fragment is shown exactly as written (`Reponse`, not `reponse`).
- **Adaptive layout.** The full table is used when it fits the terminal. On a classic 80-column terminal the output switches to one table per file, with the path printed once as a heading. Very narrow terminals get a two-line-per-finding list. Piped or redirected output always gets the full table and is never cropped.
- **Summary line** with counts of typos, affected identifiers, affected files and scanned files, followed by a tip on how to allowlist words.
- `--format text` keeps the 0.1.0 one-line-per-finding output for scripts and editors. `--format json` is unchanged.
- `--exclude PATTERN` to skip directory or file names while recursing. Common tool directories (`.venv`, `venv`, `.git`, `__pycache__`, `build`, `dist`, `node_modules`, `*.egg-info`, ...) are skipped by default; explicit paths are always scanned.
- `--max-suggestions N`, `--color auto|always|never`, `--no-color`, `--exit-zero`, `--version`, and `python -m typo_guard`.
- Allowlist files now accept several words per line (space or comma separated), inline `#` comments and a UTF-8 BOM.
- `scan_paths()` / `ScanResult` / `FileError`: a fault-tolerant API that returns findings *and* per-file errors.
- `py.typed` marker, `.pre-commit-hooks.yaml`, a GitHub Actions workflow (Python 3.9 to 3.14 on Linux, plus Windows and macOS) and a project vocabulary file so typo-guard lints its own code.
- `docs/MANUAL.md`: the full instruction manual (installation, usage, internals, test guide, troubleshooting).
- 152 automated tests (0.1.0 had 14), including the ten manual acceptance cases from the 0.1.0 README, now automated.

### Fixed

Each of these was reproduced against 0.1.0 and is covered by a regression test in
`tests/test_hardening.py`.

- A file starting with a UTF-8 byte-order mark (common on Windows) failed with "invalid non-printable character U+FEFF". It is now linted normally.
- Files with a PEP 263 encoding declaration (for example `# -*- coding: latin-1 -*-`) failed to decode. They are now read the way the Python interpreter reads them.
- A NUL byte raised an uncaught `ValueError` traceback on Python 3.9 to 3.11. It is now reported as a syntax error on every version.
- Deeply nested source code crashed with an uncaught `MemoryError` and, worse, exited with code 1 ("typos found"). Very long expressions crashed with `RecursionError`. Both are now reported as "source too complex to analyse" with exit code 2.
- One unparsable file aborted the whole run and hid all other results. Every other file is now still reported, the error is listed per file, and the exit code is 2.
- A directory whose name ends in `.py` crashed the run with `IsADirectoryError`. It is now skipped.
- Scanning a project that contained a virtual environment failed on third-party (or Python 2) files. Such directories are now skipped by default.
- `SyntaxWarning`s that belong to the scanned code (for example `"\d"`) were printed to the terminal. They are now suppressed, and linting also works under `python -W error`.
- An explicit non-`.py` path was ignored silently. A warning is now shown, plus a warning when no Python file was found at all.
- The English dictionary was rebuilt for every file. Forty small files took about 9 seconds; they now take about 0.35 seconds.
- `max_suggestions=-1` silently dropped the last suggestion. Negative values now mean "no suggestions".
- `lint_source(..., allow_words="numpy")` treated the string as a list of letters. A single string is now one word.
- `typo-guard ... | head` printed a `BrokenPipeError` traceback. It is now silent.
- Output to a non-UTF-8 console could raise `UnicodeEncodeError`. Unsupported characters are now replaced, and box drawing and symbols fall back to ASCII.
- File names containing `[` `]` could be interpreted as terminal markup. All table cells are now plain text.
- A missing, directory or binary `--allowlist` produced a traceback. Each case now has a clear one-line error.
- Undecodable files are reported as "cannot decode file" with a hint, instead of a confusing "syntax error" that repeated the path.
- Any unexpected internal error now produces a one-line message and exit code 2 (set `TYPO_GUARD_DEBUG=1` for the traceback). Ctrl+C exits with code 130.
- Directory walking no longer follows symbolic links, so a symlink loop cannot hang the run.

### Changed

- The default output is the table. Use `--format text` for the exact 0.1.0 output.
- Two 0.1.0 CLI tests that compared the old text output now pass `--format text`; their assertions are otherwise unchanged.

## [0.1.0]

- Initial release: AST-based identifier extraction, naming-style-aware splitting, offline `pyspellchecker` lookup, allowlists, recursive linting, text and JSON output, CI exit codes.

[0.2.4]: https://github.com/vincentcheng0318gitlab/Group-20/compare/v0.2.0...v0.2.4
[0.2.0]: https://github.com/vincentcheng0318gitlab/Group-20/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/vincentcheng0318gitlab/Group-20/releases/tag/v0.1.0
