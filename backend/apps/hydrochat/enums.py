from __future__ import annotations
from enum import Enum, auto

class Intent(Enum):
    CREATE_PATIENT = auto()
    UPDATE_PATIENT = auto()
    DELETE_PATIENT = auto()
    LIST_PATIENTS = auto()
    GET_PATIENT_DETAILS = auto()
    GET_SCAN_RESULTS = auto()
    UNKNOWN = auto()

class PendingAction(Enum):
    NONE = auto()
    CREATE_PATIENT = auto()
    UPDATE_PATIENT = auto()
    DELETE_PATIENT = auto()
    GET_SCAN_RESULTS = auto()

class ConfirmationType(Enum):
    NONE = auto()
    DELETE = auto()
    DOWNLOAD_STL = auto()

class DownloadStage(Enum):
    NONE = auto()
    PREVIEW_SHOWN = auto()
    AWAITING_STL_CONFIRM = auto()
    STL_LINKS_SENT = auto()

__all__ = [
    'Intent', 'PendingAction', 'ConfirmationType', 'DownloadStage'
]
