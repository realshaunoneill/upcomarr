"""Tag filters, resolved from labels to ids.

A filter fails closed: if a configured label does not exist, the source fails with
`tag_not_found` rather than quietly publishing everything.
"""

from __future__ import annotations

from .http import Client, FetchError


def resolve(client: Client, api: str, labels: tuple[str, ...]) -> frozenset[int] | None:
    if not labels:
        return None
    raw = client.get_json(f"/api/{api}/tag")
    if not isinstance(raw, list):
        raise FetchError("bad_shape")
    by_label = {}
    for tag in raw:
        if isinstance(tag, dict) and isinstance(tag.get("label"), str):
            tag_id = tag.get("id")
            if isinstance(tag_id, int) and not isinstance(tag_id, bool):
                by_label[tag["label"].strip().lower()] = tag_id
    missing = [label for label in labels if label not in by_label]
    if missing:
        raise FetchError("tag_not_found")
    return frozenset(by_label[label] for label in labels)
