#!/usr/bin/env python3
"""Verify factual claims in the skills against the source repos they document.

    python3 tools/claim-check/check_claims.py            # clone pinned refs, check
    python3 tools/claim-check/check_claims.py --coverage # add the coverage report
    python3 tools/claim-check/check_claims.py --json     # machine-readable

Exit status is 1 if any claim fails, 0 otherwise. A rule whose source repo is
unavailable is reported as SKIPPED and does **not** pass silently -- with
--strict, an unavailable source is an error instead.

What this does and does not prove is documented in README.md next to this file.
Read it before trusting a green run.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent

sys.path.insert(0, str(HERE))

import indexes  # noqa: E402
import rules as rulesmod  # noqa: E402


def resolve_checkouts(config: dict, cache: Path, offline: bool) -> dict[str, Path]:
    """Return {source key: checkout path}, cloning pinned refs when needed."""
    out: dict[str, Path] = {}
    for key, spec in config["sources"].items():
        override = os.environ.get(f"CLAIM_CHECK_SRC_{key.upper()}")
        if override:
            path = Path(override).expanduser().resolve()
            if path.is_dir():
                out[key] = path
                continue
            print(f"warning: CLAIM_CHECK_SRC_{key.upper()}={path} is not a directory",
                  file=sys.stderr)
        if offline:
            continue
        dest = cache / key
        try:
            if not dest.exists():
                subprocess.run(
                    ["git", "clone", "--quiet", "--filter=blob:none",
                     spec["repo"], str(dest)],
                    check=True, capture_output=True,
                )
            subprocess.run(["git", "-C", str(dest), "fetch", "--quiet", "origin",
                            spec["ref"]], check=False, capture_output=True)
            subprocess.run(["git", "-C", str(dest), "checkout", "--quiet",
                            spec["ref"]], check=True, capture_output=True)
            out[key] = dest
        except (subprocess.CalledProcessError, OSError) as exc:
            print(f"warning: could not prepare {key} at {spec['ref']}: {exc}",
                  file=sys.stderr)
    return out


def iter_files(globs: tuple[str, ...]) -> list[Path]:
    seen: dict[Path, None] = {}
    for g in globs:
        for p in sorted(REPO.glob(g)):
            if p.is_file():
                seen.setdefault(p, None)
    return list(seen)


def run(sources, only: str | None):
    results = []
    for rule in rulesmod.RULES:
        if only and rule.id != only:
            continue
        index = sources.get(rule.source)
        entry = {
            "rule": rule.id,
            "description": rule.description,
            "source": rule.source,
            "status": "ok",
            "checked": 0,
            "skipped": 0,
            "failures": [],
        }
        if index is None:
            entry["status"] = "skipped-no-source"
            results.append(entry)
            continue

        for path in iter_files(rule.globs):
            rel = path.relative_to(REPO).as_posix()
            text = path.read_text(errors="replace")
            for line_no, claim, detail in rule.extract(text):
                if claim in rule.ignore:
                    entry["skipped"] += 1
                    continue
                if rule.id == "acko-error-strings" and not rulesmod._checkable_message(claim):
                    entry["skipped"] += 1
                    continue
                entry["checked"] += 1
                try:
                    ok = rule.verify(index, claim)
                except Exception as exc:  # a broken rule must not look like a pass
                    entry["status"] = "error"
                    entry["failures"].append(
                        {"file": rel, "line": line_no, "claim": claim,
                         "detail": f"rule raised {exc!r}"}
                    )
                    continue
                if not ok:
                    entry["failures"].append(
                        {"file": rel, "line": line_no, "claim": claim,
                         "detail": detail}
                    )
        if entry["failures"] and entry["status"] == "ok":
            entry["status"] = "failed"
        results.append(entry)
    return results


def coverage_report() -> dict:
    """How much of the skills' backticked content any rule even looks at.

    This is the honest denominator: total backticked spans across every skill
    file, versus the spans some rule extracted. It intentionally over-counts the
    denominator -- plenty of backticked text is prose formatting, not a claim --
    so treat the percentage as a floor on coverage, not a grade.
    """
    import re

    total = 0
    per_file: dict[str, int] = {}
    for p in sorted((REPO / "skills").rglob("*.md")):
        n = len(re.findall(r"`[^`\n]+`", p.read_text(errors="replace")))
        total += n
        per_file[p.relative_to(REPO).as_posix()] = n
    return {"backticked_spans_total": total, "per_file": per_file}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="emit JSON")
    ap.add_argument("--coverage", action="store_true",
                    help="also report how much of the skills the rules look at")
    ap.add_argument("--offline", action="store_true",
                    help="never clone; use CLAIM_CHECK_SRC_* checkouts only")
    ap.add_argument("--strict", action="store_true",
                    help="treat an unavailable source repo as a failure")
    ap.add_argument("--rule", help="run a single rule by id")
    ap.add_argument("--cache", default=os.environ.get("CLAIM_CHECK_CACHE"),
                    help="directory to clone source repos into")
    args = ap.parse_args()

    config = json.loads((HERE / "sources.json").read_text())

    tmp = None
    if args.cache:
        cache = Path(args.cache).expanduser()
        cache.mkdir(parents=True, exist_ok=True)
    else:
        tmp = tempfile.TemporaryDirectory(prefix="claim-check-")
        cache = Path(tmp.name)

    try:
        checkouts = resolve_checkouts(config, cache, args.offline)
        sources = indexes.load_sources(HERE / "sources.json", checkouts)
        results = run(sources, args.rule)
    finally:
        if tmp is not None:
            tmp.cleanup()

    checked = sum(r["checked"] for r in results)
    skipped = sum(r["skipped"] for r in results)
    failed = sum(len(r["failures"]) for r in results)
    no_source = [r["rule"] for r in results if r["status"] == "skipped-no-source"]

    payload = {
        "refs": {k: v["ref"] for k, v in config["sources"].items()},
        "sources_available": sorted(sources),
        "totals": {"checked": checked, "skipped": skipped, "failed": failed},
        "rules": results,
    }
    if args.coverage:
        payload["coverage"] = coverage_report()
        payload["coverage"]["claims_extracted"] = checked + skipped

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"claim-check — {checked} claims checked, {failed} failed, "
              f"{skipped} skipped as unverifiable\n")
        for r in results:
            mark = {"ok": "PASS", "failed": "FAIL", "error": "ERROR",
                    "skipped-no-source": "SKIP"}[r["status"]]
            print(f"[{mark}] {r['rule']:<24} {r['checked']:>4} checked  "
                  f"{len(r['failures']):>3} failed   ({r['source']})")
            for f in r["failures"]:
                extra = f" — {f['detail']}" if f["detail"] else ""
                print(f"         {f['file']}:{f['line']}: {f['claim']}{extra}")
        if no_source:
            print(f"\nno source checkout for: {', '.join(no_source)}")
        if args.coverage:
            cov = payload["coverage"]
            spans = cov["backticked_spans_total"]
            pct = 100.0 * (checked + skipped) / spans if spans else 0.0
            print(f"\ncoverage: {checked + skipped} claims extracted from "
                  f"{spans} backticked spans across skills/ ({pct:.1f}%).")
            print("That percentage is a floor, not a grade: the denominator "
                  "counts every backticked span,\nincluding prose formatting "
                  "that is not a factual claim at all. See README.md.")

    if failed:
        return 1
    if args.strict and no_source:
        return 1
    if any(r["status"] == "error" for r in results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
