# HydroChat Django REST API Views
# Phase 11: Django Endpoint Implementation for `/api/hydrochat/converse/`

import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, Optional, Any
from threading import Lock

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from .conversation_graph import ConversationGraph, create_conversation_graph
from .state import ConversationState
from .http_client import HttpClient
from .config import load_config
from .enums import Intent, PendingAction, ConfirmationType, DownloadStage
from .utils import mask_nric

logger = logging.getLogger(__name__)

# ===== IN-MEMORY STATE STORE =====

class ConversationStateStore:
    """
    In-memory conversation state store with TTL eviction.
    
    Thread-safe storage for conversation states keyed by UUID.
    Implements simple LRU and timestamp-based eviction.
    """
    
    def __init__(self, max_conversations: int = 100, ttl_minutes: int = 30):
        self.store: Dict[str, Dict[str, Any]] = {}
        self.access_times: Dict[str, datetime] = {}
        self.max_conversations = max_conversations
        self.ttl_minutes = ttl_minutes
        self._lock = Lock()
        
        logger.info(f"[STATE_STORE] 🗄️ Initialized with max_conversations={max_conversations}, ttl_minutes={ttl_minutes}")
    
    def get(self, conversation_id: str) -> Optional[ConversationState]:
        """Get conversation state by ID, returning None if not found or expired."""
        with self._lock:
            # Clean expired entries first
            self._evict_expired()
            
            if conversation_id not in self.store:
                logger.info(f"[STATE_STORE] 🔍 Conversation {conversation_id[:8]}... not found")
                return None
            
            # Check if this specific conversation has expired (additional check)
            if conversation_id in self.access_times:
                # Special case: TTL=0 means immediate expiration
                if self.ttl_minutes == 0:
                    # Remove immediately
                    if conversation_id in self.store:
                        del self.store[conversation_id]
                    if conversation_id in self.access_times:
                        del self.access_times[conversation_id]
                    logger.info(f"[STATE_STORE] 🗑️ Evicted expired conversation {conversation_id[:8]}... on access")
                    return None
                else:
                    cutoff_time = datetime.now() - timedelta(minutes=self.ttl_minutes)
                    if self.access_times[conversation_id] < cutoff_time:
                        # Remove expired conversation
                        if conversation_id in self.store:
                            del self.store[conversation_id]
                        if conversation_id in self.access_times:
                            del self.access_times[conversation_id]
                        logger.info(f"[STATE_STORE] 🗑️ Evicted expired conversation {conversation_id[:8]}... on access")
                        return None
            
            # Update access time
            self.access_times[conversation_id] = datetime.now()
            state_data = self.store[conversation_id]
            
            # Reconstruct ConversationState from stored data
            conv_state = ConversationState()
            
            # Reconstruct deque for recent_messages
            from collections import deque
            conv_state.recent_messages = deque(state_data['recent_messages'], maxlen=5)
            
            # Reconstruct core fields
            conv_state.history_summary = state_data['history_summary']
            conv_state.intent = Intent[state_data['intent']] if state_data['intent'] != 'UNKNOWN' else Intent.UNKNOWN
            conv_state.pending_action = PendingAction[state_data['pending_action']]
            conv_state.extracted_fields = state_data['extracted_fields']
            conv_state.validated_fields = state_data['validated_fields']
            conv_state.pending_fields = set(state_data['pending_fields'])
            conv_state.patient_cache = state_data['patient_cache']
            conv_state.patient_cache_timestamp = datetime.fromisoformat(state_data['patient_cache_timestamp'])
            conv_state.disambiguation_options = state_data['disambiguation_options']
            conv_state.selected_patient_id = state_data['selected_patient_id']
            conv_state.clarification_loop_count = state_data['clarification_loop_count']
            conv_state.confirmation_required = state_data['confirmation_required']
            conv_state.awaiting_confirmation_type = ConfirmationType[state_data['awaiting_confirmation_type']]
            conv_state.last_patient_snapshot = state_data['last_patient_snapshot']
            conv_state.last_tool_request = state_data['last_tool_request']
            conv_state.last_tool_response = state_data['last_tool_response']
            conv_state.last_tool_error = state_data['last_tool_error']
            conv_state.scan_results_buffer = state_data['scan_results_buffer']
            conv_state.scan_pagination_offset = state_data['scan_pagination_offset']
            conv_state.scan_display_limit = state_data['scan_display_limit']
            conv_state.download_stage = DownloadStage[state_data['download_stage']]
            conv_state.metrics = state_data['metrics']
            conv_state.nric_policy = state_data['nric_policy']
            conv_state.config_snapshot = state_data['config_snapshot']
            
            logger.info(f"[STATE_STORE] ✅ Retrieved conversation {conversation_id[:8]}...")
            return conv_state
    
    def put(self, conversation_id: str, state: ConversationState) -> None:
        """Store conversation state by ID."""
        with self._lock:
            # Enforce max conversations limit
            if len(self.store) >= self.max_conversations and conversation_id not in self.store:
                self._evict_lru()
            
            # Store serialized state
            state_dict = state.serialize_snapshot()
            self.store[conversation_id] = state_dict
            self.access_times[conversation_id] = datetime.now()
            
            logger.info(f"[STATE_STORE] 💾 Stored conversation {conversation_id[:8]}...")
    
    def _evict_expired(self) -> None:
        """Remove expired conversations based on TTL."""
        # Special case: TTL=0 means immediate expiration (all conversations expire)
        if self.ttl_minutes == 0:
            expired_ids = list(self.access_times.keys())
        else:
            cutoff_time = datetime.now() - timedelta(minutes=self.ttl_minutes)
            expired_ids = [
                conv_id for conv_id, access_time in self.access_times.items()
                if access_time < cutoff_time
            ]
        
        for conv_id in expired_ids:
            if conv_id in self.store:
                del self.store[conv_id]
            if conv_id in self.access_times:
                del self.access_times[conv_id]
            logger.info(f"[STATE_STORE] 🗑️ Evicted expired conversation {conv_id[:8]}...")
    
    def _evict_lru(self) -> None:
        """Remove least recently used conversation."""
        if not self.access_times:
            return
        
        lru_id = min(self.access_times.keys(), key=lambda x: self.access_times[x])
        del self.store[lru_id]
        del self.access_times[lru_id]
        logger.info(f"[STATE_STORE] 🗑️ Evicted LRU conversation {lru_id[:8]}...")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get store statistics for monitoring."""
        with self._lock:
            self._evict_expired()
            return {
                'active_conversations': len(self.store),
                'max_conversations': self.max_conversations,
                'ttl_minutes': self.ttl_minutes,
                'oldest_access': min(self.access_times.values()) if self.access_times else None,
                'newest_access': max(self.access_times.values()) if self.access_times else None,
            }


# Global state store instance
conversation_store = ConversationStateStore()

# Global conversation graph instance
_conversation_graph: Optional[ConversationGraph] = None
_graph_lock = Lock()


def get_conversation_graph() -> ConversationGraph:
    """Get or create the global conversation graph instance."""
    global _conversation_graph
    
    with _graph_lock:
        if _conversation_graph is None:
            config = load_config()
            http_client = HttpClient()
            _conversation_graph = create_conversation_graph(http_client)
            logger.info("[CONVERSE_API] 🤖 Global conversation graph initialized")
        
        return _conversation_graph


# ===== API VIEWS =====

class ConverseAPIView(APIView):
    """
    HydroChat conversation endpoint.
    
    POST /api/hydrochat/converse/
    Handles conversational interactions with the HydroChat assistant.
    """
    
    permission_classes = [IsAuthenticated]
    
    def post(self, request) -> Response:
        """
        Process a conversation turn.
        
        Request Body:
        {
            "conversation_id": "<uuid|null>",
            "message": "<raw user text>"
        }
        
        Response:
        {
            "conversation_id": "<uuid>",
            "messages": [
                {"role": "assistant", "content": "<reply>"}
            ],
            "agent_state": {
                "intent": "CREATE_PATIENT|UPDATE_PATIENT|...|UNKNOWN",
                "awaiting_confirmation": false,
                "missing_fields": []
            },
            "agent_op": "CREATE|UPDATE|DELETE|NONE"
        }
        """
        try:
            # Validate request data - handle parsing errors
            try:
                data = request.data
                if not isinstance(data, dict):
                    return Response(
                        {"error": "validation", "detail": "Request body must be JSON object"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            except Exception as e:
                return Response(
                    {"error": "validation", "detail": f"Invalid request format: {str(e)}"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            conversation_id = data.get('conversation_id')
            message = data.get('message')
            
            # Validate message
            if not message or not isinstance(message, str):
                return Response(
                    {"error": "validation", "detail": "message field is required and must be a string"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            message = message.strip()
            if not message:
                return Response(
                    {"error": "validation", "detail": "message cannot be empty"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            logger.info(f"[CONVERSE_API] 💬 Processing message: '{mask_nric(message[:50])}...'")
            
            # Load or create conversation state
            if conversation_id:
                # Try to load existing conversation
                conv_state = conversation_store.get(conversation_id)
                if conv_state is None:
                    # Conversation not found or expired, create new one
                    conversation_id = str(uuid.uuid4())
                    conv_state = ConversationState()
                    logger.info(f"[CONVERSE_API] 🆕 Created new conversation {conversation_id[:8]}... (previous not found)")
                else:
                    logger.info(f"[CONVERSE_API] 🔄 Continuing conversation {conversation_id[:8]}...")
            else:
                # Create new conversation
                conversation_id = str(uuid.uuid4())
                conv_state = ConversationState()
                logger.info(f"[CONVERSE_API] 🆕 Created new conversation {conversation_id[:8]}...")
            
            # Get conversation graph
            graph = get_conversation_graph()
            
            # Process the message
            agent_response, updated_conv_state = graph.process_message_sync(message, conv_state)
            
            # Store updated state
            conversation_store.put(conversation_id, updated_conv_state)
            
            # Determine agent_op based on conversation state
            agent_op = self._determine_agent_op(updated_conv_state)
            
            # Build response
            response_data = {
                "conversation_id": conversation_id,
                "messages": [
                    {"role": "assistant", "content": agent_response}
                ],
                "agent_state": {
                    "intent": updated_conv_state.intent.name,  # Use .name instead of .value
                    "awaiting_confirmation": updated_conv_state.confirmation_required,
                    "missing_fields": list(updated_conv_state.pending_fields) if updated_conv_state.pending_fields else []
                },
                "agent_op": agent_op
            }
            
            logger.info(f"[CONVERSE_API] ✅ Response prepared for {conversation_id[:8]}... (agent_op: {agent_op})")
            return Response(response_data, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"[CONVERSE_API] ❌ Server error: {e}")
            return Response(
                {"error": "server", "detail": "Internal server error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _determine_agent_op(self, conv_state: ConversationState) -> str:
        """
        Determine the agent_op value based on conversation state.
        
        Returns: "CREATE", "UPDATE", "DELETE", or "NONE"
        """
        # Check if we just completed a successful operation
        if conv_state.last_tool_response and conv_state.last_tool_response.get('success'):
            # Check if there was a recent successful tool execution
            if conv_state.intent == Intent.CREATE_PATIENT:
                return "CREATE"
            elif conv_state.intent == Intent.UPDATE_PATIENT:
                return "UPDATE"
            elif conv_state.intent == Intent.DELETE_PATIENT:
                return "DELETE"
        
        # Check pending action for operations in progress that may complete
        if conv_state.pending_action == PendingAction.CREATE_PATIENT:
            return "NONE"  # Still in progress
        elif conv_state.pending_action == PendingAction.UPDATE_PATIENT:
            return "NONE"  # Still in progress
        elif conv_state.pending_action == PendingAction.DELETE_PATIENT:
            return "NONE"  # Still in progress
        
        # Default to NONE for read operations or no operation
        return "NONE"


class ConverseStatsAPIView(APIView):
    """
    HydroChat conversation statistics endpoint.
    
    GET /api/hydrochat/converse/stats/
    Returns statistics about active conversations and system health.
    """
    
    permission_classes = [IsAuthenticated]
    
    def get(self, request) -> Response:
        """Get conversation system statistics."""
        try:
            stats = conversation_store.get_stats()
            return Response(stats, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"[CONVERSE_STATS] ❌ Error getting stats: {e}")
            return Response(
                {"error": "server", "detail": "Failed to retrieve statistics"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class MetricsExportAPIView(APIView):
    """
    Phase 17: Metrics Export Endpoint for Dashboard Integration
    
    GET /api/hydrochat/metrics/export/
    Returns comprehensive performance and LLM metrics in JSON format.
    
    Developer-only endpoint per §29 - restricted to staff/superuser.
    """
    
    permission_classes = [IsAuthenticated]
    
    def get(self, request) -> Response:
        """
        Export comprehensive metrics for external monitoring.
        
        Returns JSON with:
        - Performance metrics (response times, violations)
        - LLM API metrics (token usage, costs)
        - Conversation analytics
        - Alert thresholds status
        - Metrics retention statistics
        """
        try:
            # Developer-only access check per §29
            if not (request.user.is_staff or request.user.is_superuser):
                logger.warning(
                    f"[METRICS_EXPORT] ⚠️ Unauthorized access attempt by user {request.user.username}"
                )
                return Response(
                    {"error": "forbidden", "detail": "Developer-only endpoint"},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            logger.info(f"[METRICS_EXPORT] 📊 Exporting metrics for user {request.user.username}")
            
            # Import metrics modules
            from .performance import get_performance_summary
            from .gemini_client import get_gemini_metrics_v2
            from .metrics_store import get_global_metrics_store
            from .agent_stats import agent_stats
            
            # Gather performance metrics
            performance_summary = get_performance_summary()
            
            # Gather LLM API metrics
            llm_metrics = get_gemini_metrics_v2()
            
            # Gather metrics store statistics
            metrics_store = get_global_metrics_store()
            retention_stats = metrics_store.get_statistics()
            
            # Get a dummy conversation state for agent stats
            # In production, this would aggregate across all conversations
            from .state import ConversationState
            sample_state = ConversationState()
            
            # Aggregate conversation metrics if available
            aggregate_metrics = {
                'total_api_calls': 0,
                'successful_ops': 0,
                'aborted_ops': 0,
                'retries': 0
            }
            
            # Generate comprehensive export
            export_data = {
                'timestamp': datetime.now().isoformat(),
                'performance_metrics': performance_summary,
                'llm_api_metrics': {
                    'successful_calls': llm_metrics['successful_calls'],
                    'failed_calls': llm_metrics['failed_calls'],
                    'total_calls': llm_metrics['successful_calls'] + llm_metrics['failed_calls'],
                    'total_tokens_used': llm_metrics['total_tokens_used'],
                    'prompt_tokens': llm_metrics['prompt_tokens_used'],
                    'completion_tokens': llm_metrics['completion_tokens_used'],
                    'total_cost_usd': llm_metrics['total_cost_usd'],
                    'last_call_timestamp': llm_metrics['last_call_timestamp']
                },
                'conversation_analytics': aggregate_metrics,
                'retention_policy': {
                    'max_entries': retention_stats['max_entries'],
                    'ttl_hours': retention_stats['ttl_hours'],
                    'current_entries': retention_stats['total_entries'],
                    'expired_count': retention_stats['expired_count'],
                    'storage_utilization_percent': retention_stats['storage_utilization_percent'],
                    'last_cleanup': retention_stats['last_cleanup']
                },
                'system_info': {
                    'active_conversations': len(conversation_store.store),
                    'export_version': '1.0.0'
                }
            }
            
            logger.info(
                f"[METRICS_EXPORT] ✅ Export complete - "
                f"{export_data['llm_api_metrics']['total_calls']} LLM calls, "
                f"{export_data['performance_metrics']['metrics_count']} performance entries"
            )
            
            return Response(export_data, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.exception(f"[METRICS_EXPORT] ❌ Export error: {e}")
            return Response(
                {"error": "server", "detail": "Failed to export metrics"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )