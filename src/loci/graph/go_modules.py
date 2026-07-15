from __future__ import annotations

import hashlib
import os
import re
import stat
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal, Sequence

from loci.parser.symbols import Symbol

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
_KEYWORD_RE = re.compile(r"[a-z][a-z0-9]*")
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
class GoPackageBinding:
    import_prefix: str
    module_root: str
    declared_module_path: str
    source: str


@dataclass(frozen=True, slots=True)
class GoPackageIndex:
    modules: tuple[GoModule, ...]
    package_nodes: tuple[Symbol, ...]
    bindings_by_source_module: Mapping[str, tuple[GoPackageBinding, ...]]
    packages_by_binding: Mapping[tuple[str, str], Symbol]
    command_packages: frozenset[tuple[str, str]]


@dataclass(frozen=True, slots=True)
class GoPackageBuild:
    index: GoPackageIndex
    problems: tuple[GoModuleProblem, ...]


@dataclass(frozen=True, slots=True)
class _GoPackageDirectory:
    directory: str
    name: str
    anchor: Symbol


@dataclass(frozen=True, slots=True)
class _Directive:
    keyword: str
    entries: tuple[tuple[str, ...], ...]
    line: int
    is_block: bool


class _QuotedToken(str):
    pass


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
    """Parse bounded repository Go controls without executing the Go toolchain."""
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


def make_go_package_id(directory: str, import_path: str) -> str:
    normalized_directory = directory or "."
    return f"{normalized_directory}::{import_path}#package"


def build_go_package_index(
    context: GoModuleContext,
    *,
    file_nodes: Mapping[str, Symbol],
) -> GoPackageBuild:
    """Build deterministic package endpoints without resolving imports."""
    modules = tuple(sorted(context.modules, key=lambda item: item.source))
    directories, package_problems = _collect_go_package_directories(file_nodes)
    bindings_by_source, binding_problems = _build_go_package_bindings(
        context,
        modules,
    )
    problems = [*package_problems, *binding_problems]
    binding_count = sum(len(bindings) for bindings in bindings_by_source.values())
    if binding_count > MAX_GO_PACKAGE_BINDINGS:
        return _rejected_go_package_build(
            "binding_limit_exceeded",
            MAX_GO_PACKAGE_BINDINGS,
        )

    package_nodes: dict[str, Symbol] = {}
    packages_by_binding: dict[tuple[str, str], Symbol] = {}
    command_packages: set[tuple[str, str]] = set()
    for _, bindings in sorted(bindings_by_source.items()):
        for binding in bindings:
            for package in directories:
                if _owning_module_root(package.directory, modules) != binding.module_root:
                    continue
                suffix = _relative_package_suffix(
                    package.directory,
                    binding.module_root,
                )
                if suffix is None:
                    continue
                import_path = binding.import_prefix
                if suffix:
                    import_path = f"{import_path}/{suffix}"
                key = (binding.module_root, import_path)
                if package.name == "main":
                    command_packages.add(key)
                    continue
                node = _make_go_package_symbol(package, binding, import_path)
                package_nodes[node.id] = node
                packages_by_binding[key] = node

    if len(package_nodes) > MAX_GO_PACKAGE_NODES:
        return _rejected_go_package_build(
            "package_node_limit_exceeded",
            MAX_GO_PACKAGE_NODES,
        )

    return GoPackageBuild(
        index=GoPackageIndex(
            modules=modules,
            package_nodes=tuple(sorted(package_nodes.values(), key=lambda item: item.id)),
            bindings_by_source_module=dict(sorted(bindings_by_source.items())),
            packages_by_binding=dict(sorted(packages_by_binding.items())),
            command_packages=frozenset(command_packages),
        ),
        problems=tuple(sorted(
            problems,
            key=lambda item: (item.source, item.code, item.message),
        )),
    )


