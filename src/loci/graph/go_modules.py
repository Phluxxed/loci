from __future__ import annotations

import hashlib
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal, Sequence

from .contracts import GraphContractError, JSONValue
from .profiles import read_contained_file


MAX_GO_CONTROL_BYTES = 1_048_576
MAX_GO_DIRECTIVES_PER_FILE = 10_000
MAX_GO_PACKAGE_BINDINGS = 10_000
MAX_GO_PACKAGE_NODES = 10_000

GoModuleProblemCode = Literal[
    "GRAPH_GO_MODULE_INVALID",
    "GRAPH_GO_WORKSPACE_INVALID",
    "GRAPH_GO_PACKAGE_INVALID",
    "GRAPH_GO_INDEX_LIMIT_EXCEEDED",
]

_MODULE_ELEMENT_RE = re.compile(r"[A-Za-z0-9._~-]+")
_VERSION_RE = re.compile(r"[^\s/()]+")
_GO_VERSION_RE = re.compile(r"[1-9][0-9]*\.[0-9]+(?:\.[0-9]+)?")
_WINDOWS_RESERVED_RE = re.compile(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])", re.I)
_WINDOWS_SHORT_NAME_RE = re.compile(r".*~[0-9]+", re.I)


@dataclass(frozen=True, slots=True)
class GoRequirement:
    module_path: str
    version: str


@dataclass(frozen=True, slots=True)
class GoExclusion:
    module_path: str
    version: str


@dataclass(frozen=True, slots=True)
class GoReplacement:
    module_path: str
    version: str | None
    local_root: str | None
    remote_path: str | None
    remote_version: str | None


@dataclass(frozen=True, slots=True)
class GoModule:
    source: str
    root: str
    module_path: str
    requirements: tuple[GoRequirement, ...]
    exclusions: tuple[GoExclusion, ...]
    replacements: tuple[GoReplacement, ...]


@dataclass(frozen=True, slots=True)
class GoWorkspace:
    source: str
    root: str
    go_version: str
    use_roots: tuple[str, ...]
    replacements: tuple[GoReplacement, ...]


@dataclass(frozen=True, slots=True)
class GoModuleProblem:
    code: GoModuleProblemCode
    message: str
    source: str
    details: dict[str, JSONValue]


@dataclass(frozen=True, slots=True)
class GoModuleContext:
    modules: tuple[GoModule, ...]
    workspaces: tuple[GoWorkspace, ...]


@dataclass(frozen=True, slots=True)
class GoModuleLoad:
    context: GoModuleContext
    input_hashes: dict[str, str]
    problems: tuple[GoModuleProblem, ...]


@dataclass(frozen=True, slots=True)
class _Directive:
    keyword: str
    entries: tuple[tuple[str, ...], ...]
    line: int


class _GoControlError(ValueError):
    def __init__(
        self,
        reason: str,
        *,
        line: int | None = None,
        limit: int | None = None,
        limit_error: bool = False,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.line = line
        self.limit = limit
        self.limit_error = limit_error


def load_go_module_context(
    repo_path: Path,
    control_candidates: Sequence[Path],
) -> GoModuleLoad:
    root = repo_path.resolve(strict=True)
    modules: list[GoModule] = []
    workspaces: list[GoWorkspace] = []
    input_hashes: dict[str, str] = {}
    problems: list[GoModuleProblem] = []

    candidates = sorted(
        {_candidate_source(root, path): path for path in control_candidates}.items()
    )
    for source, path in candidates:
        kind = "workspace" if path.name == "go.work" else "module"
        try:
            data, source = _read_control_candidate(root, path)
        except _GoControlError as exc:
            input_hashes[source] = _sentinel_hash(kind, exc.reason)
            problems.append(_problem(kind, source, exc))
            continue

        input_hashes[source] = hashlib.sha256(data).hexdigest()
        try:
            directives = _parse_directives(data)
            control_root = root / _control_root(source)
            if kind == "workspace":
                workspaces.append(
                    _parse_workspace(root, control_root, source, directives)
                )
            else:
                modules.append(_parse_module(root, control_root, source, directives))
        except _GoControlError as exc:
            problems.append(_problem(kind, source, exc))

    return GoModuleLoad(
        context=GoModuleContext(
            modules=tuple(sorted(modules, key=lambda item: item.source)),
            workspaces=tuple(sorted(workspaces, key=lambda item: item.source)),
        ),
        input_hashes=dict(sorted(input_hashes.items())),
        problems=tuple(sorted(
            problems,
            key=lambda item: (item.source, item.code, item.message),
        )),
    )


def _read_control_candidate(root: Path, path: Path) -> tuple[bytes, str]:
    candidate = path if path.is_absolute() else root / path
    source = _candidate_source(root, candidate)
    try:
        lexical = Path(os.path.abspath(candidate))
        lexical.relative_to(root)
    except ValueError as exc:
        raise _GoControlError("outside_repository") from exc

    try:
        candidate_stat = os.lstat(lexical)
    except OSError as exc:
        raise _GoControlError("unreadable") from exc
    if stat.S_ISLNK(candidate_stat.st_mode):
        raise _GoControlError("symlink")
    if not stat.S_ISREG(candidate_stat.st_mode):
        raise _GoControlError("not_regular")
    if candidate_stat.st_size > MAX_GO_CONTROL_BYTES:
        raise _GoControlError(
            "control_file_too_large",
            limit=MAX_GO_CONTROL_BYTES,
            limit_error=True,
        )
    try:
        resolved = lexical.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise _GoControlError("outside_repository") from exc
    try:
        return read_contained_file(
            root,
            resolved,
            record="Go control file",
            max_bytes=MAX_GO_CONTROL_BYTES,
        )
    except GraphContractError as exc:
        raise _GoControlError("unsafe_or_unreadable") from exc


def _parse_directives(data: bytes) -> tuple[_Directive, ...]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _GoControlError("invalid_utf8") from exc
    token_lines = _tokenize_lines(text)
    directives: list[_Directive] = []
    index = 0
    logical_count = 0
    while index < len(token_lines):
        line, tokens = token_lines[index]
        index += 1
        if not tokens:
            continue
        if tokens[0] == ")":
            raise _GoControlError("unexpected_block_close", line=line)
        keyword = tokens[0]
        if len(tokens) == 2 and tokens[1] == "(":
            entries: list[tuple[str, ...]] = []
            closed = False
            while index < len(token_lines):
                entry_line, entry = token_lines[index]
                index += 1
                if not entry:
                    continue
                if entry == (")",):
                    closed = True
                    break
                if "(" in entry or ")" in entry:
                    raise _GoControlError("nested_or_malformed_block", line=entry_line)
                entries.append(entry)
            if not closed:
                raise _GoControlError("unterminated_block", line=line)
        else:
            if "(" in tokens or ")" in tokens:
                raise _GoControlError("malformed_directive", line=line)
            entries = [tokens[1:]]
        logical_count += max(1, len(entries))
        if logical_count > MAX_GO_DIRECTIVES_PER_FILE:
            raise _GoControlError(
                "directive_limit_exceeded",
                line=line,
                limit=MAX_GO_DIRECTIVES_PER_FILE,
                limit_error=True,
            )
        directives.append(_Directive(keyword, tuple(entries), line))
    return tuple(directives)


def _tokenize_lines(text: str) -> list[tuple[int, tuple[str, ...]]]:
    lines: list[tuple[int, tuple[str, ...]]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        tokens: list[str] = []
        index = 0
        while index < len(line):
            char = line[index]
            if char in " \t\r":
                index += 1
                continue
            if line.startswith("//", index):
                break
            if line.startswith("/*", index) or line.startswith("*/", index):
                raise _GoControlError("block_comments_not_allowed", line=line_number)
            if line.startswith("=>", index):
                tokens.append("=>")
                index += 2
                continue
            if char in "()":
                tokens.append(char)
                index += 1
                continue
            if char in {'"', "`"}:
                token, index = _quoted_token(line, index, line_number)
                tokens.append(token)
                continue
            start = index
            while index < len(line):
                if line[index] in " \t\r()\"`":
                    break
                if line.startswith("//", index) or line.startswith("=>", index):
                    break
                index += 1
            if start == index:
                raise _GoControlError("invalid_token", line=line_number)
            tokens.append(line[start:index])
        lines.append((line_number, tuple(tokens)))
    return lines


def _quoted_token(line: str, start: int, line_number: int) -> tuple[str, int]:
    quote = line[start]
    index = start + 1
    value: list[str] = []
    while index < len(line):
        char = line[index]
        if char == quote:
            return "".join(value), index + 1
        if quote == '"' and char == "\\":
            index += 1
            if index >= len(line):
                raise _GoControlError("unterminated_string", line=line_number)
            value.append(line[index])
            index += 1
            continue
        value.append(char)
        index += 1
    raise _GoControlError("unterminated_string", line=line_number)


def _parse_module(
    repo_root: Path,
    control_root: Path,
    source: str,
    directives: Sequence[_Directive],
) -> GoModule:
    module_paths: list[str] = []
    requirements: list[GoRequirement] = []
    exclusions: list[GoExclusion] = []
    replacements: list[GoReplacement] = []
    for directive in directives:
        if directive.keyword == "use":
            raise _GoControlError("workspace_directive_in_go_mod", line=directive.line)
        if directive.keyword == "module":
            module_paths.extend(
                _one_module_path(entry, directive.line) for entry in directive.entries
            )
        elif directive.keyword == "require":
            requirements.extend(
                _requirement(entry, directive.line) for entry in directive.entries
            )
        elif directive.keyword == "exclude":
            exclusions.extend(
                _exclusion(entry, directive.line) for entry in directive.entries
            )
        elif directive.keyword == "replace":
            replacements.extend(
                _replacement(repo_root, control_root, entry, directive.line)
                for entry in directive.entries
            )
    if len(module_paths) != 1:
        raise _GoControlError("module_directive_count")
    return GoModule(
        source=source,
        root=_control_root(source),
        module_path=module_paths[0],
        requirements=tuple(sorted(
            requirements,
            key=lambda item: (item.module_path, item.version),
        )),
        exclusions=tuple(sorted(
            exclusions,
            key=lambda item: (item.module_path, item.version),
        )),
        replacements=tuple(sorted(replacements, key=_replacement_sort_key)),
    )


def _parse_workspace(
    repo_root: Path,
    control_root: Path,
    source: str,
    directives: Sequence[_Directive],
) -> GoWorkspace:
    go_versions: list[str] = []
    use_roots: list[str] = []
    replacements: list[GoReplacement] = []
    for directive in directives:
        if directive.keyword in {"module", "require", "exclude"}:
            raise _GoControlError("module_directive_in_go_work", line=directive.line)
        if directive.keyword == "go":
            for entry in directive.entries:
                if len(entry) != 1 or not _GO_VERSION_RE.fullmatch(entry[0]):
                    raise _GoControlError("invalid_go_version", line=directive.line)
                go_versions.append(entry[0])
        elif directive.keyword == "use":
            for entry in directive.entries:
                if len(entry) != 1:
                    raise _GoControlError("invalid_use", line=directive.line)
                normalized = _contained_local_root(
                    repo_root,
                    control_root,
                    entry[0],
                    line=directive.line,
                    require_local_marker=False,
                )
                if normalized is not None:
                    use_roots.append(normalized)
        elif directive.keyword == "replace":
            replacements.extend(
                _replacement(repo_root, control_root, entry, directive.line)
                for entry in directive.entries
            )
    if len(go_versions) != 1:
        raise _GoControlError("go_directive_count")
    return GoWorkspace(
        source=source,
        root=_control_root(source),
        go_version=go_versions[0],
        use_roots=tuple(sorted(set(use_roots))),
        replacements=tuple(sorted(replacements, key=_replacement_sort_key)),
    )


def _one_module_path(entry: Sequence[str], line: int) -> str:
    if len(entry) != 1:
        raise _GoControlError("invalid_module", line=line)
    return _module_path(entry[0], line)


def _requirement(entry: Sequence[str], line: int) -> GoRequirement:
    if len(entry) != 2:
        raise _GoControlError("invalid_require", line=line)
    return GoRequirement(_module_path(entry[0], line), _version(entry[1], line))


def _exclusion(entry: Sequence[str], line: int) -> GoExclusion:
    if len(entry) != 2:
        raise _GoControlError("invalid_exclude", line=line)
    return GoExclusion(_module_path(entry[0], line), _version(entry[1], line))


def _replacement(
    repo_root: Path,
    control_root: Path,
    entry: Sequence[str],
    line: int,
) -> GoReplacement:
    if entry.count("=>") != 1:
        raise _GoControlError("invalid_replace", line=line)
    arrow = entry.index("=>")
    left = entry[:arrow]
    right = entry[arrow + 1:]
    if len(left) not in {1, 2} or len(right) not in {1, 2}:
        raise _GoControlError("invalid_replace", line=line)
    module_path = _module_path(left[0], line)
    version = _version(left[1], line) if len(left) == 2 else None
    if len(right) == 1:
        local_root = _contained_local_root(
            repo_root,
            control_root,
            right[0],
            line=line,
            require_local_marker=True,
        )
        return GoReplacement(module_path, version, local_root, None, None)
    return GoReplacement(
        module_path,
        version,
        None,
        _module_path(right[0], line),
        _version(right[1], line),
    )


def _module_path(value: str, line: int) -> str:
    if not value or value.startswith("/") or value.endswith("/"):
        raise _GoControlError("invalid_module_path", line=line)
    for element in value.split("/"):
        if (
            not element
            or not _MODULE_ELEMENT_RE.fullmatch(element)
            or element.startswith(".")
            or element.endswith(".")
        ):
            raise _GoControlError("invalid_module_path", line=line)
        prefix = element.split(".", 1)[0]
        if _WINDOWS_RESERVED_RE.fullmatch(prefix) or _WINDOWS_SHORT_NAME_RE.fullmatch(prefix):
            raise _GoControlError("invalid_module_path", line=line)
    return value


def _version(value: str, line: int) -> str:
    if not value or not _VERSION_RE.fullmatch(value):
        raise _GoControlError("invalid_version", line=line)
    return value


def _contained_local_root(
    repo_root: Path,
    control_root: Path,
    value: str,
    *,
    line: int,
    require_local_marker: bool,
) -> str | None:
    if not value or "\\" in value or "\x00" in value:
        raise _GoControlError("invalid_local_path", line=line)
    raw = Path(value)
    has_local_marker = (
        raw.is_absolute()
        or value in {".", ".."}
        or value.startswith("./")
        or value.startswith("../")
    )
    if require_local_marker and not has_local_marker:
        raise _GoControlError("invalid_local_path", line=line)
    candidate = raw if raw.is_absolute() else control_root / raw
    lexical = Path(os.path.abspath(candidate))
    try:
        lexical_relative = lexical.relative_to(repo_root)
    except ValueError:
        return None
    resolved = lexical.resolve(strict=False)
    try:
        resolved_relative = resolved.relative_to(repo_root)
    except ValueError as exc:
        raise _GoControlError("local_path_symlink_escape", line=line) from exc
    relative = resolved_relative if resolved != lexical else lexical_relative
    return relative.as_posix() or "."


def _control_root(source: str) -> str:
    parent = PurePosixPath(source).parent.as_posix()
    return "." if parent in {"", "."} else parent


def _replacement_sort_key(
    replacement: GoReplacement,
) -> tuple[str, str, str, str, str]:
    return (
        replacement.module_path,
        replacement.version or "",
        replacement.local_root or "",
        replacement.remote_path or "",
        replacement.remote_version or "",
    )


def _candidate_source(root: Path, path: Path) -> str:
    candidate = path if path.is_absolute() else root / path
    try:
        return Path(os.path.abspath(candidate)).relative_to(root).as_posix()
    except ValueError:
        return path.name


def _sentinel_hash(kind: str, reason: str) -> str:
    return hashlib.sha256(f"loci-go-{kind}:{reason}".encode()).hexdigest()


def _problem(kind: str, source: str, error: _GoControlError) -> GoModuleProblem:
    code: GoModuleProblemCode
    if error.limit_error:
        code = "GRAPH_GO_INDEX_LIMIT_EXCEEDED"
    elif kind == "workspace":
        code = "GRAPH_GO_WORKSPACE_INVALID"
    else:
        code = "GRAPH_GO_MODULE_INVALID"
    details: dict[str, JSONValue] = {"reason": error.reason}
    if error.line is not None:
        details["line"] = error.line
    if error.limit is not None:
        details["limit"] = error.limit
    message = (
        "Go workspace control file is invalid"
        if kind == "workspace"
        else "Go module control file is invalid"
    )
    return GoModuleProblem(code, message, source, details)
