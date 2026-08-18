#!/usr/bin/env python3
"""Verify factual claims in skills/ against pinned checkouts of the source repos.

Why this exists
---------------
A drift audit of these skills checked 1,770 claims and found 128 wrong (7.2%).
The dangerous subset was not the obviously-wrong kind: ~20 were commands that
exit 0 and print nothing, so neither Claude nor the user learns the instruction
was bad. Six identifiers had never existed in ANY version of the source — they
were wrong when written, which means the gap is authoring verification, not
keeping up with upstream. Nothing scored the skills, so they accumulated
unnoticed.

Design bias: precision over recall
----------------------------------
This checker deliberately verifies a NARROW set of claim kinds, chosen because
each resolves to a closed, enumerable set in source (a condition-type constant
list, a flag registration, a route decorator). It does not attempt fuzzy prose
checking.

That bias is deliberate and was learned the hard way. An earlier version of this
check compared documented webhook error strings against Go string literals and
reported 29 failures, of which 19 were false positives. Go assembles most of
those messages from format verbs and `+`-concatenated literals spanning several
source lines, so the documented rendering ("spec.size N exceeds CE maximum of 8")
is not a substring of anything in source. Joining concatenations was not enough —
the format verbs still broke it. That check was REMOVED rather than shipped
noisy: a check that cries wolf two times in three gets disabled within a week,
and then catches nothing at all. Every extractor below is written to under-report
rather than guess, and a category that cannot be made precise is left to humans
and named in COVERAGE.

Honest accounting is part of the contract: `--report` prints how many claims
were checked, and `coverage` states plainly which claim kinds are NOT covered.
Do not describe a green run as "the skills are verified" — it means "the claim
kinds listed under COVERAGE are consistent with the pinned SHAs".

Usage
-----
    python3 scripts/verify_skill_claims.py --sources <dir>   # <dir>/<repo>/...
    python3 scripts/verify_skill_claims.py --coverage        # what is/isn't checked
    python3 scripts/verify_skill_claims.py --sources <dir> --format github

Exit codes: 0 clean, 1 claims failed, 2 setup/usage error.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
LOCK_FILE = Path(__file__).resolve().parent / "sources.lock"

ACKO = "aerospike-ce-kubernetes-operator"
ACKOCTL = "ackoctl"
PY = "aerospike-py"
ACM = "aerospike-cluster-manager"


# --------------------------------------------------------------------------
# Findings
# --------------------------------------------------------------------------


@dataclass
class Finding:
    path: str
    line: int
    category: str
    claim: str
    message: str

    def format_text(self) -> str:
        return (
            f"  {self.path}:{self.line}\n"
            f"    [{self.category}] {self.claim}\n"
            f"    {self.message}"
        )

    def format_github(self) -> str:
        msg = f"[{self.category}] {self.claim} — {self.message}".replace("\n", " ")
        return f"::error file={self.path},line={self.line}::{msg}"


@dataclass
class Stats:
    checked: int = 0
    by_category: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def count(self, category: str, n: int = 1) -> None:
        self.checked += n
        self.by_category[category] += n


# --------------------------------------------------------------------------
# Source-of-truth extraction
#
# Each function returns the closed set a claim kind is checked against. If an
# extractor returns an empty set the corresponding check is SKIPPED rather than
# failing every claim — an extractor that silently stops matching (upstream
# refactor, renamed file) must not manifest as a wall of false failures.
# --------------------------------------------------------------------------


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _walk(root: Path, suffix: str, skip: tuple[str, ...] = ()) -> list[Path]:
    if not root.is_dir():
        return []
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in {".git", "vendor", "node_modules", ".venv"}]
        for fn in filenames:
            if fn.endswith(suffix) and not any(s in fn for s in skip):
                out.append(Path(dirpath) / fn)
    return out


def acko_conditions(root: Path) -> set[str]:
    src = _read(root / "api/v1alpha1/aerospikecluster_types.go")
    return set(re.findall(r"Condition[A-Za-z]+\s*=\s*\"([A-Za-z]+)\"", src))


def acko_phases(root: Path) -> set[str]:
    src = _read(root / "api/v1alpha1/aerospikecluster_types.go")
    m = re.search(r"\+kubebuilder:validation:Enum=([A-Za-z;]+)\s*\ntype AerospikePhase", src)
    return set(m.group(1).split(";")) if m else set()


def acko_event_reasons(root: Path) -> set[str]:
    src = _read(root / "internal/controller/events.go")
    return set(re.findall(r"Event[A-Za-z]+\s*=\s*\"([A-Za-z]+)\"", src))


def acko_label_keys(root: Path) -> set[str]:
    """Label/annotation keys the operator sets, plus chart-applied selector keys."""
    keys = set(re.findall(r'"([a-z0-9.-]+/[a-z0-9._-]+)"', _read(root / "internal/utils/labels.go")))
    # Chart and kustomize both label the manager pods with a bare `control-plane`.
    for path in _walk(root / "charts", ".tpl") + _walk(root / "config", ".yaml"):
        keys.update(re.findall(r"^\s*(control-plane):\s*\S", _read(path), re.M))
    return keys


def acko_crd_fields(root: Path) -> set[str]:
    """Every json tag name in the API package (name existence, not path shape)."""
    names: set[str] = set()
    for path in _walk(root / "api", ".go", skip=("_test.go",)):
        names.update(re.findall(r'json:"([A-Za-z0-9_]+)', _read(path)))
    return names


def ackoctl_flags(root: Path) -> set[str]:
    flags: set[str] = set()
    for path in _walk(root, ".go", skip=("_test.go",)):
        text = _read(path)
        flags.update(re.findall(r'Flags\(\)\.[A-Za-z]+VarP?\([^,]+,\s*"([a-z0-9-]+)"', text))
        flags.update(re.findall(r'PersistentFlags\(\)\.[A-Za-z]+VarP?\([^,]+,\s*"([a-z0-9-]+)"', text))
    # Cobra supplies these on every command.
    flags.update({"help", "version"})
    return flags


def py_constants(root: Path) -> set[str]:
    """Constants exported from the Rust extension AND from Python-level modules.

    Not everything lives in constants.rs: `exp.EXP_TYPE_*`, for instance, is
    defined in src/aerospike_py/exp.py. Reading only the Rust side reported
    every one of those as missing.
    """
    names = set(re.findall(r'm\.add\("([A-Z0-9_]+)"', _read(root / "rust/src/constants.rs")))
    for path in _walk(root / "src", ".py") + _walk(root / "src", ".pyi"):
        names.update(re.findall(r"^([A-Z][A-Z0-9_]{3,})\s*[:=]", _read(path), re.M))
    return names


def acm_routes(root: Path) -> set[str]:
    """Declared API paths, resolved through each router's prefix and both mounts.

    A route reads `@router.get("/clusters")` in a file whose router was built as
    `APIRouter(prefix="/k8s")`, and main.py mounts every router under both /api
    and /api/v1. Ignoring either layer makes real routes look nonexistent.
    """
    api = root / "api/src/aerospike_cluster_manager_api"
    paths: set[str] = set()
    for path in _walk(api, ".py", skip=("test_",)):
        text = _read(path)
        m = re.search(r'APIRouter\(\s*prefix\s*=\s*"([^"]*)"', text)
        prefix = m.group(1) if m else ""
        for route in re.findall(r'@(?:app|router)\.(?:get|post|put|delete|patch)\(\s*"([^"]+)"', text):
            paths.add(route if route.startswith("/api") else prefix + route)
    if not paths:
        return set()
    expanded = set(paths)
    for p in paths:
        if not p.startswith("/api"):
            for mount in ("/api", "/api/v1"):
                expanded.add(mount + p)
    return expanded


# --------------------------------------------------------------------------
# Claim extraction from skills/
# --------------------------------------------------------------------------

# Label keys that are legitimately not ACKO's own (Kubernetes built-ins and
# third-party operators the skills interact with).
EXTERNAL_LABEL_PREFIXES = (
    "kubernetes.io/",
    "node.kubernetes.io/",
    "topology.kubernetes.io/",
    "statefulset.kubernetes.io/",
    "batch.kubernetes.io/",
    "controller-revision-hash",
)

PLACEHOLDER = re.compile(r"^[<{$]|[>}]$|^\.\.\.$|^N$|^M$|^T$|^X$|^S$|^KEY$")


def _iter_skill_lines():
    for path in sorted(_walk(SKILLS_DIR, ".md")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        for i, line in enumerate(_read(path).splitlines(), 1):
            yield rel, i, line


def check_label_selectors(known: set[str], stats: Stats) -> list[Finding]:
    """`-l key=value` — a wrong key exits 0 with empty output, so nothing surfaces it."""
    out = []
    if not known:
        return out
    pat = re.compile(r"-l\s+([A-Za-z0-9][A-Za-z0-9./_-]*)=")
    for rel, ln, line in _iter_skill_lines():
        for key in pat.findall(line):
            if key.startswith(EXTERNAL_LABEL_PREFIXES) or PLACEHOLDER.match(key):
                continue
            stats.count("label-selector")
            if key not in known:
                out.append(Finding(rel, ln, "label-selector", key,
                                   "no such label key is set by the operator or its chart; "
                                   "a selector that matches nothing still exits 0"))
    return out


def check_condition_types(known: set[str], stats: Stats) -> list[Finding]:
    """`@.type=="X"` in a jsonpath — a wrong type yields empty output, not an error."""
    out = []
    if not known:
        return out
    pat = re.compile(r'@\.type\s*==\s*"([A-Za-z]+)"')
    for rel, ln, line in _iter_skill_lines():
        for cond in pat.findall(line):
            stats.count("condition-type")
            if cond not in known:
                out.append(Finding(rel, ln, "condition-type", cond,
                                   f"not a declared condition type; the set is {sorted(known)}"))
    return out


def check_phases(known: set[str], stats: Stats) -> list[Finding]:
    """`phase=X` / `phase: X` / `status.phase == "X"` in unambiguous positions only."""
    out = []
    if not known:
        return out
    pats = [
        re.compile(r"\bphase\s*=\s*[\"'`]?([A-Z][A-Za-z]+)"),
        re.compile(r"\bstatus\.phase\s*==\s*[\"']([A-Z][A-Za-z]+)"),
    ]
    for rel, ln, line in _iter_skill_lines():
        for pat in pats:
            for phase in pat.findall(line):
                stats.count("phase-name")
                if phase not in known:
                    out.append(Finding(rel, ln, "phase-name", phase,
                                       f"not in the AerospikePhase enum: {sorted(known)}"))
    return out


def check_ackoctl_flags(known: set[str], stats: Stats) -> list[Finding]:
    """Long flags on an `ackoctl` invocation — Cobra rejects an unknown flag outright."""
    out = []
    if not known:
        return out
    # Syntax-summary placeholders, not real flags.
    placeholders = {"flag", "flags", "option", "options", "opt", "args"}
    flag_pat = re.compile(r"--([a-z][a-z0-9-]+)")
    for rel, ln, line in _iter_skill_lines():
        if "ackoctl" not in line:
            continue
        # Ignore prose that merely mentions ackoctl alongside another tool.
        if re.search(r"\b(kubectl|helm|asinfo|asadm|curl)\b", line):
            continue
        # A shell comment is commentary, not an invocation — and is often
        # explaining that a flag does NOT exist, which would self-flag.
        if line.lstrip().startswith("#"):
            continue
        for flag in flag_pat.findall(line):
            if flag in placeholders:
                continue
            stats.count("ackoctl-flag")
            if flag not in known:
                out.append(Finding(rel, ln, "ackoctl-flag", "--" + flag,
                                   "not registered on any ackoctl command; Cobra rejects unknown flags"))
    return out


def check_py_constants(known: set[str], stats: Stats) -> list[Finding]:
    """Backticked `AEROSPIKE_*` / `POLICY_*` / `EXP_*` names must exist in constants.rs."""
    out = []
    if not known:
        return out
    prefixes = ("AEROSPIKE_", "POLICY_", "EXP_", "AUTH_", "SERIALIZER_", "LOG_LEVEL_")
    # AEROSPIKE_PY_* is the environment-variable namespace, not the constant one.
    env_prefixes = ("AEROSPIKE_PY_",)
    pat = re.compile(r"`([A-Z][A-Z0-9_]{3,})`")
    for rel, ln, line in _iter_skill_lines():
        for name in pat.findall(line):
            if not name.startswith(prefixes) or name.startswith(env_prefixes):
                continue
            stats.count("py-constant")
            if name not in known:
                out.append(Finding(rel, ln, "py-constant", name,
                                   "not exported by rust/src/constants.rs"))
    return out


def check_acm_routes(known: set[str], stats: Stats) -> list[Finding]:
    """`/api/...` paths must correspond to a declared route."""
    out = []
    if not known:
        return out
    pat = re.compile(r"`(/api/[A-Za-z0-9/_.-]*)`")
    # Compare with path parameters normalised: /clusters/{id} ~ /clusters/<id>.
    def norm(p: str) -> str:
        p = re.sub(r"\{[^}]+\}", "{}", p)
        p = re.sub(r"<[^>]+>", "{}", p)
        return p.rstrip("/")

    known_norm = {norm(k) for k in known}
    for rel, ln, line in _iter_skill_lines():
        for raw in pat.findall(line):
            if any(ch in raw for ch in "<>{}") or "..." in raw:
                continue  # templated/elided example, not a literal claim
            stats.count("acm-route")
            if norm(raw) not in known_norm:
                out.append(Finding(rel, ln, "acm-route", raw,
                                   "no such route is declared by the cluster-manager API"))
    return out


def check_event_reasons(known: set[str], stats: Stats) -> list[Finding]:
    """Event reasons in the first column of an "Event Reason" table.

    Scoped to that column rather than to any CamelCase token in prose: an event
    reason is shaped exactly like a condition type, a phase, or a Go identifier,
    so a free-text scan cannot tell them apart and would flag all of them.
    """
    out = []
    if not known:
        return out
    cell = re.compile(r"^\|\s*`([A-Za-z]+)`\s*\|")
    for path in sorted(_walk(SKILLS_DIR, ".md")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        in_event_table = False
        for ln, line in enumerate(_read(path).splitlines(), 1):
            if line.startswith("|"):
                head = line.split("|")[1].strip().lower() if line.count("|") > 1 else ""
                if "event reason" in head:
                    in_event_table = True
                    continue
            elif line.strip() == "" or line.startswith("#"):
                in_event_table = False
            if not in_event_table:
                continue
            m = cell.match(line)
            if not m:
                continue
            reason = m.group(1)
            stats.count("event-reason")
            if reason not in known:
                out.append(Finding(rel, ln, "event-reason", reason,
                                   "no such event reason is defined in internal/controller/events.go"))
    return out


def check_crd_fields(known: set[str], stats: Stats) -> list[Finding]:
    """Field NAMES in `spec.*` / `status.*` paths must exist as a json tag.

    Name existence only — this does not verify that the path nests correctly.
    It still catches the real-world failure mode (`status.operation` where the
    field is `status.operationStatus`).
    """
    out = []
    if not known:
        return out
    pat = re.compile(r"`\.?((?:spec|status)(?:\.[A-Za-z][A-Za-z0-9]*(?:\[[^\]]*\])?)+)`")
    for rel, ln, line in _iter_skill_lines():
        for path_expr in pat.findall(line):
            # Drop jsonpath filter expressions first — `[?(@.type=="X")]` contains
            # dots of its own and would otherwise be split into bogus segments.
            cleaned = re.sub(r"\[\?\(.*?\)\]", "", path_expr)
            segments = [re.sub(r"\[.*?\]", "", s) for s in cleaned.split(".")[1:]]
            for seg in segments:
                if not seg or PLACEHOLDER.match(seg):
                    continue
                stats.count("crd-field")
                if seg not in known:
                    out.append(Finding(rel, ln, "crd-field", f"{path_expr} → '{seg}'",
                                       "no such json tag exists anywhere in the CRD API package"))
    return out


# --------------------------------------------------------------------------
# Coverage
# --------------------------------------------------------------------------

COVERAGE = """\
COVERAGE — what this checker does and does not verify

  Verified (each resolves to a closed, enumerable set in source):
    label-selector   `-l key=` against the operator's label constants + chart
    condition-type   `@.type=="X"` against the Condition* constants
    phase-name       `phase=X` against the AerospikePhase kubebuilder enum
    event-reason     first column of an "Event Reason" table against events.go
    crd-field        names in `spec.*`/`status.*` against CRD json tags
    ackoctl-flag     `--flag` on an ackoctl line against Cobra registrations
    py-constant      backticked AEROSPIKE_*/POLICY_*/EXP_*/AUTH_* against
                     constants.rs plus the Python-level modules
    acm-route        `/api/...` against cluster-manager routes, resolved through
                     each APIRouter prefix and both the /api and /api/v1 mounts

  NOT verified — these still need human review:
    - Webhook error strings. Tried and removed: Go assembles them from format
      verbs and concatenated literals, so the documented rendering is not a
      substring of anything in source. 19 of 29 reports were false. The manual
      audit did find 11 genuinely wrong strings here, so the risk is real — it
      simply is not mechanically checkable at acceptable precision.
    - Default VALUES (`max_retries` = 2 vs 5). They live in a dependency crate
      and in per-policy override builders; a wrong guess is worse than no check.
    - Whether a documented rule is actually IMPLEMENTED. "Rack IDs cannot be
      changed" names real fields in fluent English; only reading ValidateUpdate
      shows the webhook never enforced it. This class caused the worst finding
      in the audit and no extractor can catch it.
    - Prose semantics, procedure ordering, and whether the advice is good.
    - CRD path SHAPE. crd-field checks that each name exists somewhere in the
      API package, not that the nesting is correct.
    - aerospike-py's Python API surface beyond constants; Helm values; metric
      names; Ginkgo/pytest specifics.

  Honest denominator: the drift audit that motivated this checker examined
  ~1,770 claims. The categories above cover roughly a fifth of that population,
  and they are deliberately the fifth where a wrong claim fails SILENTLY — a bad
  label selector or condition type exits 0 and prints nothing, so no human ever
  sees an error. A green run means "these claim kinds agree with the pinned
  SHAs". It does NOT mean the skills are correct.