def _build_go_package_bindings(
    context: GoModuleContext,
    modules: Sequence[GoModule],
) -> tuple[dict[str, tuple[GoPackageBinding, ...]], list[GoModuleProblem]]:
    modules_by_root = {module.root: module for module in modules}
    bindings_by_source: dict[str, tuple[GoPackageBinding, ...]] = {}
    problems: list[GoModuleProblem] = []
    workspaces = tuple(sorted(context.workspaces, key=lambda item: item.source))

    for module in modules:
        candidates = [
            GoPackageBinding(
                import_prefix=module.module_path,
                module_root=module.root,
                declared_module_path=module.module_path,
                source=module.source,
            )
        ]
        workspace = _active_workspace(module, workspaces)
        if workspace is not None:
            for use_root in workspace.use_roots:
                used_module = modules_by_root.get(use_root)
                if used_module is None:
                    problems.append(
                        _binding_problem(
                            workspace.source,
                            "workspace_module_missing",
                            module_root=use_root,
                        )
                    )
                    continue
                candidates.append(
                    GoPackageBinding(
                        import_prefix=used_module.module_path,
                        module_root=used_module.root,
                        declared_module_path=used_module.module_path,
                        source=workspace.source,
                    )
                )

        for requirement in module.requirements:
            if _requirement_is_excluded(module, requirement):
                continue
            replacement, replacement_source, replacement_problem = (
                _select_local_replacement(
                    module,
                    requirement,
                    workspace,
                    modules_by_root,
                )
            )
            if replacement_problem is not None:
                problems.append(replacement_problem)
                continue
            if replacement is None or replacement.local_root is None:
                continue
            replacement_module = modules_by_root.get(replacement.local_root)
            if replacement_module is None:
                problems.append(
                    _binding_problem(
                        replacement_source,
                        "replacement_module_missing",
                        module_root=replacement.local_root,
                        import_prefix=requirement.module_path,
                    )
                )
                continue
            candidates.append(
                GoPackageBinding(
                    import_prefix=requirement.module_path,
                    module_root=replacement_module.root,
                    declared_module_path=replacement_module.module_path,
                    source=replacement_source,
                )
            )

        bindings, conflicts = _deduplicate_bindings(module, candidates)
        bindings_by_source[module.root] = bindings
        problems.extend(conflicts)

    return dict(sorted(bindings_by_source.items())), problems


def _active_workspace(
    module: GoModule,
    workspaces: Sequence[GoWorkspace],
) -> GoWorkspace | None:
    enclosing = [
        workspace
        for workspace in workspaces
        if _relative_package_suffix(module.root, workspace.root) is not None
    ]
    if not enclosing:
        return None
    nearest = max(enclosing, key=lambda item: (_path_depth(item.root), item.source))
    return nearest if module.root in nearest.use_roots else None


def _requirement_is_excluded(
    module: GoModule,
    requirement: GoRequirement,
) -> bool:
    return any(
        exclusion.module_path == requirement.module_path
        and exclusion.version == requirement.version
        for exclusion in module.exclusions
    )


def _select_local_replacement(
    module: GoModule,
    requirement: GoRequirement,
    workspace: GoWorkspace | None,
    modules_by_root: Mapping[str, GoModule],
) -> tuple[GoReplacement | None, str, GoModuleProblem | None]:
    module_matches = _matching_replacements(module.replacements, requirement)
    source = module.source
    matches = module_matches
    if workspace is not None:
        workspace_matches = _matching_replacements(
            workspace.replacements,
            requirement,
        )
        if workspace_matches:
            source = workspace.source
            matches = workspace_matches
            if any(item.version is not None for item in matches):
                versions = _workspace_requirement_versions(
                    workspace,
                    requirement.module_path,
                    modules_by_root,
                )
                if versions != {requirement.version}:
                    return None, source, _binding_problem(
                        source,
                        "workspace_requirement_version_conflict",
                        import_prefix=requirement.module_path,
                    )

    if not matches:
        return None, source, None
    roots = {item.local_root for item in matches}
    remote_targets = {(item.remote_path, item.remote_version) for item in matches}
    if len(roots) > 1 or len(remote_targets) > 1:
        return None, source, _binding_problem(
            source,
            "conflicting_local_replacements",
            import_prefix=requirement.module_path,
        )
    return matches[0], source, None


def _matching_replacements(
    replacements: Sequence[GoReplacement],
    requirement: GoRequirement,
) -> tuple[GoReplacement, ...]:
    matches = [
        replacement
        for replacement in replacements
        if replacement.module_path == requirement.module_path
        and replacement.version in {None, requirement.version}
    ]
    if any(replacement.version == requirement.version for replacement in matches):
        matches = [
            replacement
            for replacement in matches
            if replacement.version == requirement.version
        ]
    return tuple(matches)


def _workspace_requirement_versions(
    workspace: GoWorkspace,
    module_path: str,
    modules_by_root: Mapping[str, GoModule],
) -> set[str]:
    versions: set[str] = set()
    for root in workspace.use_roots:
        module = modules_by_root.get(root)
        if module is None:
            continue
        versions.update(
            requirement.version
            for requirement in module.requirements
            if requirement.module_path == module_path
            and not _requirement_is_excluded(module, requirement)
        )
    return versions


