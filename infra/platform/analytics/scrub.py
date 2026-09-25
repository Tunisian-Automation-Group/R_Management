"""Firehose transform for the analytics lake (P-6): only what analytics needs
leaves the event, and nothing that says who someone is.

An allowlist, not a denylist: a field added to an event later stays out of the
two-year lake until someone decides it belongs there. Ids are pseudonymous
(Cognito subs, booking ids) and are what account deletion keys on; names,
emails, addresses, VAT ids, titles and free text never arrive.
"""

from __future__ import annotations

import base64
import json

TOP = ("id", "type", "source", "occurredAt")
FIELDS = frozenset(
    {
        "from", "to", "by", "amount", "currency", "refundAmount", "noShow", "windowStart", "windowEnd",
        "expiresAt", "change", "rating", "quality", "reason", "targetType", "decision", "category",
        "district", "ready", "status", "cancellationRate", "mode", "hours",
    }
)  # fmt: skip


def keep(event: dict) -> dict:
    data = event.get("data") or {}
    safe = {
        k: v
        for k, v in data.items()
        if (k.endswith("Id") or k in FIELDS) and (v is None or isinstance(v, (str, int, float, bool)))
    }
    return {**{k: event[k] for k in TOP if k in event}, "data": safe}


def handler(event: dict, _context: object) -> dict:
    out = []
    for r in event["records"]:
        try:
            clean = keep(json.loads(base64.b64decode(r["data"])))
            data = base64.b64encode((json.dumps(clean, separators=(",", ":")) + "\n").encode()).decode()
            out.append({"recordId": r["recordId"], "result": "Ok", "data": data})
        except (ValueError, KeyError, TypeError):
            # Not an event we understand: never store it raw.
            out.append({"recordId": r["recordId"], "result": "Dropped", "data": r["data"]})
    return {"records": out}


if __name__ == "__main__":
    ev = {
        "id": "ev_1",
        "type": "moderation.report_received",
        "source": "catalog",
        "occurredAt": "2026-09-26T10:00:00Z",
        "trace": {"traceparent": "x"},
        "data": {
            "reportId": "rp_1", "reporterId": None, "reporterEmail": "ana@example.com", "targetType": "listing",
            "ownerName": "Ana", "ownerBusiness": {"vatId": "DE123456789"}, "title": "Ana's saw", "amount": 2300,
        },
    }  # fmt: skip
    got = keep(ev)
    assert got["data"] == {"reportId": "rp_1", "reporterId": None, "targetType": "listing", "amount": 2300}, got
    assert "trace" not in got and got["type"] == ev["type"]
    rec = {"recordId": "1", "data": base64.b64encode(json.dumps(ev).encode()).decode()}
    res = handler({"records": [rec, {"recordId": "2", "data": base64.b64encode(b"not json").decode()}]}, None)
    assert [r["result"] for r in res["records"]] == ["Ok", "Dropped"]
    assert b"example.com" not in base64.b64decode(res["records"][0]["data"])
    print("scrub ok")
