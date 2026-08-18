"""Searchable indexes built from the source repositories the skills document.

Each index is a set (or dict) of facts read out of source, so a rule can ask
"is this identifier real?" without knowing anything about Go, Rust or cobra.

Everything here is deliberately syntactic. There is no compiler and no test
run: an index answers "does this string appear where it would have to appear
if the claim were true", which catches renames, typos and inventions, and does
not catch semantics. Rules that need semantics are out of scope by design --
see README.md.
"""

from __future__ import annotations

import json
import re
from functools import cached_property
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_GO_STR = re.compile(r'"((?:[^"\\\n]|\\.)*)"')
# Go concatenates adjacent literals across lines: `"a " +\n  "b"`. Fold those
# before extracting so a message split over three lines is indexed as one.
_GO_CONCAT = re.compile(r'"\s*\+\s*\n?\s*"')
_GO_CONST = re.compile(
    r'^\s*(?:const\s+)?([A-Z]\w*)\s+(?:[\w.]+\s*)?=\s*"([^"]*)"', re.M
)
_JSON_TAG = re.compile(r'json:"([^",]+)')
_RUST_CONST = re.compile(
    r'^\s*pub const ([A-Z][A-Z0-9_]*)\s*:\s*[\w:<>&\[\] ]+\s*=\s*(.+?);', re.M
)
# What PyO3 actually registers on the module: `m.add("NAME", 1)?;`
_PYO3_ADD = re.compile(r'\bm\.add\(\s*"([A-Z][A-Z0-9_]*)"\s*,\s*([^)]+?)\s*\)')
# What the type stub advertises: `NAME: Literal[1]`
_PYI_LITERAL = re.compile(
    r'^([A-Z][A-Z0-9_]*)\s*:\s*(?:Final\[)?Literal\[\s*(-?\d+)\s*\]', re.M
)
_PY_DEF = re.compile(r'^\s*(?:async\s+)?def\s+(\w+)', re.M)
_PY_CLASS = re.compile(r'^\s*class\s+(\w+)', re.M)
_PY_ASSIGN = re.compile(r'^([A-Za-z_]\w*)\s*[:=]', re.M)
_COBRA_USE = re.compile(r'Use:\s*"([^"\s]+)')
# Any pflag registrar: .StringVar, .BoolVarP, .StringArrayVar, .IntSliceVarP, …
_COBRA_FLAG = re.compile(
    r'\.[A-Z]\w*Var P?\(\s*&[\w.\[\]()]+\s*,\s*"([a-zA-Z0-9][\w-]*)"'.replace(" ", "")
)
_GO_FUNC = re.compile(r'^func\s+(\w+)\s*\(', re.M)
_ADD_CHILD = re.compile(r'\b(new\w*Cmd)\s*\(')


def _is_test(path: Path) -> bool:
    n = path.name
    return n.endswith("_test.go") or n.endswith("_test.rs") or "/tests/" in str(path)


def _read(path: Path) -> str:
    try:
        return path.read_text(errors="replace")
    except OSError:
        return ""


def _walk_schema(node, prefix: str, out: set[str]) -> None:
    """Collect every dotted path in a CRD openAPIV3Schema."""
    if not isinstance(node, dict):
        return
    for name, child in (node.get("properties") or {}).items():
        path = f"{prefix}.{name}" if prefix else name
        out.add(path)
        _walk_schema(child, path, out)
    items = node.get("items")
    if isinstance(items, dict):
        # List entries keep the parent path: `spec.racks.id` and
        # `spec.racks[].id` and `spec.racks[0].id` all normalise to the same
        # thing, so index the un-subscripted form and normalise on lookup.
        _walk_schema(items, prefix, out)
    if isinstance(node.get("additionalProperties"), dict):
        _walk_schema(node["additionalProperties"], prefix, out)


def _flatten_yaml(node, prefix: str, out: set[str]) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            path = f"{prefix}.{k}" if prefix else str(k)
            out.add(path)
            _flatten_yaml(v, path, out)


