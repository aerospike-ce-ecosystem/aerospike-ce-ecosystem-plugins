# Health Check Reference

## Table of Contents
- [`ping()` — round-trip health probe](#ping--round-trip-health-probe)
- [Liveness vs Readiness in Kubernetes](#liveness-vs-readiness-in-kubernetes)
- [Comparison with `get_node_names()` and `is_connected()`](#comparison-with-get_node_names-and-is_connected)

---

## `ping()` — round-trip health probe

```python
ok: bool = client.ping()                  # sync
ok: bool = await async_client.ping()      # async
```

Sends `info("build")` to a randomly selected cluster node. Returns `True` on success, `False` on any failure (timeout, connection refused, parse error, etc.). **Never raises** — safe to call from a health-check handler without try/except.

Both sync and async clients implement `ping()`. The async variant is awaitable; the sync variant blocks.

### What it actually validates

- TCP connection to a cluster node is established (or can be re-established).
- Cluster tend has discovered at least one node.
- The selected node responds to a basic info request within client policy timeouts.

It does NOT validate per-namespace state (e.g., a namespace stuck in `dead-partitions`). For deeper checks, use `client.info_random_node("namespace/<ns>")` or `client.info_all("namespace/<ns>")` and parse the response.

---

## Liveness vs Readiness in Kubernetes

Use `ping()` for **readiness**, not liveness:

| Probe | Recommended | Why |
|-------|-------------|-----|
| **Readiness** | `await client.ping()` | If the cluster is unreachable, take this pod out of the Service so traffic shifts to healthy peers. |
| **Liveness**  | A trivial `200 OK` from the HTTP server | A failed liveness probe restarts the pod. You typically don't want to restart your app process just because Aerospike blipped — that won't fix the database. |

### FastAPI readiness example

For the `client.ping()`-driven `/health/ready` route (with `Depends(get_client)` and the `JSONResponse(status_code=503, …)` unhealthy path) and the matching K8s `readinessProbe` / `livenessProbe` manifest snippet, see the `aerospike-py-fastapi` skill — it carries the same pattern with the rest of the FastAPI wiring.

---

## Comparison with `get_node_names()` and `is_connected()`

`get_node_names()` returns the locally cached list of cluster nodes from the most recent tend cycle. It does not perform any network I/O at call time and always returns synchronously, even on `AsyncClient`.

| | `ping()` | `get_node_names()` |
|---|---|---|
| Network I/O at call time | yes (info round-trip) | no (cache lookup) |
| Returns | `bool` | `list[str]` |
| Sync or async | matches client | always sync |
| Raises on failure | no (returns `False`) | no (returns possibly stale list) |
| Good for | readiness probe | introspection, metrics labels |

`is_connected()` reports whether the client currently holds an active cluster connection — again a local check with no network I/O — and the sync and async clients do not implement it the same way:

| | what it checks |
|---|---|
| `Client.is_connected()` | state is `CONNECTED` **and** `aerospike-core` reports a non-empty node list on an unclosed cluster (`rust/src/client.rs:144-151`) |
| `AsyncClient.is_connected()` | state is `CONNECTED` **and** an inner client exists — no cluster check at all (`rust/src/async_client.rs:225-228`) |

If the cluster has gone fully unreachable but the tend interval has not yet elapsed, `get_node_names()` may still return a non-empty list — making it unsuitable as a health check on its own. `is_connected()` shares that limitation. Use `ping()` for readiness; use `is_connected()` only to avoid operating on a client that was never connected or has been closed.

---

## Tuning timeouts

**`ping()` is not tunable.** `do_ping` (`rust/src/client_ops.rs:525-532`) picks a random node and calls `node.info(&AdminPolicy::default(), &["build"])` — the policy is constructed inline, so neither `operation_queue_timeout_ms` nor any `total_timeout` policy reaches it, and no limiter permit is acquired. Its bound is the `AdminPolicy` default: the field is `0`, which `AdminPolicy::timeout()` substitutes with **3000 ms**.

Size readiness probes around that 3 s ceiling rather than trying to shorten it — `periodSeconds: 5` with a `timeoutSeconds` above 3 gives the client room to ride out a transient blip without flapping out of the Service. To bound probe latency more tightly than 3 s, use a real read against a known key instead of `ping()`.
