from __future__ import annotations
from enum import Enum, auto

class Intent(Enum):
    CREATE_PATIENT = auto()
    UPDATE_PATIENT = auto()
    DELETE_PATIENT = auto()
    LIST_PATIENTS = auto()
    GET_PATIENT_DETAILS = auto()
    GET_SCAN_RESULTS = auto()
    SHOW_MORE_SCANS = auto()       # Phase 16: Show additional scan results
    PROVIDE_DEPTH_MAPS = auto()    # Phase 16: Provide depth map data
    PROVIDE_AGENT_STATS = auto()   # Phase 16: Show agent statistics
    CANCEL = auto()                # Phase 8: Cancellation command handling
    UNKNOWN = auto()

class PendingAction(Enum):
    NONE = auto()
    CREATE_PATIENT = auto()
    UPDATE_PATIENT = auto()
    DELETE_PATIENT = auto()
    LIST_PATIENTS = auto()  # Added for Phase 13
    GET_PATIENT_DETAILS = auto()  # Added for Phase 13  
    GET_SCAN_RESULTS = auto()

class ConfirmationType(Enum):
    NONE = auto()
    DELETE = auto()
    UPDATE = auto()        # Phase 16: Update confirmation
    DOWNLOAD_STL = auto()

class DownloadStage(Enum):
    NONE = auto()
    PREVIEW_SHOWN = auto()
    AWAITING_STL_CONFIRM = auto()
    STL_LINKS_SENT = auto()

__all__ = [
    'Intent', 'PendingAction', 'ConfirmationType', 'DownloadStage'
]
