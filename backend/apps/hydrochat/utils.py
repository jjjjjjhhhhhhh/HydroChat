from __future__ import annotations
import re
from datetime import datetime, timezone

NRIC_REGEX = re.compile(r'^[STFG]\d{7}[A-Z]$')

def validate_nric(nric: str) -> bool:
    return bool(NRIC_REGEX.match(nric))

def mask_nric(nric: str) -> str:
    if not nric:
        return nric
    if len(nric) < 3:
        return nric[0] + '*' * (len(nric) - 1)
    return f"{nric[0]}******{nric[-2:]}"

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

__all__ = ['validate_nric', 'mask_nric', 'utc_now', 'NRIC_REGEX']
