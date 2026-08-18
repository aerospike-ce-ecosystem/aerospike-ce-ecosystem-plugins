"""Extraction rules: what counts as a checkable claim, and what proves it.

A rule is (id, description, file glob, extractor, verifier). The extractor
pulls candidate claims out of a markdown file; the verifier says whether an
index confirms it. A rule that cannot find its index is reported as SKIPPED,
never as passing.

Adding a rule is the way to raise coverage. See README.md for the shape.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Iterator

# A claim is (line number, the literal text, optional detail for the report).
Claim = tuple[int, str, str]


@dataclass(frozen=True)
class Rule:
    id: str
    description: str
    globs: tuple[str, ...]
    source: str  # index key this rule needs
    extract: Callable[[str], Iterator[Claim]]
    verify: Callable[[object, str], bool]
    # Claims matching these are structurally unverifiable and are counted as
    # skipped rather than failed (documented placeholders, mostly).
    ignore: tuple[str, ...] = field(default=())


# ---------------------------------------------------------------------------
# shared extractors
# ---------------------------------------------------------------------------


def _lines(text: str):
    return enumerate(text.splitlines(), 1)


def _backticked(pattern: re.Pattern):
    """Extract backticked spans whose whole content matches `pattern`."""

    def extractor(text: str) -> Iterator[Claim]:
        in_fence = False
        for n, line in _lines(text):
            if line.lstrip().startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            for m in re.finditer(r"`([^`\n]+)`", line):
                s = m.group(1)
                if pattern.fullmatch(s):
                    yield (n, s, "")

    return extractor


# Placeholder tokens the reference pages use for interpolated values. Splitting
# a documented message on these leaves the literal runs, which is what has to
# appear in source. Keep this in sync with the "How the messages reach you"
# note in acko-operations/reference/validation-rules.md.
_PLACEHOLDER = re.compile(
    r'%\w'                      # a raw Go verb, if one leaked into the docs
    r'|\b(?:N|M|T|S|KEY|MIN|ID|FIELD|v|i|j|k)\b'
    r'|\\"[^"]*\\"|"[^"]*"'     # any quoted sub-value
    r'|<[^>]+>'                 # <inner CE error>
    r'|\.\.\.'
    r'|\d+'
)
_MIN_RUN = 12  # a run shorter than this matches too much to be evidence


def _quoted_message(text: str) -> Iterator[Claim]:
    """Backticked, double-quoted strings — the webhook error catalog shape."""
    in_fence = False
    for n, line in _lines(text):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for m in re.finditer(r'`"((?:[^"`\\]|\\.)*)"`', line):
            yield (n, m.group(1).replace('\\"', '"'), "")


def _message_runs(claim: str) -> list[str]:
    return [r.strip() for r in _PLACEHOLDER.split(claim) if len(r.strip()) >= _MIN_RUN]


def _verify_message(index, claim: str) -> bool:
    runs = _message_runs(claim)
    if not runs:
        return True  # too templated to check; counted as skipped by the caller
    return all(run in index.go_strings for run in runs)


def _checkable_message(claim: str) -> bool:
    return bool(_message_runs(claim))


# ---------------------------------------------------------------------------
# ACKO rules
# ---------------------------------------------------------------------------

_ACKO_GLOBS = (
    "skills/acko-*/SKILL.md",
    "skills/acko-*/reference/*.md",
)


def _crd_paths(text: str) -> Iterator[Claim]:
    in_fence = False
    for n, line in _lines(text):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for m in re.finditer(r"`((?:spec|status)\.[A-Za-z0-9_.\[\]-]+)`", line):
            yield (n, m.group(1), "")


def _normalise_crd_path(p: str) -> str:
    p = re.sub(r"\[[^\]]*\]", "", p)          # racks[0] / racks[] -> racks
    p = re.sub(r"\.(N|i|j|k)\b", "", p)       # racks.N -> racks
    return p.rstrip(".")


def _verify_crd_path(index, claim: str) -> bool:
    return _normalise_crd_path(claim) in index.crd_paths


_SEPARATOR = re.compile(r"^\s*\|[\s:\-|]+\|\s*$")


def _table_rows(text: str) -> Iterator[tuple[int, list[str]]]:
    """Yield (line, cells) for data rows only — header and separator skipped.

    A markdown table header is the line immediately above the `|---|` rule, so
    the header is recognised by lookahead rather than by guessing at its text.
    Without this, "Phase" and "Type" get extracted as if they were claims.
    """
    lines = text.splitlines()
    header_rows = set()
    for i, line in enumerate(lines):
        if _SEPARATOR.match(line) and i > 0:
            header_rows.add(i - 1)
            header_rows.add(i)
    for i, line in enumerate(lines):
        if i in header_rows or not line.strip().startswith("|"):
            continue
        yield i + 1, [c.strip() for c in line.strip().strip("|").split("|")]


def _table_first_col(pattern: re.Pattern):
    """Extract the first column of every markdown data row matching pattern."""

    def extractor(text: str) -> Iterator[Claim]:
        for n, cells in _table_rows(text):
            if not cells:
                continue
            cell = cells[0].strip("`*_ ")
            if pattern.fullmatch(cell):
                yield (n, cell, "")

    return extractor


def _const_table(text: str) -> Iterator[Claim]:
    """`| `NAME` | value | ... |` rows — name and value checked together."""
    for n, cells in _table_rows(text):
        if len(cells) < 2:
            continue
        name = cells[0].strip("`*_ ")
        value = cells[1].strip("`*_ ")
        if re.fullmatch(r"[A-Z][A-Z0-9_]{2,}", name) and re.fullmatch(r"-?\d+", value):
            yield (n, f"{name}={value}", f"documented value {value}")


def _verify_const_pair(index, claim: str) -> bool:
    name, _, value = claim.partition("=")
    actual = index.constants.get(name)
    if actual is None:
        return False
    return actual.replace("_", "").strip() == value.strip()


_ACKO_CHART = "aerospike-ce-kubernetes-operator"


def _helm_set_keys(text: str) -> Iterator[Claim]:
    """`--set key=` keys, but only for the ACKO chart.

    A `helm install` block routinely installs cert-manager first, and
    cert-manager has its own values with its own names — `crds.enabled` is
    real there and absent from ACKO's chart. Attributing every `--set` on the
    page to ACKO's values.yaml reports correct documentation as drift, which
    is worse than missing it: it costs a reviewer's time and teaches everyone
    to ignore the check.

    A `--set` belongs to the most recent `helm install`/`helm upgrade`
    command, so the extractor tracks which chart that was, across line
    continuations.
    """
    in_command = False        # inside a multi-line `helm ...` invocation
    command_is_acko = False

    for n, line in _lines(text):
        if re.search(r"\bhelm\s+(?:install|upgrade|template)\b", line):
            in_command = True
            command_is_acko = _ACKO_CHART in line
        elif in_command:
            command_is_acko = command_is_acko or _ACKO_CHART in line

        if in_command:
            attribute = command_is_acko
            if not line.rstrip().endswith("\\"):
                in_command = False    # command ends at the last unescaped EOL
        else:
            # Outside an invocation, a `--set` in an install-variant table or
            # bullet refers to the chart the page is about, unless the line
            # itself names another one.
            attribute = "cert-manager" not in line

        if not attribute:
            continue
        for m in re.finditer(r"--set(?:-string)?[= ]([A-Za-z][\w.]*)=", line):
            yield (n, m.group(1), "")


def _ackoctl_lines(text: str) -> Iterator[tuple[int, str]]:
    """Lines that are an actual `ackoctl` invocation, not prose mentioning it.

    Prose says things like "if `ackoctl guide get` 404s, say so and do not
    invent a policy" — extracting every following word as a subcommand turns
    "say", "so", "do" into failures. An invocation is either a whole line
    inside a fenced code block, or a backticked span that starts with the
    binary name.
    """
    in_fence = False
    for n, line in _lines(text):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            # `# ackoctl has no --previous equivalent` is a comment about the
            # CLI, and often a *negative* claim. Extracting from it inverts the
            # check: the rule would demand that a flag the docs say does not
            # exist does exist.
            if stripped.startswith("#"):
                continue
            if stripped.startswith("ackoctl ") or " ackoctl " in f" {stripped} ":
                yield n, stripped
            continue
        for m in re.finditer(r"`(ackoctl\s[^`\n]*)`", line):
            span = m.group(1)
            # `ackoctl <noun> <verb> [POSITIONAL] [--flag value]` is the
            # grammar, not an invocation — `--flag` is the word "flag".
            if re.search(r"<(?:noun|verb|flag|command|subcommand)>", span):
                continue
            yield n, span


def _ackoctl_invocations(text: str) -> Iterator[Claim]:
    """Yield the whole command path so the verifier can walk the cobra tree."""
    for n, cmd in _ackoctl_lines(text):
        after = cmd.split("ackoctl", 1)[1]
        path = []
        for token in after.split():
            if token.startswith("-"):
                continue  # a global flag may precede the subcommand
            if not re.fullmatch(r"[a-z][a-z0-9-]*", token):
                break     # placeholder, ALL-CAPS arg, shell operator
            path.append(token)
        if path:
            yield (n, " ".join(path), "")


def _verify_ackoctl_path(index, claim: str) -> bool:
    """Walk the cobra tree, distinguishing a bad verb from a positional arg.

    The rule that makes this useful: a *group* node (one with children) is
    never invoked directly, so the next token must be one of its children. A
    *leaf* takes positional arguments, so anything after it is data.

    `ackoctl k8s pod logs` therefore fails — `k8s` has children `{cluster}` and
    `pod` is not among them — while `ackoctl config use-context kind-local`
    passes, because `use-context` is a leaf and `kind-local` is a context name.
    Without the group/leaf distinction the first case passes too, which is the
    exact drift (`k8s pod logs` → `k8s cluster logs`) this repo has already had
    to fix once by hand.
    """
    tree = index.command_tree
    path: tuple[str, ...] = ()
    for token in claim.split():
        children = tree.get(path, set())
        if token in children:
            path += (token,)
            continue
        if children:
            return False       # group node, and this is not one of its verbs
        return len(path) > 0   # leaf reached; the rest are arguments
    return len(path) > 0


def _ackoctl_flags(text: str) -> Iterator[Claim]:
    """Long flags inside an actual `ackoctl` invocation."""
    for n, cmd in _ackoctl_lines(text):
        for m in re.finditer(r"(?<![\w-])--([a-z][\w-]*)", cmd):
            yield (n, m.group(1), "")


def _py_client_calls(text: str) -> Iterator[Claim]:
    seen_on_line = set()
    for n, line in _lines(text):
        for m in re.finditer(r"\b(?:client|aclient|async_client)\.(\w+)\s*\(", line):
            key = (n, m.group(1))
            if key in seen_on_line:
                continue
            seen_on_line.add(key)
            yield (n, m.group(1), "")


def _py_exceptions(text: str) -> Iterator[Claim]:
    """Exception classes named where the name has to be exactly right.

    Two positions: caught/raised in example code, and any backticked name with
    an `Error`/`Exception` suffix. The suffix rule alone would miss classes
    like `RecordNotFound`, which is why the `except` / `raise` forms are
    extracted regardless of how the name is spelled — those are the ones that
    fail loudly at runtime if wrong.
    """
    for n, line in _lines(text):
        for m in re.finditer(r"\bexcept\s+\(?([A-Za-z_][\w.]*(?:\s*,\s*[A-Za-z_][\w.]*)*)",
                             line):
            for name in re.split(r"\s*,\s*", m.group(1)):
                name = name.split(".")[-1]
                if re.fullmatch(r"[A-Z]\w*", name):
                    yield (n, name, "caught in an example")
        for m in re.finditer(r"\braise\s+([A-Z]\w*)\s*\(", line):
            yield (n, m.group(1), "raised in an example")
        for m in re.finditer(r"`([A-Z]\w*(?:Error|Exception))`", line):
            yield (n, m.group(1), "")


def _domain_keys(text: str) -> Iterator[Claim]:
    """Operator-owned `acko.io/…` / `aerospike.io/…` keys.

    Scoped to the two domains the operator defines. `app.kubernetes.io/*` and
    cloud-provider annotations are upstream and are not checked — see the
    label_keys index for why.
    """
    for n, line in _lines(text):
        for m in re.finditer(
            r"(?<![\w./-])((?:acko|aerospike)\.io/[a-z0-9._-]+)", line
        ):
            yield (n, m.group(1), "")


def _condition_refs(text: str) -> Iterator[Claim]:
    """Condition types written as `type=Foo` / `Condition<Foo>` / jsonpath.

    Only forms that unambiguously name a status condition are extracted; a bare
    capitalised word could be anything.
    """
    pats = (
        r'conditions\[\?\(@\.type=="(\w+)"\)\]',   # jsonpath selector
        r'`(Condition[A-Z]\w+)`',                  # the Go constant name
    )
    for n, line in _lines(text):
        for p in pats:
            for m in re.finditer(p, line):
                yield (n, m.group(1), "")


# Python builtins and stdlib names that legitimately appear in prose/examples.
_PY_EXC_ALLOW = (
    "Exception", "BaseException", "ValueError", "TypeError", "KeyError",
    "RuntimeError", "OSError", "IOError", "AttributeError", "IndexError",
    "NotImplementedError", "TimeoutError", "ConnectionError", "ImportError",
    "HTTPException", "ValidationError", "AssertionError", "StopIteration",
)


RULES: list[Rule] = [
    Rule(
        id="acko-error-strings",
        description="Webhook error messages quoted in the reference catalog must "
                    "appear, run for run, in operator source",
        globs=_ACKO_GLOBS,
        source="acko",
        extract=_quoted_message,
        verify=_verify_message,
    ),
    Rule(
        id="acko-crd-paths",
        description="`spec.*` / `status.*` field paths must resolve in the "
                    "generated CRD schema",
        globs=_ACKO_GLOBS + ("skills/acko-deploy/examples/*.yaml",),
        source="acko",
        extract=_crd_paths,
        verify=_verify_crd_path,
    ),
    Rule(
        id="acko-event-reasons",
        description="Event reasons must be defined in internal/controller/events.go",
        globs=("skills/acko-operations/reference/events.md",),
        source="acko",
        extract=_table_first_col(re.compile(r"[A-Z][A-Za-z]{5,}")),
        verify=lambda idx, c: c in idx.events,
    ),
    Rule(
        id="acko-phases",
        description="Cluster phases must be AerospikePhase constants",
        globs=("skills/acko-config-reference/reference/conditions-and-phases.md",),
        source="acko",
        extract=_table_first_col(re.compile(r"[A-Z][A-Za-z]{3,}")),
        verify=lambda idx, c: c in idx.phases or c in idx.conditions,
    ),
    Rule(
        id="acko-dynamic-params",
        description="Parameters documented as dynamic must be in the operator's "
                    "dynamic_params.go allowlist",
        globs=("skills/acko-config-reference/reference/parameters-8.md",),
        source="acko",
        extract=lambda t: _dynamic_yes_rows(t),
        verify=lambda idx, c: any(
            p.split(".")[-1] == c for p in idx.dynamic_params
        ),
    ),
    Rule(
        id="acko-helm-values",
        description="`--set key=` keys must exist in the operator chart's values.yaml",
        globs=("skills/acko-deploy/reference/helm-install.md", "skills/acko-*/**/*.md"),
        source="acko",
        extract=_helm_set_keys,
        verify=lambda idx, c: c in idx.helm_values,
    ),
    Rule(
        id="acko-label-keys",
        description="Domain-qualified label/annotation keys must appear in "
                    "operator source",
        globs=_ACKO_GLOBS,
        source="acko",
        extract=_domain_keys,
        verify=lambda idx, c: c in idx.label_keys,
        # User-chosen, not operator-defined: the docs use it to force a
        # pod-spec-hash change, and any annotation key would do. There is
        # nothing in operator source for it to match.
        ignore=("acko.io/restart-trigger",),
    ),
    Rule(
        id="apy-constant-values",
        description="Constant name+value pairs must match rust/src/constants.rs",
        globs=("skills/aerospike-py-api/reference/constants.md",
               "skills/aerospike-py-api/reference/policies.md"),
        source="aerospike_py",
        extract=_const_table,
        verify=_verify_const_pair,
    ),
    Rule(
        id="apy-client-methods",
        description="`client.foo(...)` calls must exist on Client/AsyncClient "
                    "in the type stubs",
        globs=("skills/aerospike-py-*/**/*.md", "skills/aerospike-py-*/SKILL.md"),
        source="aerospike_py",
        extract=_py_client_calls,
        verify=lambda idx, c: c in idx.client_methods,
    ),
    Rule(
        id="apy-exceptions",
        description="Exception class names must be defined in aerospike-py",
        globs=("skills/aerospike-py-*/**/*.md", "skills/aerospike-py-*/SKILL.md",
               "skills/bug-reporter/**/*.md"),
        source="aerospike_py",
        extract=_py_exceptions,
        verify=lambda idx, c: c in idx.exceptions,
        ignore=_PY_EXC_ALLOW,
    ),
    Rule(
        id="apy-constant-names",
        description="`SCREAMING_CASE` constants referenced in aerospike-py "
                    "skills must be registered on the module",
        globs=("skills/aerospike-py-*/**/*.md", "skills/aerospike-py-*/SKILL.md"),
        source="aerospike_py",
        extract=_backticked(re.compile(
            r"(?:POLICY|AS|TTL|PRIV|AUTH|REGEX|OP|INDEX|SERIALIZER|"
            r"CLIENT_SIDE|LOG|MAP|LIST|BIT|HLL|EXPIRATION)_[A-Z0-9_]+"
        )),
        verify=lambda idx, c: c in idx.constant_names,
    ),
    Rule(
        id="acko-conditions",
        description="Status condition types must be Condition* constants",
        globs=("skills/acko-*/SKILL.md", "skills/acko-*/reference/*.md"),
        source="acko",
        extract=_condition_refs,
        verify=lambda idx, c: c in idx.conditions,
    ),
    Rule(
        id="ackoctl-commands",
        description="`ackoctl <noun> <verb>` paths must resolve in the CLI's "
                    "cobra command tree",
        globs=("skills/ackoctl/SKILL.md", "skills/ackoctl/reference/*.md",
               "skills/acko-debugging/**/*.md"),
        source="ackoctl",
        extract=_ackoctl_invocations,
        verify=_verify_ackoctl_path,
    ),
    Rule(
        id="ackoctl-flags",
        description="Long flags on `ackoctl` lines must be registered on some "
                    "cobra command",
        globs=("skills/ackoctl/SKILL.md", "skills/ackoctl/reference/*.md",
               "skills/acko-debugging/**/*.md"),
        source="ackoctl",
        extract=_ackoctl_flags,
        verify=lambda idx, c: c in idx.flags,
        ignore=("help",),
    ),
]


def _dynamic_yes_rows(text: str) -> Iterator[Claim]:
    """Rows of the parameters table whose Dynamic column says Yes."""
    for n, cells in _table_rows(text):
        if len(cells) < 3:
            continue
        name = cells[0].strip("`*_ ")
        dynamic = cells[2].strip("`*_ ").lower()
        if dynamic == "yes" and re.fullmatch(r"[a-z][a-z0-9-]+", name):
            yield (n, name, "documented Dynamic=Yes")
