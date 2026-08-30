from __future__ import annotations

import re
from typing import Any

SENSITIVE = re.compile(
    r"(?i)(authorization|api[-_ ]?key|cookie|password)(\s*[:=]\s*)([^\s,;]+|\"[^\"]*\")"
)
SENSITIVE_KEY = re.compile(r"(?i)^(authorization|api[-_ ]?key|cookie|password)$")


def sanitize(value: Any) -> Any:
    if isinstance(value, str):
        return SENSITIVE.sub(r"\1\2[REDACTED]", value)
    if isinstance(value, dict):
        return {
            key: ("[REDACTED]" if SENSITIVE_KEY.search(str(key)) else sanitize(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    return value
