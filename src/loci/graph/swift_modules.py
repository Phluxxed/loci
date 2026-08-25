"""Swift package manifests to module nodes.

`Package.swift` is executable Swift, not a declarative manifest, so a package
can compute its target list at run time. Nothing here evaluates it. The literal
declaration form is read from the syntax tree and anything else is recorded as
an unsupported configuration, which keeps a manifest we cannot read from
becoming a manifest we guess at.
"""

from __future__ import annotations

import os
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Literal, Sequence

from loci.parser.symbols import Symbol

from .contracts import GraphContractError, JSONValue
from .profiles import read_contained_file


MAX_SWIFT_CONTROL_BYTES = 1_048_576
MAX_SWIFT_TARGETS_PER_PACKAGE = 1_000
MAX_SWIFT_MODULE_NODES = 10_000

SWIFT_MANIFEST_NAME = "Package.swift"

SwiftModuleProblemCode = Literal[
    "GRAPH_SWIFT_PACKAGE_INVALID",
    "GRAPH_SWIFT_TARGET_INVALID",
    "GRAPH_SWIFT_INDEX_LIMIT_EXCEEDED",
]

SwiftTargetKind = Literal[
    "target",
    "testTarget",
    "executableTarget",
    "macro",
]

# Only these declare a module with Swift sources in this repository. `plugin`,
# `binaryTarget` and `systemLibrary` name build tooling or prebuilt artefacts,
# not a compilation unit whose files we index.
_TARGET_KINDS: frozenset[str] = frozenset(
    {"target", "testTarget", "executableTarget", "macro"}
)
_TEST_TARGET_KINDS: frozenset[str] = frozenset({"testTarget"})


@dataclass(frozen=True, slots=True)
class SwiftTarget:
    """One target declared literally in a package manifest."""

    name: str
    kind: SwiftTargetKind
    declared_path: str | None
    directory: str | None
    dependencies: tuple[str, ...]
    line: int


@dataclass(frozen=True, slots=True)
class SwiftPackage:
    source: str
    root: str
    name: str
    content_hash: str
    targets: tuple[SwiftTarget, ...]


@dataclass(frozen=True, slots=True)
class SwiftModuleProblem:
    code: SwiftModuleProblemCode
    message: str
    source: str
    details: dict[str, JSONValue]


@dataclass(frozen=True, slots=True)
class SwiftModuleContext:
    packages: tuple[SwiftPackage, ...]


@dataclass(frozen=True, slots=True)
class SwiftModuleLoad:
    context: SwiftModuleContext
    input_hashes: dict[str, str]
    problems: tuple[SwiftModuleProblem, ...]


@dataclass(frozen=True, slots=True)
class SwiftModuleIndex:
    packages: tuple[SwiftPackage, ...]
    module_nodes: tuple[Symbol, ...]
    modules_by_name: Mapping[str, Symbol]
    directories_by_module: Mapping[str, str]

    @classmethod
    def empty(cls) -> SwiftModuleIndex:
        return cls(
            packages=(),
            module_nodes=(),
            modules_by_name={},
            directories_by_module={},
        )


@dataclass(frozen=True, slots=True)
class SwiftModuleBuild:
    index: SwiftModuleIndex
    problems: tuple[SwiftModuleProblem, ...]


