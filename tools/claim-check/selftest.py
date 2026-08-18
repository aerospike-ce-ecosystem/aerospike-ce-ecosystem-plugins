#!/usr/bin/env python3
"""Self-test for the claim checker.

A verifier that returns True for everything passes silently and looks green
forever — the same failure mode as the drift it exists to catch. These tests
feed each rule a claim that is known-good and a claim that is known-bad,
against real source checkouts, and assert it separates them.

Run it the same way as the checker:

    CLAIM_CHECK_SRC_ACKO=… CLAIM_CHECK_SRC_AEROSPIKE_PY=… CLAIM_CHECK_SRC_ACKOCTL=… \
        python3 tools/claim-check/selftest.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import check_claims  # noqa: E402
import indexes  # noqa: E402
import rules as rulesmod  # noqa: E402

# (rule id, a claim that must verify, a claim that must NOT verify)
CASES = [
    ("acko-error-strings",
     "spec.size N exceeds CE maximum of 8",
     "spec.size N exceeds the community edition limit of 8"),
    ("acko-crd-paths", "spec.rackConfig.racks", "spec.rackConfiguration.racks"),
    ("acko-event-reasons", "RollingRestartStarted", "RollingRestartBegun"),
    ("acko-phases", "WaitingForMigration", "WaitingOnMigration"),
    ("acko-conditions", "ConditionReconcileHealthy", "ConditionReconcileHappy"),
    ("acko-dynamic-params", "proto-fd-max", "max-record-size"),
    ("acko-helm-values", "crds.install", "crds.enabled"),
    ("acko-label-keys", "acko.io/rack", "aerospike.io/cr-name"),
    ("apy-constant-values", "POLICY_KEY_SEND=1", "POLICY_KEY_SEND=7"),
    ("apy-constant-names", "POLICY_KEY_SEND", "POLICY_KEY_TRANSMIT"),
    ("apy-client-methods", "batch_read", "batch_fetch"),
    ("apy-exceptions", "RecordNotFound", "RecordVanishedError"),
    ("ackoctl-commands", "k8s cluster logs", "k8s pod logs"),
    ("ackoctl-flags", "allow-write", "allow-writes"),
]


def main() -> int:
    import contextlib
    import os

    config = check_claims.json.loads((HERE / "sources.json").read_text())
    cache_env = os.environ.get("CLAIM_CHECK_CACHE")
    if cache_env:
        cache_ctx = contextlib.nullcontext(cache_env)
        Path(cache_env).mkdir(parents=True, exist_ok=True)
    else:
        cache_ctx = tempfile.TemporaryDirectory(prefix="claim-selftest-")
    with cache_ctx as tmp:
        checkouts = check_claims.resolve_checkouts(config, Path(tmp), offline=False)
        sources = indexes.load_sources(HERE / "sources.json", checkouts)

        by_id = {r.id: r for r in rulesmod.RULES}
        failures = []
        skipped = []
        for rule_id, good, bad in CASES:
            rule = by_id.get(rule_id)
            if rule is None:
                failures.append(f"{rule_id}: no such rule")
                continue
            index = sources.get(rule.source)
            if index is None:
                skipped.append(rule_id)
                continue
            if not rule.verify(index, good):
                failures.append(f"{rule_id}: rejected a true claim {good!r}")
            if rule.verify(index, bad):
                failures.append(f"{rule_id}: accepted a false claim {bad!r}")

    covered = {c[0] for c in CASES}
    uncovered = sorted({r.id for r in rulesmod.RULES} - covered)
    if uncovered:
        failures.append(
            "rules with no self-test case: " + ", ".join(uncovered)
            + " — add one to CASES before merging the rule"
        )

    for f in failures:
        print(f"FAIL {f}")
    if skipped:
        print(f"skipped (no source checkout): {', '.join(sorted(set(skipped)))}")
    if failures:
        return 1
    print(f"selftest: {len(CASES) - len(set(skipped))} rules verified "
          f"positive and negative")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
