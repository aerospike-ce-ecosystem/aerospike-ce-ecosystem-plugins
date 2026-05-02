"""Parse the OTel collector debug exporter's stdout into Span objects.

The debug exporter prints spans in a fixed line-oriented format. We could
shell-out to grep+awk (the previous bash version did), but parsing into
typed dicts lets the test assert "trace X has both a fastapi server span
and an asyncpg child" without awk magic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Span:
    trace_id: str
    span_id: str
    parent_id: str  # empty string for root spans
    name: str
    kind: str  # Server / Client / Internal / Producer / Consumer / Unspecified
    scope: str  # InstrumentationScope name
    attrs: dict[str, str] = field(default_factory=dict)


# The collector prints span metadata in a format like:
#   InstrumentationScope opentelemetry.instrumentation.fastapi 0.62b1
#   Span #0
#       Trace ID       : 028eb416932a7f9a2383f33d04a9ed06
#       Parent ID      : 99617de8b0982756
#       ID             : 6e2369a389694173
#       Name           : GET /api/v1/connections http send
#       Kind           : Internal
#       ...
#   Attributes:
#        -> http.method: Str(GET)
#        -> http.route: Str(/api/v1/connections)

_SCOPE_RE = re.compile(r"^InstrumentationScope (\S+)")
_SPAN_HEAD_RE = re.compile(r"^Span #\d+")
_FIELD_RE = re.compile(r"^\s+(\w[\w ]*?)\s*:\s*(.*)$")
_ATTR_RE = re.compile(r"^\s*->\s*([\w\.]+):\s*(?:Str|Int|Bool|Double)?\(?(.*?)\)?\s*$")


def parse_collector_log(text: str) -> list[Span]:
    """Return all Spans found in `kubectl logs deploy/otel-collector` output."""
    spans: list[Span] = []
    scope = ""
    cur: dict | None = None
    in_attrs = False

    def flush():
        nonlocal cur
        if cur is not None and cur.get("trace_id"):
            spans.append(
                Span(
                    trace_id=cur.get("trace_id", ""),
                    span_id=cur.get("id", ""),
                    parent_id=cur.get("parent_id", ""),
                    name=cur.get("name", ""),
                    kind=cur.get("kind", ""),
                    scope=scope,
                    attrs=cur.get("attrs", {}),
                )
            )
        cur = None

    for line in text.splitlines():
        m = _SCOPE_RE.match(line)
        if m:
            flush()
            scope = m.group(1)
            in_attrs = False
            continue

        if _SPAN_HEAD_RE.match(line):
            flush()
            cur = {"attrs": {}}
            in_attrs = False
            continue

        if cur is None:
            continue

        if line.strip().startswith("Attributes"):
            in_attrs = True
            continue

        if in_attrs:
            m_attr = _ATTR_RE.match(line)
            if m_attr:
                k, v = m_attr.groups()
                cur["attrs"][k] = v
            elif line.strip() == "":
                # Blank line ends this span block
                flush()
                in_attrs = False
            continue

        m_field = _FIELD_RE.match(line)
        if not m_field:
            continue
        key, val = m_field.groups()
        key_n = key.strip().lower().replace(" ", "_")
        if key_n == "trace_id":
            cur["trace_id"] = val.strip()
        elif key_n == "id":
            cur["id"] = val.strip()
        elif key_n == "parent_id":
            cur["parent_id"] = val.strip()
        elif key_n == "name":
            cur["name"] = val.strip()
        elif key_n == "kind":
            cur["kind"] = val.strip()

    flush()
    return spans


def by_trace(spans: list[Span]) -> dict[str, list[Span]]:
    out: dict[str, list[Span]] = {}
    for s in spans:
        out.setdefault(s.trace_id, []).append(s)
    return out


def find_correlated_traces(spans: list[Span]) -> list[str]:
    """Trace IDs that contain BOTH a fastapi-server span AND an asyncpg span.

    This is the cluster-manager #265 contract: HTTP request span must parent
    asyncpg child spans, proving in-process trace context propagation.
    """
    out = []
    for tid, group in by_trace(spans).items():
        has_http_server = any("fastapi" in s.scope and s.kind == "Server" for s in group)
        has_db_client = any("asyncpg" in s.scope for s in group)
        if has_http_server and has_db_client:
            out.append(tid)
    return out