def _deduplicate_bindings(
    source_module: GoModule,
    candidates: Sequence[GoPackageBinding],
) -> tuple[tuple[GoPackageBinding, ...], list[GoModuleProblem]]:
    grouped: dict[str, list[GoPackageBinding]] = {}
    for binding in candidates:
        grouped.setdefault(binding.import_prefix, []).append(binding)

    bindings: list[GoPackageBinding] = []
    problems: list[GoModuleProblem] = []
    for import_prefix, matches in sorted(grouped.items()):
        targets = {
            (binding.module_root, binding.declared_module_path)
            for binding in matches
        }
        if len(targets) != 1:
            problems.append(
                _binding_problem(
                    source_module.source,
                    "conflicting_local_bindings",
                    import_prefix=import_prefix,
                )
            )
            continue
        bindings.append(min(matches, key=_binding_sort_key))
    return tuple(sorted(bindings, key=_binding_sort_key)), problems


def _binding_sort_key(binding: GoPackageBinding) -> tuple[str, str, str, str]:
    return (
        binding.import_prefix,
        binding.module_root,
        binding.declared_module_path,
        binding.source,
    )


def _rejected_go_package_build(reason: str, limit: int) -> GoPackageBuild:
    return GoPackageBuild(
        index=GoPackageIndex((), (), {}, {}, frozenset()),
        problems=(
            GoModuleProblem(
                code="GRAPH_GO_INDEX_LIMIT_EXCEEDED",
                message="Go package index exceeds the configured limit",
                source=".",
                details={"reason": reason, "limit": limit},
            ),
        ),
    )


def _binding_problem(
    source: str,
    reason: str,
    *,
    module_root: str | None = None,
    import_prefix: str | None = None,
) -> GoModuleProblem:
    details: dict[str, JSONValue] = {"reason": reason}
    if module_root is not None:
        details["module_root"] = module_root
    if import_prefix is not None:
        details["import_prefix"] = import_prefix
    return GoModuleProblem(
        code="GRAPH_GO_MODULE_INVALID",
        message="Go package binding is invalid",
        source=source,
        details=details,
    )


def _collect_go_package_directories(
    file_nodes: Mapping[str, Symbol],
) -> tuple[tuple[_GoPackageDirectory, ...], list[GoModuleProblem]]:
    grouped: dict[str, list[tuple[Symbol, str | None]]] = {}
    problems: list[GoModuleProblem] = []
    for path, node in sorted(file_nodes.items()):
        if node.kind != "file" or node.language != "go":
            continue
        normalized = _normalized_go_source_path(path, node)
        if normalized is None:
            problems.append(_package_problem("@invalid/go-file", "invalid_go_file_node"))
            continue
        if normalized.name.endswith("_test.go"):
            continue
        if "vendor" in normalized.parts:
            continue
        directory = normalized.parent.as_posix()
        if directory == ".":
            directory = "."
        grouped.setdefault(directory, []).append(
            (node, _go_package_name(node))
        )

    packages: list[_GoPackageDirectory] = []
    for directory, entries in sorted(grouped.items()):
        names = [name for _, name in entries]
        if any(name is None for name in names):
            problems.append(_package_problem(directory, "missing_package_declaration"))
            continue
        unique_names = set(names)
        if len(unique_names) != 1:
            problems.append(_package_problem(directory, "conflicting_package_declarations"))
            continue
        name = names[0]
        assert name is not None
        anchor = min((node for node, _ in entries), key=lambda item: item.file_path)
        packages.append(_GoPackageDirectory(directory, name, anchor))
    return tuple(packages), problems


def _normalized_go_source_path(path: str, node: Symbol) -> PurePosixPath | None:
    candidate = PurePosixPath(path)
    if (
        path != node.file_path
        or candidate.is_absolute()
        or any(part in {"", ".", ".."} for part in candidate.parts)
        or candidate.suffix != ".go"
    ):
        return None
    return candidate


def _go_package_name(node: Symbol) -> str | None:
    loci = node.metadata.get("loci")
    if not isinstance(loci, Mapping):
        return None
    declaration = loci.get("go_package")
    if not isinstance(declaration, Mapping):
        return None
    name = declaration.get("name")
    line = declaration.get("line")
    if (
        not isinstance(name, str)
        or not _valid_go_identifier(name)
        or isinstance(line, bool)
        or not isinstance(line, int)
        or line < 1
    ):
        return None
    return name


