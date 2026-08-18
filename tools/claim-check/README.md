# claim-check

Verifies factual claims in `skills/` against the source repositories those
skills document. Runs in CI on every PR and blocks merge on a failure.

```bash
# clone the pinned refs and check everything
python3 tools/claim-check/check_claims.py

# reuse checkouts you already have
CLAIM_CHECK_SRC_ACKO=~/src/aerospike-ce-kubernetes-operator \
CLAIM_CHECK_SRC_AEROSPIKE_PY=~/src/aerospike-py \
CLAIM_CHECK_SRC_ACKOCTL=~/src/ackoctl \
  python3 tools/claim-check/check_claims.py --offline --coverage

# one rule at a time while you are fixing something
python3 tools/claim-check/check_claims.py --rule acko-error-strings
```

Requires Python 3.10+ and PyYAML. Exit status is 1 when any claim fails.

## What it actually proves — read this before trusting a green run

**It is syntactic.** Each rule asks "does this string appear where it would
have to appear if the claim were true". That catches renames, typos, and
identifiers that never existed. It does not compile anything, does not run the
operator, and cannot tell you whether a documented *procedure* works.

A green run means: the identifiers, error strings, CRD paths, constant values,
CLI verbs and flags that the rules extract all still exist in source at the
pinned refs. It does not mean the skills are correct.

**Coverage is partial, and the tool tells you how partial.** `--coverage`
prints how many claims the rules extracted against the total number of
backticked spans across `skills/`. The current figure is around 27%. That
denominator is deliberately unflattering — it counts every backticked span,
including prose emphasis and shell fragments that are not factual claims at
all — so the real proportion of *claims* covered is higher than the number
shown. Treat it as a floor.

**What is definitely not covered:**

- Prose. "Removing a key always forces a rolling restart" is a claim about
  behaviour with no identifier to match; nothing here checks it.
- Semantics of any kind: argument order, whether an example would run,
  whether a documented default is the one a user actually gets after the
  wrapper layer has had its say.
- Whether a command that exists does what the docs say it does.
- Anything in the three source repos that the skills *should* document but
  don't. This finds wrong claims, never missing ones.

Every past defect class this tool would have caught is listed at the bottom.
Anything not on that list, it would have missed.

**A false positive is worse than a miss.** Reporting correct documentation as
drift costs a reviewer's time and, repeated, teaches everyone to skim past the
check — after which it may as well not exist. Three rules carry extra logic for
exactly this reason, and the same care applies to any rule you add:

- `acko-helm-values` attributes each `--set` to the chart of the enclosing
  `helm install`. A page that installs cert-manager first has `--set
  crds.enabled=true` on it, which is a real cert-manager value and absent from
  ACKO's chart.
- `ackoctl-flags` skips comment lines inside code fences, because a comment
  saying a flag does *not* exist would otherwise be read as a claim that it
  does.
- `acko-event-reasons` and friends read markdown *data* rows only, never the
  header — otherwise "Phase" and "Type" get checked as if they were claims.

When a rule fires on something correct, fix the rule. Do not add the claim to
`ignore` unless it is genuinely unverifiable, and say why in a comment.

## Rules

| id | source | what it checks |
|---|---|---|
| `acko-error-strings` | operator | Every quoted webhook message in the reference catalog, run by run, against Go string literals |
| `acko-crd-paths` | operator | `spec.*` / `status.*` paths resolve in the generated CRD schema |
| `acko-event-reasons` | operator | Event reasons are defined in `internal/controller/events.go` |
| `acko-phases` | operator | Phase names are `AerospikePhase` constants |
| `acko-conditions` | operator | Condition types, by value or by Go constant name |
| `acko-dynamic-params` | operator | Params documented `Dynamic=Yes` are in `dynamic_params.go` |
| `acko-helm-values` | operator | `--set key=` keys exist in the chart's `values.yaml` |
| `acko-label-keys` | operator | `acko.io/…` and `aerospike.io/…` keys exist in operator source |
| `apy-constant-values` | aerospike-py | Constant **name and value** match what PyO3 registers |
| `apy-constant-names` | aerospike-py | Referenced constants are registered on the module |
| `apy-client-methods` | aerospike-py | `client.foo(...)` exists on `Client`/`AsyncClient` in the stubs |
| `apy-exceptions` | aerospike-py | Exception classes are defined |
| `ackoctl-commands` | ackoctl | `ackoctl <noun> <verb>` resolves in the cobra command tree |
| `ackoctl-flags` | ackoctl | Long flags in `ackoctl` invocations are registered |

## Pinned refs

`sources.json` pins the commit of each source repo. **Bumping a ref is a
claim**: it says the skills were checked against that commit and passed. Bump
it only alongside a passing run, never as routine maintenance — a ref moved
forward without a check turns this tool into decoration.

## Adding a rule

A rule is an extractor plus a verifier. The extractor pulls candidate claims
out of markdown; the verifier decides whether an index confirms one.

1. Add whatever index the verifier needs to `indexes.py`.
2. Add the `Rule(...)` to `RULES` in `rules.py`.
3. **Add a case to `CASES` in `selftest.py`** — one claim that must verify and
   one that must not. `selftest.py` fails if any rule lacks a case, because a
   verifier that returns `True` for everything looks exactly like a passing
   rule, which is the failure mode this whole tool exists to prevent.

Run `python3 tools/claim-check/selftest.py` before opening the PR.

## Placeholder convention

Error-message rules split a documented message on placeholder tokens and
require each remaining literal run of 12+ characters to appear in source. The
placeholders are `N M T S KEY MIN ID FIELD v i j k`, anything in quotes,
`<angle brackets>`, `...`, and bare digits. This mirrors the convention
documented at the top of
`skills/acko-operations/reference/validation-rules.md`; if you change one,
change the other.

## Defect classes this would have caught

From the drift audit in issue #97, with the rule that catches each:

- `aerospike.io/cr-name` — a label selector that never existed, in 12 places
  (`acko-label-keys`)
- Five more never-existed identifiers (`acko-event-reasons`,
  `acko-crd-paths`, `ackoctl-commands`)
- `k8s pod logs` → `k8s cluster logs`, and `udf register` → `udf upload`
  (`ackoctl-commands`)
- `--namespace`/`--set` → `--name`/`--param` on `configure-namespace`
  (`ackoctl-flags`)
- The phantom `DynamicConfigRecovered` event (`acko-event-reasons`)
- `max-record-size` / `evict-used-pct` / `evict-tenths-pct` documented as
  dynamic (`acko-dynamic-params`)
- Webhook error strings that are not substrings of the real message
  (`acko-error-strings`)

It would **not** have caught the FastAPI `JSONResponse` argument-order bug,
the reversed NumPy `key_field` round-trip, or the no-op `ping()` tuning knobs.
Those are semantic, and they need a human or a test.
