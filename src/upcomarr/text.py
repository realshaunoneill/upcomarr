"""Text hygiene shared by the sources and the renderer."""

from __future__ import annotations

import re

# C0 controls (except tab, newline and carriage return), DEL, zero-width and directional
# marks, and the bidi embedding, override and isolate characters, which can make text read
# differently from how it is stored.
UNSAFE = re.compile("[\\x00-\\x08\\x0b\\x0c\\x0e-\\x1f\\x7f\\u200b-\\u200f\\u202a-\\u202e\\u2066-\\u2069]")


def clean(value: str) -> str:
    return UNSAFE.sub("", value)
