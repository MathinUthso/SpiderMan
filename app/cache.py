"""In-memory interpretation cache keyed by notes + battery. Judge retries cost zero LLM calls."""

from __future__ import annotations

import hashlib
import json
from collections import OrderedDict

_MAX = 512
_store: "OrderedDict[str, list[dict]]" = OrderedDict()


def _key(notes: list[str], battery: dict) -> str:
    payload = json.dumps({"n": notes, "b": battery}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def get(notes: list[str], battery: dict) -> list[dict] | None:
    k = _key(notes, battery)
    v = _store.get(k)
    if v is not None:
        _store.move_to_end(k)
    return None if v is None else [dict(d) for d in v]


def put(notes: list[str], battery: dict, directives: list[dict]) -> None:
    k = _key(notes, battery)
    _store[k] = [dict(d) for d in directives]
    _store.move_to_end(k)
    while len(_store) > _MAX:
        _store.popitem(last=False)