# ---------------------------------------------------------------------------
# ACKO (aerospike-ce-kubernetes-operator)
# ---------------------------------------------------------------------------


class AckoIndex:
    key = "acko"

    def __init__(self, root: Path):
        self.root = root

    @cached_property
    def _go_files(self) -> list[Path]:
        dirs = ["api", "internal", "cmd", "controllers"]
        return [
            p
            for d in dirs
            for p in (self.root / d).rglob("*.go")
            if not _is_test(p)
        ]

    @cached_property
    def go_strings(self) -> str:
        """All Go string literals, newline-joined, with concatenations folded.

        Kept as one blob rather than a set: webhook messages interpolate in the
        middle (`"rack ID must be > 0, got %d (…)"`), so rules substring-match
        literal runs rather than looking up whole messages.
        """
        parts = []
        for p in self._go_files:
            text = _GO_CONCAT.sub("", _read(p))
            parts.extend(m.group(1).replace('\\"', '"') for m in _GO_STR.finditer(text))
        return "\n".join(parts)

    @cached_property
    def go_string_set(self) -> set[str]:
        return set(self.go_strings.split("\n"))

    @cached_property
    def events(self) -> set[str]:
        src = _read(self.root / "internal/controller/events.go")
        return {m.group(2) for m in _GO_CONST.finditer(src)}

    @cached_property
    def phases(self) -> set[str]:
        src = _read(self.root / "api/v1alpha1/aerospikecluster_types.go")
        return {
            m.group(2)
            for m in _GO_CONST.finditer(src)
            if m.group(1).startswith("AerospikePhase")
        }

    @cached_property
    def conditions(self) -> set[str]:
        """Condition types, by both their value and their Go constant name.

        The reference pages cite both forms — `ConditionDynamicConfigDegraded`
        when pointing at source, `DynamicConfigDegraded` when showing what
        `kubectl` prints — and both are true statements about the operator.
        """
        src = _read(self.root / "api/v1alpha1/aerospikecluster_types.go")
        out: set[str] = set()
        for m in _GO_CONST.finditer(src):
            if m.group(1).startswith("Condition"):
                out.add(m.group(1))
                out.add(m.group(2))
        return out

    @cached_property
    def dynamic_params(self) -> set[str]:
        src = _read(self.root / "internal/configdiff/dynamic_params.go")
        return set(re.findall(r'^\s*"([\w.-]+)":\s*true', src, re.M))

    @cached_property
    def crd_paths(self) -> set[str]:
        """Every dotted path in the AerospikeCluster / template CRD schemas."""
        out: set[str] = set()
        base = self.root / "config/crd/bases"
        for f in sorted(base.glob("*.yaml")):
            try:
                doc = yaml.safe_load(_read(f))
            except yaml.YAMLError:
                continue
            for version in (doc or {}).get("spec", {}).get("versions", []):
                schema = version.get("schema", {}).get("openAPIV3Schema", {})
                _walk_schema(schema, "", out)
        return out

    @cached_property
    def helm_values(self) -> set[str]:
        out: set[str] = set()
        for f in self.root.rglob("charts/*/values.yaml"):
            try:
                _flatten_yaml(yaml.safe_load(_read(f)), "", out)
            except yaml.YAMLError:
                continue
        return out

    @cached_property
    def label_keys(self) -> set[str]:
        """Operator-owned label/annotation keys, plus the CR's apiVersion.

        Deliberately scoped to the `acko.io` / `aerospike.io` domains. Upstream
        keys (`app.kubernetes.io/*`, cloud-provider annotations) are not the
        operator's to define, so asserting they appear in operator source would
        produce noise, not signal — and the failure this rule exists to catch,
        an invented `aerospike.io/...` selector that silently matches nothing,
        lives entirely in those two domains.
        """
        keys = {
            s
            for s in re.findall(
                r'(?<![\w./-])((?:acko|aerospike)\.io/[a-z0-9._-]+)', self.go_strings
            )
        }
        src = _read(self.root / "api/v1alpha1/groupversion_info.go")
        group = re.search(r'Group:\s*"([^"]+)"', src)
        version = re.search(r'Version:\s*"([^"]+)"', src)
        if group and version:
            keys.add(f"{group.group(1)}/{version.group(1)}")
        return keys