"""


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------


def load_lock() -> list[tuple[str, str, str]]:
    entries = []
    for raw in _read(LOCK_FILE).splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 3:
            print(f"warning: malformed sources.lock line: {raw}", file=sys.stderr)
            continue
        entries.append((parts[0], parts[1], parts[2]))
    return entries


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sources", type=Path, help="directory holding one checkout per source repo")
    ap.add_argument("--format", choices=("text", "github", "json"), default="text")
    ap.add_argument("--coverage", action="store_true", help="print coverage notes and exit")
    ap.add_argument("--report", action="store_true", default=True, help=argparse.SUPPRESS)
    args = ap.parse_args()

    if args.coverage:
        print(COVERAGE)
        return 0

    if not args.sources:
        print("error: --sources is required (or use --coverage)", file=sys.stderr)
        return 2
    if not SKILLS_DIR.is_dir():
        print(f"error: no skills/ directory at {SKILLS_DIR}", file=sys.stderr)
        return 2

    locked = {name: sha for name, _url, sha in load_lock()}
    roots = {name: args.sources / name for name in locked}

    missing = [n for n, p in roots.items() if not p.is_dir()]
    if missing:
        print(f"error: missing checkouts under {args.sources}: {', '.join(missing)}", file=sys.stderr)
        print("hint: scripts/fetch_sources.sh clones every repo in sources.lock at its pinned SHA", file=sys.stderr)
        return 2

    stats = Stats()
    findings: list[Finding] = []
    skipped: list[str] = []

    def run(label, extractor, checker, repo):
        known = extractor(roots[repo])
        if not known:
            skipped.append(f"{label} (extractor found nothing in {repo}; source layout may have changed)")
            return
        findings.extend(checker(known, stats))

    run("label-selector", acko_label_keys, check_label_selectors, ACKO)
    run("condition-type", acko_conditions, check_condition_types, ACKO)
    run("phase-name", acko_phases, check_phases, ACKO)
    run("event-reason", acko_event_reasons, check_event_reasons, ACKO)
    run("crd-field", acko_crd_fields, check_crd_fields, ACKO)
    run("ackoctl-flag", ackoctl_flags, check_ackoctl_flags, ACKOCTL)
    run("py-constant", py_constants, check_py_constants, PY)
    run("acm-route", acm_routes, check_acm_routes, ACM)

    if args.format == "json":
        print(json.dumps({
            "checked": stats.checked,
            "by_category": dict(stats.by_category),
            "skipped_checks": skipped,
            "pinned": locked,
            "findings": [f.__dict__ for f in findings],
        }, indent=2))
        return 1 if findings else 0

    if args.format == "github":
        for f in findings:
            print(f.format_github())

    print()
    print(f"Verified {stats.checked} claims against pinned source checkouts.")
    for cat in sorted(stats.by_category):
        print(f"  {cat:<24} {stats.by_category[cat]:>5}")
    print()
    for name, sha in sorted(locked.items()):
        print(f"  pinned {name:<34} {sha[:12]}")
    if skipped:
        print()
        print("SKIPPED (not counted as passing):")
        for s in skipped:
            print(f"  - {s}")
    print()

    if findings:
        print(f"FAILED — {len(findings)} claim(s) do not match source:\n")
        if args.format == "text":
            for f in findings:
                print(f.format_text())
                print()
        print("Each is a claim the skills assert and the pinned source contradicts.")
        print("Fix the skill, or bump the SHA in scripts/sources.lock if upstream moved.")
        return 1

    print("OK — every claim in the covered categories matches the pinned sources.")
    print("Run with --coverage to see what this does NOT check.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
