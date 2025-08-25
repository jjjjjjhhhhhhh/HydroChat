from __future__ import annotations
from collections import deque
from datetime import datetime
from typing import Dict, Any, List, Optional, Set
import json

from .enums import Intent, PendingAction, ConfirmationType, DownloadStage
from .utils import utc_now

class ConversationState:
    """
    Authoritative state container for HydroChat conversations.
    All keys MUST exist to avoid hallucination. Missing keys => implementation bug.
    """
    
    def __init__(self):
        # Message history (rolling window)
        self.recent_messages = deque(maxlen=5)
        self.history_summary = ""
        
        # Intent & action tracking
        self.intent = Intent.UNKNOWN
        self.pending_action = PendingAction.NONE
        
        # Field extraction & validation
        self.extracted_fields: Dict[str, Any] = {}
        self.validated_fields: Dict[str, Any] = {}
        self.pending_fields: Set[str] = set()
        
        # Patient resolution
        self.patient_cache: List[Dict[str, Any]] = []
        self.patient_cache_timestamp = datetime.fromordinal(1)  # epoch placeholder
        self.disambiguation_options: List[Dict[str, Any]] = []
        self.selected_patient_id: Optional[int] = None
        
        # Conversation flow control
        self.clarification_loop_count = 0
        self.confirmation_required = False
        self.awaiting_confirmation_type = ConfirmationType.NONE
        
        # Tool execution tracking
        self.last_patient_snapshot: Dict[str, Any] = {}
        self.last_tool_request: Dict[str, Any] = {}
        self.last_tool_response: Dict[str, Any] = {}
        self.last_tool_error: Optional[Dict[str, Any]] = None
        
        # Scan results & pagination
        self.scan_results_buffer: List[Dict[str, Any]] = []
        self.scan_pagination_offset = 0
        self.scan_display_limit = 10
        self.download_stage = DownloadStage.NONE
        
        # Metrics & policy
        self.metrics: Dict[str, int] = {
            'total_api_calls': 0,
            'retries': 0,
            'successful_ops': 0,
            'aborted_ops': 0
        }
        self.nric_policy: Dict[str, str] = {
            'regex': r'^[STFG]\d{7}[A-Z]$',
            'mask_style': 'first+******+last2'
        }
        self.config_snapshot: Dict[str, Any] = {}
        
        # Validate all required keys exist
        self._validate_completeness()
    
    def _validate_completeness(self) -> None:
        """Assert all required state keys are present to prevent hallucination."""
        required_attrs = [
            'recent_messages', 'history_summary', 'intent', 'pending_action',
            'extracted_fields', 'validated_fields', 'pending_fields',
            'patient_cache', 'patient_cache_timestamp', 'disambiguation_options',
            'selected_patient_id', 'clarification_loop_count', 'confirmation_required',
            'awaiting_confirmation_type', 'last_patient_snapshot', 'last_tool_request',
            'last_tool_response', 'last_tool_error', 'scan_results_buffer',
            'scan_pagination_offset', 'scan_display_limit', 'download_stage',
            'metrics', 'nric_policy', 'config_snapshot'
        ]
        
        for attr in required_attrs:
            if not hasattr(self, attr):
                raise ValueError(f"Missing required state attribute: {attr}")
    
    def serialize_snapshot(self) -> Dict[str, Any]:
        """Return JSON-safe snapshot with enums serialized by name."""
        return {
            'recent_messages': list(self.recent_messages),
            'history_summary': self.history_summary,
            'intent': self.intent.name,
            'pending_action': self.pending_action.name,
            'extracted_fields': self.extracted_fields.copy(),
            'validated_fields': self.validated_fields.copy(),
            'pending_fields': list(self.pending_fields),
            'patient_cache': self.patient_cache.copy(),
            'patient_cache_timestamp': self.patient_cache_timestamp.isoformat(),
            'disambiguation_options': self.disambiguation_options.copy(),
            'selected_patient_id': self.selected_patient_id,
            'clarification_loop_count': self.clarification_loop_count,
            'confirmation_required': self.confirmation_required,
            'awaiting_confirmation_type': self.awaiting_confirmation_type.name,
            'last_patient_snapshot': self.last_patient_snapshot.copy(),
            'last_tool_request': self.last_tool_request.copy(),
            'last_tool_response': self.last_tool_response.copy(),
            'last_tool_error': self.last_tool_error.copy() if self.last_tool_error else None,
            'scan_results_buffer': self.scan_results_buffer.copy(),
            'scan_pagination_offset': self.scan_pagination_offset,
            'scan_display_limit': self.scan_display_limit,
            'download_stage': self.download_stage.name,
            'metrics': self.metrics.copy(),
            'nric_policy': self.nric_policy.copy(),
            'config_snapshot': self.config_snapshot.copy()
        }
    
    def reset_for_cancellation(self) -> None:
        """Reset state when user cancels current action."""
        self.pending_action = PendingAction.NONE
        self.extracted_fields.clear()
        self.validated_fields.clear()
        self.pending_fields.clear()
        self.disambiguation_options.clear()
        self.selected_patient_id = None
        self.clarification_loop_count = 0
        self.confirmation_required = False
        self.awaiting_confirmation_type = ConfirmationType.NONE
        self.download_stage = DownloadStage.NONE
        self.last_tool_error = None
    
    def add_message(self, role: str, content: str) -> None:
        """Add message to rolling window."""
        self.recent_messages.append({
            'role': role,
            'content': content,
            'timestamp': utc_now().isoformat()
        })

__all__ = ['ConversationState']