# ---------------------------------------------------------------------------
# aerospike-py
# ---------------------------------------------------------------------------


class AerospikePyIndex:
    key = "aerospike_py"

    def __init__(self, root: Path):
        self.root = root

    @cached_property
    def constants(self) -> dict[str, str]:
        """Python-visible constant values.

        Two sources, and they must agree: `m.add("NAME", value)?` is what PyO3
        actually registers on the module, and `NAME: Literal[value]` in the type
        stub is what a reader's editor shows. A disagreement between them is
        itself a defect, so it is reported as an unknown value rather than
        silently preferring one.
        """
        registered: dict[str, str] = {}
        src = _read(self.root / "rust/src/constants.rs")
        for m in _PYO3_ADD.finditer(src):
            registered[m.group(1)] = m.group(2).strip().rstrip(",")
        for m in _RUST_CONST.finditer(src):
            registered.setdefault(m.group(1), m.group(2).strip().rstrip(","))

        stub = _read(self.root / "src/aerospike_py/__init__.pyi")
        for m in _PYI_LITERAL.finditer(stub):
            name, val = m.group(1), m.group(2).strip()
            if name in registered and registered[name] != val:
                registered[name] = "<disagreement: rust=%s stub=%s>" % (
                    registered[name], val)
            else:
                registered.setdefault(name, val)
        return registered

    @cached_property
    def constant_names(self) -> set[str]:
        return set(self.constants)

    @cached_property
    def _stub_files(self) -> list[Path]:
        return sorted((self.root / "src/aerospike_py").rglob("*.pyi"))

    @cached_property
    def symbols(self) -> set[str]:
        out: set[str] = set()
        for p in self._stub_files:
            src = _read(p)
            out |= set(_PY_DEF.findall(src))
            out |= set(_PY_CLASS.findall(src))
            out |= set(_PY_ASSIGN.findall(src))
        return out

    @cached_property
    def client_methods(self) -> set[str]:
        """Methods on Client / AsyncClient in the type stubs."""
        src = _read(self.root / "src/aerospike_py/__init__.pyi")
        out: set[str] = set()
        current = None
        for line in src.splitlines():
            cls = _PY_CLASS.match(line)
            if cls:
                current = cls.group(1)
                continue
            if current in ("Client", "AsyncClient"):
                d = re.match(r'\s+(?:async\s+)?def\s+(\w+)', line)
                if d:
                    out.add(d.group(1))
        return out

    @cached_property
    def exceptions(self) -> set[str]:
        """Every exception class aerospike-py defines.

        Not all of them end in `Error`: `RecordNotFound`, `RecordTooBig`,
        `BinNotFound` and `FilteredOut` are classes too, so a suffix heuristic
        would reject true claims about them.
        """
        out: set[str] = set()
        stub = _read(self.root / "src/aerospike_py/exception.pyi")
        out |= set(re.findall(r'^class\s+(\w+)\s*\(', stub, re.M))
        rust = _read(self.root / "rust/src/errors.rs")
        # create_exception!(module, Name, Base, "docstring");
        out |= set(re.findall(r'create_exception!\(\s*[\w:]+\s*,\s*(\w+)', rust))
        out |= set(re.findall(r'\b([A-Z]\w*(?:Error|Exception))\b', rust))
        return out

    @cached_property
    def rust_strings(self) -> str:
        parts = []
        for p in (self.root / "rust/src").rglob("*.rs"):
            if _is_test(p):
                continue
            parts.extend(m.group(1) for m in _GO_STR.finditer(_read(p)))
        return "\n".join(parts)

    @cached_property
    def pytest_markers(self) -> set[str]:
        src = _read(self.root / "pyproject.toml")
        block = re.search(r'markers\s*=\s*\[(.*?)\]', src, re.S)
        if not block:
            return set()
        return set(re.findall(r'"(\w+)\s*:', block.group(1)))


# ---------------------------------------------------------------------------
# ackoctl
# ---------------------------------------------------------------------------


class AckoctlIndex:
    key = "ackoctl"

    def __init__(self, root: Path):
        self.root = root

    @cached_property
    def _go_files(self) -> list[Path]:
        return [p for p in self.root.rglob("*.go") if not _is_test(p)]

    @cached_property
    def _src(self) -> str:
        return "\n".join(_read(p) for p in self._go_files)

    @cached_property
    def _funcs(self) -> dict[str, str]:
        """Map each `func newXCmd(...)` to its body text."""
        bodies: dict[str, str] = {}
        for p in self._go_files:
            src = _read(p)
            marks = [(m.start(), m.group(1)) for m in _GO_FUNC.finditer(src)]
            for i, (start, name) in enumerate(marks):
                end = marks[i + 1][0] if i + 1 < len(marks) else len(src)
                bodies[name] = src[start:end]
        return bodies

    @cached_property
    def command_tree(self) -> dict[tuple[str, ...], set[str]]:
        """Full cobra command tree, as {path: set of child tokens}.

        Reconstructed from `Use:` strings plus `AddCommand(newXCmd(...))`
        wiring. Knowing the tree — rather than a flat bag of verbs — is what
        lets the rule tell `ackoctl config use-context kind-local` (valid, with
        a context *name* as the argument) from a subcommand that does not
        exist. A flat check calls `kind-local` a bad subcommand; a tree check
        knows `use-context` is a leaf and stops.
        """
        tree: dict[tuple[str, ...], set[str]] = {}

        def token_of(func: str) -> str | None:
            body = self._funcs.get(func)
            if not body:
                return None
            m = _COBRA_USE.search(body)
            return m.group(1) if m else None

        def walk(func: str, path: tuple[str, ...], seen: frozenset[str]) -> None:
            if func in seen:
                return
            body = self._funcs.get(func)
            if body is None:
                return
            children: set[str] = set()
            for call in _ADD_CHILD.finditer(body):
                child = call.group(1)
                if child == func:
                    continue
                tok = token_of(child)
                if tok:
                    children.add(tok)
            tree.setdefault(path, set()).update(children)
            for call in _ADD_CHILD.finditer(body):
                child = call.group(1)
                tok = token_of(child)
                if tok and child != func:
                    walk(child, path + (tok,), seen | {func})

        roots = [f for f in self._funcs if f in ("newRootCmd", "NewRootCmd")]
        for r in roots:
            walk(r, (), frozenset())
        return tree

    @cached_property
    def commands(self) -> set[str]:
        """Every command token anywhere in the tree (flat fallback)."""
        flat = {t for children in self.command_tree.values() for t in children}
        flat |= {u.split()[0] for u in _COBRA_USE.findall(self._src) if u.strip()}
        return flat

    @cached_property
    def flags(self) -> set[str]:
        return set(_COBRA_FLAG.findall(self._src))

    @cached_property
    def go_strings(self) -> str:
        return "\n".join(m.group(1) for m in _GO_STR.finditer(self._src))

    @cached_property
    def rest_paths(self) -> set[str]:
        return {s for s in self.go_strings.split("\n") if s.startswith("/api/")}


# ---------------------------------------------------------------------------


INDEX_CLASSES = {
    "acko": AckoIndex,
    "aerospike_py": AerospikePyIndex,
    "ackoctl": AckoctlIndex,
}


def load_sources(config_path: Path, checkouts: dict[str, Path]):
    config = json.loads(config_path.read_text())
    out = {}
    for key in config["sources"]:
        if key in checkouts:
            out[key] = INDEX_CLASSES[key](checkouts[key])
    return out