class _SwiftControlError(ValueError):
    def __init__(
        self,
        reason: str,
        *,
        limit: int | None = None,
        limit_error: bool = False,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.limit = limit
        self.limit_error = limit_error


def make_swift_module_id(directory: str, name: str) -> str:
    """Stable id for a module node.

    Keyed by the declaring manifest's directory as well as the target name, so
    two packages that happen to name a target the same way stay distinct.
    """
    root = directory or "."
    return f"{root}::{name}#module"


def load_swift_module_context(
    repo_path: Path,
    control_candidates: Sequence[Path],
) -> SwiftModuleLoad:
    """Read every `Package.swift` candidate into a literal package declaration."""
    root = repo_path.resolve()
    packages: list[SwiftPackage] = []
    problems: list[SwiftModuleProblem] = []
    input_hashes: dict[str, str] = {}

    for candidate in sorted(set(control_candidates), key=str):
        source = _candidate_source(root, candidate)
        try:
            data, content_hash = _read_control_candidate(root, candidate)
        except _SwiftControlError as error:
            problems.append(_package_problem(source, error.reason, limit=error.limit))
            continue
        input_hashes[source] = content_hash
        package, package_problems = _parse_manifest(
            data,
            source=source,
            content_hash=content_hash,
            root=root,
        )
        problems.extend(package_problems)
        if package is not None:
            packages.append(package)

    return SwiftModuleLoad(
        context=SwiftModuleContext(packages=tuple(packages)),
        input_hashes=input_hashes,
        problems=tuple(problems),
    )


def build_swift_module_index(context: SwiftModuleContext) -> SwiftModuleBuild:
    """Turn literal package declarations into module nodes.

    A target name that two packages both declare is dropped rather than
    arbitrated: an `import` of that name cannot be attributed to either, and a
    guessed attribution is worse than an unresolved import.
    """
    if not isinstance(context, SwiftModuleContext):
        raise GraphContractError(
            "INVALID_GRAPH_SCHEMA",
            "Swift module context is invalid",
            {},
        )

    problems: list[SwiftModuleProblem] = []
    by_name: dict[str, list[tuple[SwiftPackage, SwiftTarget]]] = {}
    for package in context.packages:
        for target in package.targets:
            by_name.setdefault(target.name, []).append((package, target))

    nodes: list[Symbol] = []
    modules_by_name: dict[str, Symbol] = {}
    directories_by_module: dict[str, str] = {}
    for name in sorted(by_name):
        declarations = by_name[name]
        if len(declarations) > 1:
            problems.append(
                SwiftModuleProblem(
                    code="GRAPH_SWIFT_TARGET_INVALID",
                    message="Swift target name is declared by more than one package",
                    source=declarations[0][0].source,
                    details={
                        "reason": "duplicate_target_name",
                        "target": name,
                        "sources": [package.source for package, _ in declarations],
                    },
                )
            )
            continue
        package, target = declarations[0]
        node = _make_swift_module_symbol(package, target)
        nodes.append(node)
        modules_by_name[name] = node
        if target.directory is not None:
            directories_by_module[node.id] = target.directory

    if len(nodes) > MAX_SWIFT_MODULE_NODES:
        return SwiftModuleBuild(
            index=SwiftModuleIndex.empty(),
            problems=(
                SwiftModuleProblem(
                    code="GRAPH_SWIFT_INDEX_LIMIT_EXCEEDED",
                    message="Swift module index exceeds its node limit",
                    source="",
                    details={
                        "reason": "module_nodes_exceeded",
                        "limit": MAX_SWIFT_MODULE_NODES,
                    },
                ),
            ),
        )

    return SwiftModuleBuild(
        index=SwiftModuleIndex(
            packages=context.packages,
            module_nodes=tuple(nodes),
            modules_by_name=modules_by_name,
            directories_by_module=directories_by_module,
        ),
        problems=tuple(problems),
    )


def _parse_manifest(
    data: bytes,
    *,
    source: str,
    content_hash: str,
    root: Path,
) -> tuple[SwiftPackage | None, tuple[SwiftModuleProblem, ...]]:
    from tree_sitter_language_pack import get_parser

    tree = get_parser("swift").parse(data)
    if tree.root_node.has_error:
        return None, (_package_problem(source, "manifest_unparsed"),)

    call = _package_call(tree.root_node, data)
    if call is None:
        return None, (_package_problem(source, "unsupported_configuration"),)

    arguments = _labelled_arguments(call, data)
    name = _string_literal(arguments.get("name"), data)
    if not name:
        return None, (_package_problem(source, "unsupported_configuration"),)

    problems: list[SwiftModuleProblem] = []
    declarations = _target_declarations(arguments.get("targets"), data)
    if declarations is None:
        return None, (_package_problem(source, "unsupported_configuration"),)
    if len(declarations) > MAX_SWIFT_TARGETS_PER_PACKAGE:
        return None, (
            _package_problem(
                source,
                "targets_exceeded",
                limit=MAX_SWIFT_TARGETS_PER_PACKAGE,
            ),
        )

    package_root = str(PurePosixPath(source).parent)
    if package_root == ".":
        package_root = ""
    counts = {
        kind: sum(1 for other, _, _ in declarations if _is_test(other) == _is_test(kind))
        for kind, _, _ in declarations
    }

    targets: list[SwiftTarget] = []
    for kind, node, line in declarations:
        target_arguments = _labelled_arguments(node, data)
        target_name = _string_literal(target_arguments.get("name"), data)
        if not target_name:
            problems.append(
                SwiftModuleProblem(
                    code="GRAPH_SWIFT_TARGET_INVALID",
                    message="Swift target declaration is not statically readable",
                    source=source,
                    details={"reason": "unsupported_configuration", "line": line},
                )
            )
            continue
        declared_path = _string_literal(target_arguments.get("path"), data)
        directory, directory_reason = _target_directory(
            root=root,
            package_root=package_root,
            kind=kind,
            name=target_name,
            declared_path=declared_path,
            sole_of_its_class=counts.get(kind, 0) == 1,
        )
        if directory is None:
            problems.append(
                SwiftModuleProblem(
                    code="GRAPH_SWIFT_TARGET_INVALID",
                    message="Swift target has no readable source directory",
                    source=source,
                    details={
                        "reason": directory_reason,
                        "target": target_name,
                        "line": line,
                    },
                )
            )
        targets.append(
            SwiftTarget(
                name=target_name,
                kind=kind,
                declared_path=declared_path,
                directory=directory,
                dependencies=_target_dependencies(target_arguments.get("dependencies"), data),
                line=line,
            )
        )

    return (
        SwiftPackage(
            source=source,
            root=package_root,
            name=name,
            content_hash=content_hash,
            targets=tuple(targets),
        ),
        tuple(problems),
    )


def _is_test(kind: str) -> bool:
    return kind in _TEST_TARGET_KINDS


def _target_directory(
    *,
    root: Path,
    package_root: str,
    kind: str,
    name: str,
    declared_path: str | None,
    sole_of_its_class: bool,
) -> tuple[str | None, str]:
    """Resolve a target's source directory the way SwiftPM lays one out.

    An explicit ``path:`` wins. Otherwise the convention is
    ``Sources/<target>`` (``Tests/<target>`` for a test target), and SwiftPM
    also accepts the bare ``Sources`` directory when the package declares only
    one target of that class — which is how several packages here are laid out.
    """
    base = "Tests" if _is_test(kind) else "Sources"
    if declared_path is not None:
        candidate = _contained_directory(root, package_root, declared_path)
        if candidate is None:
            return None, "path_outside_repository"
        return (candidate, "") if _is_directory(root, candidate) else (None, "declared_path_missing")

    conventional = _join(package_root, f"{base}/{name}")
    if _is_directory(root, conventional):
        return conventional, ""
    fallback = _join(package_root, base)
    if sole_of_its_class and _is_directory(root, fallback):
        return fallback, ""
    return None, "target_directory_missing"


def _contained_directory(root: Path, package_root: str, declared: str) -> str | None:
    joined = PurePosixPath(_join(package_root, declared))
    parts: list[str] = []
    for part in joined.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if not parts:
                return None
            parts.pop()
            continue
        parts.append(part)
    normalized = "/".join(parts)
    try:
        (root / normalized).resolve().relative_to(root)
    except (OSError, ValueError):
        return None
    return normalized


def _join(prefix: str, suffix: str) -> str:
    suffix = suffix.strip("/")
    if not prefix:
        return suffix
    return f"{prefix}/{suffix}" if suffix else prefix


def _is_directory(root: Path, relative: str) -> bool:
    candidate = root / relative
    try:
        return candidate.is_dir() and not candidate.is_symlink()
    except OSError:
        return False


def _package_call(root_node: Any, source: bytes) -> Any | None:
    """The `Package(...)` call expression, or None if the manifest has none."""
    stack = [root_node]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        if node.type != "call_expression":
            continue
        callee = next(
            (child for child in node.named_children if child.type != "call_suffix"),
            None,
        )
        if callee is not None and callee.type == "simple_identifier":
            if _text(callee, source) == "Package":
                return node
    return None


def _target_declarations(
    node: Any | None,
    source: bytes,
) -> list[tuple[str, Any, int]] | None:
    """Target calls that are direct elements of the `targets:` array.

    Scoped deliberately: a `.plugin(name:)` inside a target's own `plugins:`
    list names a dependency, not a target, and a whole-file scan reads those as
    declarations.
    """
    if node is None:
        return []
    if node.type != "array_literal":
        return None
    declarations: list[tuple[str, Any, int]] = []
    for element in node.named_children:
        if element.type != "call_expression":
            continue
        kind = _leading_dot_name(element, source)
        if kind is None or kind not in _TARGET_KINDS:
            continue
        declarations.append((kind, element, element.start_point[0] + 1))
    return declarations


def _leading_dot_name(node: Any, source: bytes) -> str | None:
    """The member name of a `.target(...)`-style implicit member call."""
    callee = next(
        (child for child in node.named_children if child.type != "call_suffix"),
        None,
    )
    if callee is None:
        return None
    if callee.type == "prefix_expression":
        identifier = next(
            (child for child in callee.named_children if child.type == "simple_identifier"),
            None,
        )
        return _text(identifier, source) if identifier is not None else None
    if callee.type == "navigation_expression":
        suffix = callee.child_by_field_name("suffix")
        member = suffix.child_by_field_name("suffix") if suffix is not None else None
        if member is not None and member.type == "simple_identifier":
            return _text(member, source)
    return None


def _labelled_arguments(node: Any, source: bytes) -> dict[str, Any]:
    suffix = next(
        (child for child in node.named_children if child.type == "call_suffix"),
        None,
    )
    if suffix is None:
        return {}
    arguments = next(
        (child for child in suffix.named_children if child.type == "value_arguments"),
        None,
    )
    if arguments is None:
        return {}
    labelled: dict[str, Any] = {}
    for argument in arguments.named_children:
        if argument.type != "value_argument":
            continue
        label = next(
            (
                child
                for child in argument.named_children
                if child.type == "value_argument_label"
            ),
            None,
        )
        if label is None or not argument.named_children:
            continue
        value = argument.named_children[-1]
        if value is label:
            continue
        labelled.setdefault(_text(label, source), value)
    return labelled


def _string_literal(node: Any | None, source: bytes) -> str | None:
    """A literal string argument, or None when the value is computed."""
    if node is None or node.type != "line_string_literal":
        return None
    parts = [
        child for child in node.named_children if child.type == "line_str_text"
    ]
    if not parts:
        # `path: ""` is SwiftPM's way of saying "the package directory".
        return ""
    if len(parts) != 1:
        # An interpolated string is not a literal name.
        return None
    return _text(parts[0], source)


def _target_dependencies(node: Any | None, source: bytes) -> tuple[str, ...]:
    """Target names this target depends on, ignoring cross-package products."""
    if node is None or node.type != "array_literal":
        return ()
    names: list[str] = []
    for element in node.named_children:
        if element.type == "line_string_literal":
            value = _string_literal(element, source)
        elif element.type == "call_expression":
            member = _leading_dot_name(element, source)
            if member not in {"target", "byName"}:
                continue
            value = _string_literal(
                _labelled_arguments(element, source).get("name"),
                source,
            )
        else:
            continue
        if value is not None and value not in names:
            names.append(value)
    return tuple(names)


def _text(node: Any, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", "replace")


def _make_swift_module_symbol(package: SwiftPackage, target: SwiftTarget) -> Symbol:
    directory = target.directory if target.directory is not None else package.root
    return Symbol(
        id=make_swift_module_id(package.root, target.name),
        name=target.name,
        qualified_name=target.name,
        kind="module",
        language="swift",
        file_path=package.source,
        byte_offset=0,
        byte_length=0,
        signature=target.name,
        content_hash=package.content_hash,
        keywords=_module_keywords(target.name),
        metadata={
            "loci": {
                "swift_module_node": True,
                "package_name": package.name,
                "package_root": package.root,
                "target_kind": target.kind,
                "directory": directory,
                "has_sources": target.directory is not None,
            }
        },
        line=target.line,
        end_line=target.line,
    )


def _module_keywords(name: str) -> list[str]:
    words: list[str] = []
    current: list[str] = []
    for character in name:
        if character.isupper() and current:
            words.append("".join(current).lower())
            current = [character]
        elif character.isalnum():
            current.append(character)
        elif current:
            words.append("".join(current).lower())
            current = []
    if current:
        words.append("".join(current).lower())
    unique: list[str] = []
    for word in [name.lower(), *words]:
        if word and word not in unique:
            unique.append(word)
    return unique


def _package_problem(
    source: str,
    reason: str,
    *,
    limit: int | None = None,
) -> SwiftModuleProblem:
    details: dict[str, JSONValue] = {"reason": reason}
    if limit is not None:
        details["limit"] = limit
    return SwiftModuleProblem(
        code="GRAPH_SWIFT_PACKAGE_INVALID",
        message="Swift package manifest is not readable",
        source=source,
        details=details,
    )


def _candidate_source(root: Path, path: Path) -> str:
    candidate = path if path.is_absolute() else root / path
    try:
        return str(PurePosixPath(candidate.relative_to(root)))
    except ValueError:
        return str(PurePosixPath(path))


def _read_control_candidate(root: Path, path: Path) -> tuple[bytes, str]:
    candidate = path if path.is_absolute() else root / path
    try:
        lexical = Path(os.path.abspath(candidate))
        lexical.relative_to(root)
    except ValueError as exc:
        raise _SwiftControlError("outside_repository") from exc

    try:
        candidate_stat = os.lstat(lexical)
    except OSError as exc:
        raise _SwiftControlError("unreadable") from exc
    if stat.S_ISLNK(candidate_stat.st_mode):
        raise _SwiftControlError("symlink")
    if not stat.S_ISREG(candidate_stat.st_mode):
        raise _SwiftControlError("not_regular")
    if candidate_stat.st_size > MAX_SWIFT_CONTROL_BYTES:
        raise _SwiftControlError(
            "control_file_too_large",
            limit=MAX_SWIFT_CONTROL_BYTES,
            limit_error=True,
        )
    try:
        resolved = lexical.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise _SwiftControlError("outside_repository") from exc
    try:
        return read_contained_file(
            root,
            lexical,
            record="Swift control file",
            max_bytes=MAX_SWIFT_CONTROL_BYTES,
        )
    except GraphContractError as exc:
        if exc.details.get("limit") == MAX_SWIFT_CONTROL_BYTES:
            raise _SwiftControlError(
                "control_file_too_large",
                limit=MAX_SWIFT_CONTROL_BYTES,
                limit_error=True,
            ) from exc
        raise _SwiftControlError("unsafe_or_unreadable") from exc
