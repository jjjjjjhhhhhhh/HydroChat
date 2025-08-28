# HydroChat Graph Routing Integration (Phase 16)
# Enhanced routing functions that integrate with centralized routing_map.py
# Replaces hardcoded routing logic with validated, centralized routing decisions

import logging
from typing import Dict, Any, Optional

from .routing_map import RoutingToken, NodeName, route_enforcer
from .enums import Intent, PendingAction, ConfirmationType, DownloadStage
from .state import ConversationState

logger = logging.getLogger(__name__)


class GraphRoutingIntegration:
    """
    Integration layer between conversation graph and centralized routing map.
    Provides validated routing decisions for all graph conditional edges.
    """
    
    @staticmethod
    def route_from_ingest_message(state: Dict[str, Any]) -> str:
        """Route from ingest_user_message node using centralized routing."""
        current_node = "ingest_user_message"
        next_node = state.get("next_node")
        
        # Determine routing token based on next_node set by ingest_user_message_node
        if next_node == "classify_intent":
            routing_token = RoutingToken.CLASSIFIED
            target_node = "classify_intent"
            context = None
        elif next_node == "handle_cancellation":
            routing_token = RoutingToken.CANCELLED
            target_node = "handle_cancellation"
            context = None
        elif next_node is None:
            # Default route when next_node is not set - proceed to classification
            routing_token = RoutingToken.CLASSIFIED
            target_node = "classify_intent"
            context = None
        else:
            # Error case - route to finalization
            routing_token = RoutingToken.ERROR_OCCURRED
            target_node = "finalize_response"
            context = None
        
        # Validate and enforce the route
        validated_target = route_enforcer.enforce_route_decision(
            current_node, target_node, routing_token, context
        )
        
        return validated_target

    @staticmethod
    def route_from_classify_intent(state: Dict[str, Any]) -> str:
        """Route from classify_intent node using intent-specific routing."""
        current_node = "classify_intent"
        conv_state = state["conversation_state"]
        classified_intent = state.get("classified_intent")
        next_node = state.get("next_node")
        context = None  # Initialize context
        
        # Check for confirmation state first
        if conv_state.confirmation_required:
            routing_token = RoutingToken.NEED_CONFIRMATION
            target_node = "handle_confirmation"
        elif classified_intent == Intent.UNKNOWN or next_node == "unknown_intent":
            routing_token = RoutingToken.UNKNOWN_INTENT
            target_node = "unknown_intent"
        elif next_node == "handle_cancellation":
            routing_token = RoutingToken.CANCELLED
            target_node = "handle_cancellation"
        elif next_node in ["show_more_scans", "provide_depth_maps", "provide_agent_stats"]:
            # Special routing for Phase 9/10 nodes
            routing_token = RoutingToken.CLASSIFIED
            target_node = next_node
        elif classified_intent:
            # Intent-specific routing
            routing_token = RoutingToken.CLASSIFIED
            target_node = next_node or "unknown_intent"
            
            # Set context for intent validation
            context = {'intent': classified_intent}
        else:
            # Fallback to unknown intent
            routing_token = RoutingToken.UNKNOWN_INTENT
            target_node = "unknown_intent"
        
        # Validate and enforce the route
        validated_target = route_enforcer.enforce_route_decision(
            current_node, target_node, routing_token, context
        )
        
        return validated_target

    @staticmethod
    def route_from_create_patient(state: Dict[str, Any]) -> str:
        """Route from create_patient node based on field completeness."""
        current_node = "create_patient"
        next_node = state.get("next_node")
        
        if next_node == "execute_create_patient":
            routing_token = RoutingToken.FIELDS_COMPLETE
            target_node = "execute_create_patient"
        elif next_node == "end":
            # Need more fields - route to finalization
            routing_token = RoutingToken.NEED_MORE_FIELDS
            target_node = "finalize_response"
        else:
            # Error case
            routing_token = RoutingToken.ERROR_OCCURRED
            target_node = "finalize_response"
        
        validated_target = route_enforcer.enforce_route_decision(
            current_node, target_node, routing_token
        )
        
        return validated_target

    @staticmethod
    def route_from_execute_create_patient(state: Dict[str, Any]) -> str:
        """Route from execute_create_patient node based on execution result."""
        current_node = "execute_create_patient"
        next_node = state.get("next_node")
        tool_result = state.get("tool_result")
        
        if next_node == "create_patient":
            # Validation error - route back for field correction
            routing_token = RoutingToken.VALIDATION_ERROR
            target_node = "create_patient"
        elif next_node == "end" and tool_result and tool_result.success:
            # Success - check if summarization needed
            routing_token = GraphRoutingIntegration._check_summarization_need(state)
            target_node = "summarize_history" if routing_token == RoutingToken.SHOULD_SUMMARIZE else "finalize_response"
        else:
            # Error or other case
            routing_token = RoutingToken.ERROR_OCCURRED
            target_node = "finalize_response"
        
        validated_target = route_enforcer.enforce_route_decision(
            current_node, target_node, routing_token
        )
        
        return validated_target

    @staticmethod
    def route_from_update_patient(state: Dict[str, Any]) -> str:
        """Route from update_patient node based on field completeness."""
        current_node = "update_patient"
        next_node = state.get("next_node")
        
        if next_node == "execute_update_patient":
            routing_token = RoutingToken.FIELDS_COMPLETE
            target_node = "execute_update_patient"
        elif next_node == "end":
            # Need more fields or patient not found
            routing_token = RoutingToken.NEED_MORE_FIELDS  # Could be PATIENT_NOT_FOUND based on context
            target_node = "finalize_response"
        else:
            routing_token = RoutingToken.ERROR_OCCURRED
            target_node = "finalize_response"
        
        validated_target = route_enforcer.enforce_route_decision(
            current_node, target_node, routing_token
        )
        
        return validated_target

    @staticmethod
    def route_from_execute_update_patient(state: Dict[str, Any]) -> str:
        """Route from execute_update_patient node based on execution result."""
        current_node = "execute_update_patient"
        next_node = state.get("next_node")
        tool_result = state.get("tool_result")
        
        if next_node == "update_patient":
            routing_token = RoutingToken.VALIDATION_ERROR
            target_node = "update_patient"
        elif next_node == "end" and tool_result and tool_result.success:
            routing_token = GraphRoutingIntegration._check_summarization_need(state)
            target_node = "summarize_history" if routing_token == RoutingToken.SHOULD_SUMMARIZE else "finalize_response"
        else:
            routing_token = RoutingToken.ERROR_OCCURRED
            target_node = "finalize_response"
        
        validated_target = route_enforcer.enforce_route_decision(
            current_node, target_node, routing_token
        )
        
        return validated_target

    @staticmethod
    def route_from_delete_patient(state: Dict[str, Any]) -> str:
        """Route from delete_patient node (always to finalization for confirmation)."""
        current_node = "delete_patient"
        
        # Delete patient always routes to finalization to send confirmation prompt
        routing_token = RoutingToken.NEED_CONFIRMATION
        target_node = "finalize_response"
        
        validated_target = route_enforcer.enforce_route_decision(
            current_node, target_node, routing_token
        )
        
        return validated_target

    @staticmethod
    def route_from_execute_delete_patient(state: Dict[str, Any]) -> str:
        """Route from execute_delete_patient node based on deletion result."""
        current_node = "execute_delete_patient"
        tool_result = state.get("tool_result")
        
        if tool_result and tool_result.success:
            routing_token = GraphRoutingIntegration._check_summarization_need(state)
            target_node = "summarize_history" if routing_token == RoutingToken.SHOULD_SUMMARIZE else "finalize_response"
        else:
            routing_token = RoutingToken.ERROR_OCCURRED
            target_node = "finalize_response"
        
        validated_target = route_enforcer.enforce_route_decision(
            current_node, target_node, routing_token
        )
        
        return validated_target

    @staticmethod
    def route_from_confirmation(state: Dict[str, Any]) -> str:
        """Route from handle_confirmation node based on confirmation type and response."""
        current_node = "handle_confirmation"
        next_node = state.get("next_node")
        conv_state = state["conversation_state"]
        context = None  # Initialize context
        
        if next_node == "execute_delete_patient":
            routing_token = RoutingToken.CONFIRMED
            target_node = "execute_delete_patient"
            context = {'confirmation_type': ConfirmationType.DELETE}
        elif next_node == "provide_stl_links":
            routing_token = RoutingToken.STL_REQUESTED
            target_node = "provide_stl_links"
        elif next_node == "end":
            # Could be cancellation or STL declined
            if conv_state.awaiting_confirmation_type == ConfirmationType.DOWNLOAD_STL:
                routing_token = RoutingToken.STL_DECLINED
            else:
                routing_token = RoutingToken.CANCELLED
            target_node = "finalize_response"
        else:
            routing_token = RoutingToken.ERROR_OCCURRED
            target_node = "finalize_response"
        
        validated_target = route_enforcer.enforce_route_decision(
            current_node, target_node, routing_token, context
        )
        
        return validated_target

    @staticmethod
    def route_to_summarization_check(state: Dict[str, Any]) -> str:
        """
        Generic routing for terminal nodes that need summarization check.
        Used by list_patients, get_patient_details, get_scan_results, etc.
        """
        # Extract current node from state if available, otherwise infer from call context
        current_node_hint = state.get("_current_node", "unknown")
        
        routing_token = GraphRoutingIntegration._check_summarization_need(state)
        target_node = "summarize_history" if routing_token == RoutingToken.SHOULD_SUMMARIZE else "finalize_response"
        
        # For validation, we need to determine the current node
        # This is called by multiple nodes, so we'll use a generic validation approach
        logger.debug(f"[ROUTING] Summarization check: {routing_token.name} -> {target_node}")
        
        return target_node

    @staticmethod
    def _check_summarization_need(state: Dict[str, Any]) -> RoutingToken:
        """Check if conversation history needs summarization."""
        conv_state = state["conversation_state"]
        
        if len(conv_state.recent_messages) >= 5:
            return RoutingToken.SHOULD_SUMMARIZE
        else:
            return RoutingToken.FINALIZE_READY

    @staticmethod
    def get_routing_debug_info(state: Dict[str, Any]) -> Dict[str, Any]:
        """Get routing debug information for current state."""
        conv_state = state["conversation_state"]
        
        return {
            'conversation_state': {
                'intent': conv_state.intent.name,
                'pending_action': conv_state.pending_action.name,
                'confirmation_required': conv_state.confirmation_required,
                'confirmation_type': conv_state.awaiting_confirmation_type.name,
                'recent_messages_count': len(conv_state.recent_messages),
                'scan_results_count': len(conv_state.scan_results_buffer),
                'download_stage': conv_state.download_stage.name
            },
            'state_keys': list(state.keys()),
            'next_node': state.get("next_node"),
            'should_end': state.get("should_end")
        }