_GO_KEYWORDS = frozenset({
    "break", "default", "func", "interface", "select", "case", "defer",
    "go", "map", "struct", "chan", "else", "goto", "package", "switch",
    "const", "fallthrough", "if", "range", "type", "continue", "for",
    "import", "return", "var",
})


def _valid_go_identifier(value: str) -> bool:
    if not value or value == "_" or value in _GO_KEYWORDS:
        return False
    for index, char in enumerate(value):
        category = unicodedata.category(char)
        is_letter = char == "_" or category.startswith("L")
        if not is_letter and not (index > 0 and category == "Nd"):
            return False
    return True


def _owning_module_root(directory: str, modules: Sequence[GoModule]) -> str | None:
    owners = [
        module.root
        for module in modules
        if _relative_package_suffix(directory, module.root) is not None
    ]
    return max(owners, key=_path_depth, default=None)


def _relative_package_suffix(directory: str, root: str) -> str | None:
    directory_path = PurePosixPath(directory)
    if root == ".":
        return "" if directory == "." else directory
    try:
        relative = directory_path.relative_to(PurePosixPath(root))
    except ValueError:
        return None
    suffix = relative.as_posix()
    return "" if suffix == "." else suffix


def _path_depth(path: str) -> int:
    return 0 if path == "." else len(PurePosixPath(path).parts)


def _make_go_package_symbol(
    package: _GoPackageDirectory,
    binding: GoPackageBinding,
    import_path: str,
) -> Symbol:
    return Symbol(
        id=make_go_package_id(package.directory, import_path),
        name=package.name,
        qualified_name=import_path,
        kind="package",
        language="go",
        file_path=package.anchor.file_path,
        byte_offset=0,
        byte_length=0,
        signature=import_path,
        content_hash=package.anchor.content_hash,
        keywords=_package_keywords(import_path),
        metadata={
            "loci": {
                "go_package_node": True,
                "directory": package.directory,
                "import_path": import_path,
                "package_name": package.name,
                "module_root": binding.module_root,
                "declared_module_path": binding.declared_module_path,
            }
        },
        line=1,
        end_line=1,
    )


def _package_keywords(import_path: str) -> list[str]:
    words: list[str] = []
    for match in re.finditer(r"[A-Za-z0-9]+", import_path):
        word = match.group(0).lower()
        if word not in words:
            words.append(word)
    return words


def _package_problem(source: str, reason: str) -> GoModuleProblem:
    return GoModuleProblem(
        code="GRAPH_GO_PACKAGE_INVALID",
        message="Go package declaration is invalid",
        source=source,
        details={"reason": reason},
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
            lexical,
            record="Go control file",
            max_bytes=MAX_GO_CONTROL_BYTES,
        )
    except GraphContractError as exc:
        if exc.details.get("limit") == MAX_GO_CONTROL_BYTES:
            raise _GoControlError(
                "control_file_too_large",
                limit=MAX_GO_CONTROL_BYTES,
                limit_error=True,
            ) from exc
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
        if isinstance(keyword, _QuotedToken) or not _KEYWORD_RE.fullmatch(keyword):
            raise _GoControlError("invalid_directive_keyword", line=line)
        if len(tokens) == 2 and tokens[1] == "(":
            is_block = True
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
            is_block = False
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
        directives.append(_Directive(keyword, tuple(entries), line, is_block))
    return tuple(directives)


def _tokenize_lines(text: str) -> list[tuple[int, tuple[str, ...]]]:
    lines: list[tuple[int, tuple[str, ...]]] = []
    for line_number, line in enumerate(text.split("\n"), start=1):
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
            return _QuotedToken("".join(value)), index + 1
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
            if directive.is_block:
                raise _GoControlError("invalid_go_version", line=directive.line)
            for entry in directive.entries:
                if len(entry) != 1 or not _GO_VERSION_RE.fullmatch(entry[0]):
                    raise _GoControlError("invalid_go_version", line=directive.line)
                go_versions.append(str(entry[0]))
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
    return str(value)


def _version(value: str, line: int) -> str:
    if not value or not _VERSION_RE.fullmatch(value):
        raise _GoControlError("invalid_version", line=line)
    return str(value)


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
        return f"@outside/{path.name}"


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
