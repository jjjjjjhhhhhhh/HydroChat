from __future__ import annotations
import re
from datetime import datetime
from typing import Dict, Any, Optional, Tuple

from .enums import Intent

# Pre-compiled regex patterns for intent classification (case-insensitive)
_INTENT_PATTERNS = {
    Intent.CREATE_PATIENT: re.compile(r'(create|add|new)\s+(patient)', re.IGNORECASE),
    Intent.UPDATE_PATIENT: re.compile(r'(update|change|modify|edit)\s+(patient|contact|nric|name|details)', re.IGNORECASE),
    Intent.DELETE_PATIENT: re.compile(r'(delete|remove|del)\s+(patient)', re.IGNORECASE),
    Intent.LIST_PATIENTS: re.compile(r'(list|show|all)\s+patients', re.IGNORECASE),
    Intent.GET_SCAN_RESULTS: re.compile(r'(show|list|get).*(scan|result)', re.IGNORECASE),
    Intent.GET_PATIENT_DETAILS: re.compile(r'(show|get).*(patient)', re.IGNORECASE),
    Intent.CANCEL: re.compile(r'\b(cancel|abort|stop|quit|exit|reset)\b', re.IGNORECASE),  # Phase 8: Cancellation detection
}

# Phase 9: Additional patterns for pagination and depth maps
_SHOW_MORE_PATTERN = re.compile(r'\b(show|display)\s+(more|next|additional)\s+(scan|result)', re.IGNORECASE)
_DEPTH_MAP_PATTERN = re.compile(r'\b(depth\s+map|show\s+depth)\b', re.IGNORECASE)

# Phase 10: Stats command pattern
_STATS_PATTERN = re.compile(r'\b(stats|statistics|metrics|status|performance|summary)\b', re.IGNORECASE)

# Field extraction patterns
_NRIC_PATTERN = re.compile(r'\b([STFG]\d{7}[A-Z])\b')
_NAME_PATTERN = re.compile(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b')  # Two+ capitalized tokens
_CONTACT_PATTERN = re.compile(r'(\+?\d{8,15})')  # 8-15 digits with optional + (no word boundary)
_DOB_PATTERN = re.compile(r'\b(\d{4}-\d{2}-\d{2})\b')  # YYYY-MM-DD format only
_PATIENT_ID_PATTERN = re.compile(r'\bpatient\s+(\d+)\b', re.IGNORECASE)


def classify_intent(text: str) -> Intent:
    """
    Classify user intent using deterministic regex patterns.
    Returns UNKNOWN if no pattern matches.
    """
    text = text.strip()
    
    # Test patterns in priority order
    for intent, pattern in _INTENT_PATTERNS.items():
        if pattern.search(text):
            # Special disambiguation: GET_PATIENT_DETAILS vs GET_SCAN_RESULTS
            if intent == Intent.GET_PATIENT_DETAILS:
                # If text also mentions scan/result, prefer scan results
                if _INTENT_PATTERNS[Intent.GET_SCAN_RESULTS].search(text):
                    return Intent.GET_SCAN_RESULTS
            return intent
    
    return Intent.UNKNOWN


def extract_fields(text: str) -> Dict[str, Any]:
    """
    Extract structured fields from user text using regex patterns.
    Returns dict with found values (may be incomplete).
    """
    fields = {}
    
    # NRIC extraction
    nric_match = _NRIC_PATTERN.search(text)
    if nric_match:
        fields['nric'] = nric_match.group(1)
    
    # Name extraction (two consecutive capitalized words)
    name_match = _NAME_PATTERN.search(text)
    if name_match:
        name_parts = name_match.group(1).split()
        if len(name_parts) >= 2:
            fields['first_name'] = name_parts[0]
            fields['last_name'] = ' '.join(name_parts[1:])
    
    # Contact number
    contact_match = _CONTACT_PATTERN.search(text)
    if contact_match:
        # Keep as-is (including + if present)
        fields['contact_no'] = contact_match.group(1)
    
    # Date of birth (strict YYYY-MM-DD)
    dob_match = _DOB_PATTERN.search(text)
    if dob_match:
        try:
            # Validate it's a real date
            datetime.strptime(dob_match.group(1), '%Y-%m-%d')
            fields['date_of_birth'] = dob_match.group(1)
        except ValueError:
            pass  # Invalid date, skip
    
    # Patient ID extraction
    id_match = _PATIENT_ID_PATTERN.search(text)
    if id_match:
        fields['patient_id'] = int(id_match.group(1))
    
    # Details extraction (anything after structured fields - simplified)
    # Remove matched patterns and take remainder as details if substantial
    remaining = text
    for pattern in [_NRIC_PATTERN, _NAME_PATTERN, _CONTACT_PATTERN, _DOB_PATTERN, _PATIENT_ID_PATTERN]:
        remaining = pattern.sub('', remaining)
    
    # Clean up whitespace and common command words
    remaining = re.sub(r'\b(create|add|new|update|patient|contact|details?)\b', '', remaining, flags=re.IGNORECASE)
    remaining = re.sub(r'\s+', ' ', remaining).strip()
    
    if len(remaining) > 3:  # Substantial remaining text
        fields['details'] = remaining
    
    return fields


def validate_required_patient_fields(fields: Dict[str, Any]) -> Tuple[bool, set[str]]:
    """
    Check if all required patient fields are present.
    Returns (is_complete, missing_fields).
    """
    required = {'first_name', 'last_name', 'nric'}
    present = set(k for k, v in fields.items() if v is not None and str(v).strip())
    missing = required - present
    return len(missing) == 0, missing


def is_show_more_scans(text: str) -> bool:
    """
    Phase 9: Check if user is requesting to show more scan results.
    """
    return _SHOW_MORE_PATTERN.search(text) is not None


def is_depth_map_request(text: str) -> bool:
    """
    Phase 9: Check if user is requesting depth map information.
    """
    return _DEPTH_MAP_PATTERN.search(text) is not None


def is_stats_request(text: str) -> bool:
    """
    Phase 10: Check if user is requesting agent statistics.
    """
    return _STATS_PATTERN.search(text) is not None


# Fallback LLM classification stub (returns UNKNOWN for now)
def llm_classify_intent_fallback(text: str) -> Intent:
    """
    Placeholder for future LLM-based classification.
    Currently returns UNKNOWN to trigger clarifying prompt.
    """
    # TODO: Implement LLM classification with strict JSON schema {intent, reason}
    return Intent.UNKNOWN


__all__ = [
    'classify_intent', 'extract_fields', 'validate_required_patient_fields',
    'llm_classify_intent_fallback', 'is_show_more_scans', 'is_depth_map_request'
]
