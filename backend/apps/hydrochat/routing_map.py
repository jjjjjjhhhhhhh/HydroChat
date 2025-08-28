# HydroChat Centralized Routing Map (Phase 16)
# Single source of truth for all graph state transitions per HydroChat.md §24.1
# Implements complete routing matrix with all 16 nodes and conditional tokens

from typing import Dict, List, Set, Optional, Union, Tuple, Any
from enum import Enum, auto
import logging

from .enums import Intent, PendingAction, ConfirmationType, DownloadStage

logger = logging.getLogger(__name__)


class RoutingToken(Enum):
    """
    Authoritative routing tokens per HydroChat.md §24.1.
    These are the ONLY allowed conditional routing tokens in the conversation graph.
    """
    # Core flow tokens
    CLASSIFIED = auto()
    UNKNOWN_INTENT = auto()
    NEED_CONFIRMATION = auto()
    CONFIRMED = auto()
    CANCELLED = auto()
    
    # Patient workflow tokens
    NEED_MORE_FIELDS = auto()
    FIELDS_COMPLETE = auto()
    VALIDATION_ERROR = auto()
    PATIENT_NOT_FOUND = auto()
    AMBIGUOUS_PRESENT = auto()
    RESOLVED = auto()
    
    # Scan workflow tokens
    NO_SCANS = auto()
    SCANS_FOUND = auto()
    MORE_AVAILABLE = auto()
    STL_REQUESTED = auto()
    STL_DECLINED = auto()
    DEPTH_REQUESTED = auto()
    
    # System tokens
    ERROR_OCCURRED = auto()
    SHOULD_SUMMARIZE = auto()
    FINALIZE_READY = auto()
    END_CONVERSATION = auto()


class NodeName(Enum):
    """
    Complete 16-node inventory per HydroChat.md §12 and Phase 15 implementation.
    These are ALL the nodes in the conversation graph.
    """
    # Core processing nodes (Phase 15)
    INGEST_USER_MESSAGE = "ingest_user_message"
    SUMMARIZE_HISTORY = "summarize_history"
    FINALIZE_RESPONSE = "finalize_response"
    
    # Intent and classification
    CLASSIFY_INTENT = "classify_intent"
    
    # Patient CRUD workflows
    CREATE_PATIENT = "create_patient"
    EXECUTE_CREATE_PATIENT = "execute_create_patient"
    UPDATE_PATIENT = "update_patient"
    EXECUTE_UPDATE_PATIENT = "execute_update_patient"
    DELETE_PATIENT = "delete_patient"
    EXECUTE_DELETE_PATIENT = "execute_delete_patient"
    LIST_PATIENTS = "list_patients"
    GET_PATIENT_DETAILS = "get_patient_details"
    
    # Scan workflows
    GET_SCAN_RESULTS = "get_scan_results"
    PROVIDE_STL_LINKS = "provide_stl_links"
    SHOW_MORE_SCANS = "show_more_scans"
    PROVIDE_DEPTH_MAPS = "provide_depth_maps"
    
    # System workflows
    HANDLE_CONFIRMATION = "handle_confirmation"
    HANDLE_CANCELLATION = "handle_cancellation"
    UNKNOWN_INTENT = "unknown_intent"
    PROVIDE_AGENT_STATS = "provide_agent_stats"


class RoutingMatrix:
    """
    Complete routing matrix for the conversation graph.
    Maps each node to its possible next states based on conditional tokens.
    """
    
    # Node -> {Token -> Next Node or None for END}
    ROUTING_TABLE: Dict[NodeName, Dict[RoutingToken, Optional[NodeName]]] = {
        
        # Entry point (Phase 15)
        NodeName.INGEST_USER_MESSAGE: {
            RoutingToken.CLASSIFIED: NodeName.CLASSIFY_INTENT,
            RoutingToken.CANCELLED: NodeName.HANDLE_CANCELLATION,
            RoutingToken.ERROR_OCCURRED: NodeName.FINALIZE_RESPONSE,
        },
        
        # Intent classification routing
        NodeName.CLASSIFY_INTENT: {
            RoutingToken.CLASSIFIED: NodeName.CREATE_PATIENT,  # Default: will be overridden by intent
            RoutingToken.NEED_CONFIRMATION: NodeName.HANDLE_CONFIRMATION,
            RoutingToken.CANCELLED: NodeName.HANDLE_CANCELLATION,
            RoutingToken.UNKNOWN_INTENT: NodeName.UNKNOWN_INTENT,
        },
        
        # Patient creation workflow
        NodeName.CREATE_PATIENT: {
            RoutingToken.FIELDS_COMPLETE: NodeName.EXECUTE_CREATE_PATIENT,
            RoutingToken.NEED_MORE_FIELDS: NodeName.FINALIZE_RESPONSE,
            RoutingToken.ERROR_OCCURRED: NodeName.FINALIZE_RESPONSE,
        },
        
        NodeName.EXECUTE_CREATE_PATIENT: {
            RoutingToken.FINALIZE_READY: NodeName.FINALIZE_RESPONSE,
            RoutingToken.SHOULD_SUMMARIZE: NodeName.SUMMARIZE_HISTORY,
            RoutingToken.VALIDATION_ERROR: NodeName.CREATE_PATIENT,
            RoutingToken.ERROR_OCCURRED: NodeName.FINALIZE_RESPONSE,
        },
        
        # Patient update workflow  
        NodeName.UPDATE_PATIENT: {
            RoutingToken.FIELDS_COMPLETE: NodeName.EXECUTE_UPDATE_PATIENT,
            RoutingToken.NEED_MORE_FIELDS: NodeName.FINALIZE_RESPONSE,
            RoutingToken.PATIENT_NOT_FOUND: NodeName.FINALIZE_RESPONSE,
            RoutingToken.ERROR_OCCURRED: NodeName.FINALIZE_RESPONSE,
        },
        
        NodeName.EXECUTE_UPDATE_PATIENT: {
            RoutingToken.FINALIZE_READY: NodeName.FINALIZE_RESPONSE,
            RoutingToken.SHOULD_SUMMARIZE: NodeName.SUMMARIZE_HISTORY,
            RoutingToken.VALIDATION_ERROR: NodeName.UPDATE_PATIENT,
            RoutingToken.ERROR_OCCURRED: NodeName.FINALIZE_RESPONSE,
        },
        
        # Patient deletion workflow
        NodeName.DELETE_PATIENT: {
            RoutingToken.NEED_CONFIRMATION: NodeName.FINALIZE_RESPONSE,
            RoutingToken.PATIENT_NOT_FOUND: NodeName.FINALIZE_RESPONSE,
            RoutingToken.ERROR_OCCURRED: NodeName.FINALIZE_RESPONSE,
        },
        
        NodeName.EXECUTE_DELETE_PATIENT: {
            RoutingToken.FINALIZE_READY: NodeName.FINALIZE_RESPONSE,
            RoutingToken.SHOULD_SUMMARIZE: NodeName.SUMMARIZE_HISTORY,
            RoutingToken.ERROR_OCCURRED: NodeName.FINALIZE_RESPONSE,
        },
        
        # Patient listing and details
        NodeName.LIST_PATIENTS: {
            RoutingToken.FINALIZE_READY: NodeName.FINALIZE_RESPONSE,
            RoutingToken.SHOULD_SUMMARIZE: NodeName.SUMMARIZE_HISTORY,
            RoutingToken.ERROR_OCCURRED: NodeName.FINALIZE_RESPONSE,
        },
        
        NodeName.GET_PATIENT_DETAILS: {
            RoutingToken.FINALIZE_READY: NodeName.FINALIZE_RESPONSE,
            RoutingToken.SHOULD_SUMMARIZE: NodeName.SUMMARIZE_HISTORY,
            RoutingToken.PATIENT_NOT_FOUND: NodeName.FINALIZE_RESPONSE,
            RoutingToken.ERROR_OCCURRED: NodeName.FINALIZE_RESPONSE,
        },
        
        # Scan workflows
        NodeName.GET_SCAN_RESULTS: {
            RoutingToken.SCANS_FOUND: NodeName.FINALIZE_RESPONSE,
            RoutingToken.NO_SCANS: NodeName.FINALIZE_RESPONSE,
            RoutingToken.SHOULD_SUMMARIZE: NodeName.SUMMARIZE_HISTORY,
            RoutingToken.PATIENT_NOT_FOUND: NodeName.FINALIZE_RESPONSE,
            RoutingToken.ERROR_OCCURRED: NodeName.FINALIZE_RESPONSE,
        },
        
        NodeName.PROVIDE_STL_LINKS: {
            RoutingToken.FINALIZE_READY: NodeName.FINALIZE_RESPONSE,
            RoutingToken.SHOULD_SUMMARIZE: NodeName.SUMMARIZE_HISTORY,
            RoutingToken.ERROR_OCCURRED: NodeName.FINALIZE_RESPONSE,
        },
        
        NodeName.SHOW_MORE_SCANS: {
            RoutingToken.MORE_AVAILABLE: NodeName.FINALIZE_RESPONSE,
            RoutingToken.FINALIZE_READY: NodeName.FINALIZE_RESPONSE,
            RoutingToken.SHOULD_SUMMARIZE: NodeName.SUMMARIZE_HISTORY,
            RoutingToken.ERROR_OCCURRED: NodeName.FINALIZE_RESPONSE,
        },
        
        NodeName.PROVIDE_DEPTH_MAPS: {
            RoutingToken.FINALIZE_READY: NodeName.FINALIZE_RESPONSE,
            RoutingToken.SHOULD_SUMMARIZE: NodeName.SUMMARIZE_HISTORY,
            RoutingToken.ERROR_OCCURRED: NodeName.FINALIZE_RESPONSE,
        },
        
        # System and utility nodes
        NodeName.HANDLE_CONFIRMATION: {
            RoutingToken.CONFIRMED: NodeName.EXECUTE_DELETE_PATIENT,  # Context dependent
            RoutingToken.STL_REQUESTED: NodeName.PROVIDE_STL_LINKS,
            RoutingToken.STL_DECLINED: NodeName.FINALIZE_RESPONSE,
            RoutingToken.CANCELLED: NodeName.FINALIZE_RESPONSE,
            RoutingToken.ERROR_OCCURRED: NodeName.FINALIZE_RESPONSE,
        },
        
        NodeName.HANDLE_CANCELLATION: {
            RoutingToken.FINALIZE_READY: NodeName.FINALIZE_RESPONSE,
            RoutingToken.SHOULD_SUMMARIZE: NodeName.SUMMARIZE_HISTORY,
        },
        
        NodeName.UNKNOWN_INTENT: {
            RoutingToken.FINALIZE_READY: NodeName.FINALIZE_RESPONSE,
            RoutingToken.SHOULD_SUMMARIZE: NodeName.SUMMARIZE_HISTORY,
        },
        
        NodeName.PROVIDE_AGENT_STATS: {
            RoutingToken.FINALIZE_READY: NodeName.FINALIZE_RESPONSE,
            RoutingToken.SHOULD_SUMMARIZE: NodeName.SUMMARIZE_HISTORY,
            RoutingToken.ERROR_OCCURRED: NodeName.FINALIZE_RESPONSE,
        },
        
        # Terminal nodes (Phase 15)
        NodeName.SUMMARIZE_HISTORY: {
            RoutingToken.FINALIZE_READY: NodeName.FINALIZE_RESPONSE,
        },
        
        NodeName.FINALIZE_RESPONSE: {
            RoutingToken.END_CONVERSATION: None,  # END state
        },
    }
    
    # Intent-specific routing overrides for classify_intent node
    INTENT_ROUTING_OVERRIDES: Dict[Intent, NodeName] = {
        Intent.CREATE_PATIENT: NodeName.CREATE_PATIENT,
        Intent.UPDATE_PATIENT: NodeName.UPDATE_PATIENT,
        Intent.DELETE_PATIENT: NodeName.DELETE_PATIENT,
        Intent.LIST_PATIENTS: NodeName.LIST_PATIENTS,
        Intent.GET_PATIENT_DETAILS: NodeName.GET_PATIENT_DETAILS,
        Intent.GET_SCAN_RESULTS: NodeName.GET_SCAN_RESULTS,
        Intent.SHOW_MORE_SCANS: NodeName.SHOW_MORE_SCANS,
        Intent.PROVIDE_DEPTH_MAPS: NodeName.PROVIDE_DEPTH_MAPS,
        Intent.PROVIDE_AGENT_STATS: NodeName.PROVIDE_AGENT_STATS,
        Intent.CANCEL: NodeName.HANDLE_CANCELLATION,
        Intent.UNKNOWN: NodeName.UNKNOWN_INTENT,
    }
    
    # Special routing context for confirmation handling
    CONFIRMATION_CONTEXT_ROUTING: Dict[ConfirmationType, Dict[bool, NodeName]] = {
        ConfirmationType.DELETE: {
            True: NodeName.EXECUTE_DELETE_PATIENT,  # Confirmed
            False: NodeName.FINALIZE_RESPONSE,      # Cancelled
        },
        ConfirmationType.UPDATE: {
            True: NodeName.EXECUTE_UPDATE_PATIENT,  # Confirmed
            False: NodeName.FINALIZE_RESPONSE,      # Cancelled
        },
        ConfirmationType.DOWNLOAD_STL: {
            True: NodeName.PROVIDE_STL_LINKS,       # Confirmed
            False: NodeName.FINALIZE_RESPONSE,      # Declined
        },
    }


class RoutingValidator:
    """
    Graph validation and route enforcement per §26.
    Prevents invalid routes and hallucination through assertion checks.
    """
    
    @staticmethod
    def validate_routing_table() -> List[str]:
        """
        Validate the complete routing table for consistency and completeness.
        
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        
        # Check all nodes are represented
        all_nodes = set(NodeName)
        routing_nodes = set(RoutingMatrix.ROUTING_TABLE.keys())
        
        missing_nodes = all_nodes - routing_nodes
        if missing_nodes:
            errors.append(f"Missing nodes in routing table: {[n.value for n in missing_nodes]}")
        
        # Check for orphaned nodes (nodes that can't be reached)
        reachable_nodes = {NodeName.INGEST_USER_MESSAGE}  # Entry point
        
        def find_reachable(node: NodeName, visited: Optional[Set[NodeName]] = None):
            if visited is None:
                visited = set()
            if node in visited:
                return
            visited.add(node)
            
            node_routes = RoutingMatrix.ROUTING_TABLE.get(node, {})
            for next_node in node_routes.values():
                if next_node and next_node not in visited:
                    reachable_nodes.add(next_node)
                    find_reachable(next_node, visited)
        
        find_reachable(NodeName.INGEST_USER_MESSAGE)
        
        # Add intent routing overrides to reachable
        for target_node in RoutingMatrix.INTENT_ROUTING_OVERRIDES.values():
            reachable_nodes.add(target_node)
        
        # Add confirmation routing to reachable
        for confirmation_routes in RoutingMatrix.CONFIRMATION_CONTEXT_ROUTING.values():
            for target_node in confirmation_routes.values():
                if target_node:
                    reachable_nodes.add(target_node)
        
        unreachable_nodes = all_nodes - reachable_nodes
        if unreachable_nodes:
            errors.append(f"Unreachable nodes: {[n.value for n in unreachable_nodes]}")
        
        # Check for invalid token usage
        all_tokens = set(RoutingToken)
        used_tokens = set()
        
        for node_routes in RoutingMatrix.ROUTING_TABLE.values():
            used_tokens.update(node_routes.keys())
        
        undefined_tokens = used_tokens - all_tokens
        if undefined_tokens:
            errors.append(f"Undefined routing tokens used: {undefined_tokens}")
        
        return errors
    
    @staticmethod
    def validate_node_transition(
        from_node: str, 
        to_node: str, 
        routing_token: RoutingToken,
        context: Optional[Dict] = None
    ) -> bool:
        """
        Validate a specific node transition is allowed.
        
        Args:
            from_node: Source node name
            to_node: Target node name 
            routing_token: The routing token justifying the transition
            context: Additional context (intent, confirmation type, etc.)
            
        Returns:
            True if transition is valid, False otherwise
        """
        try:
            from_node_enum = NodeName(from_node)
            to_node_enum = NodeName(to_node) if to_node else None
        except ValueError as e:
            logger.error(f"[ROUTING] Invalid node name in transition: {e}")
            return False
        
        # Get allowed transitions for source node
        allowed_transitions = RoutingMatrix.ROUTING_TABLE.get(from_node_enum, {})
        
        # Check if the token is valid for this node
        if routing_token not in allowed_transitions:
            logger.error(f"[ROUTING] Token {routing_token.name} not valid for node {from_node}")
            return False
        
        expected_target = allowed_transitions[routing_token]
        
        # Handle special cases
        if from_node_enum == NodeName.CLASSIFY_INTENT and routing_token == RoutingToken.CLASSIFIED:
            # Intent-specific routing override
            if context and 'intent' in context:
                intent = context['intent']
                if isinstance(intent, Intent) and intent in RoutingMatrix.INTENT_ROUTING_OVERRIDES:
                    expected_target = RoutingMatrix.INTENT_ROUTING_OVERRIDES[intent]
        
        elif from_node_enum == NodeName.HANDLE_CONFIRMATION and routing_token == RoutingToken.CONFIRMED:
            # Confirmation context routing
            if context and 'confirmation_type' in context:
                conf_type = context['confirmation_type']
                if isinstance(conf_type, ConfirmationType) and conf_type in RoutingMatrix.CONFIRMATION_CONTEXT_ROUTING:
                    expected_target = RoutingMatrix.CONFIRMATION_CONTEXT_ROUTING[conf_type][True]
        
        # Validate transition
        if expected_target != to_node_enum:
            logger.error(f"[ROUTING] Invalid transition: {from_node} -> {to_node} via {routing_token.name}, expected {expected_target.value if expected_target else 'END'}")
            return False
        
        return True
    
    @staticmethod
    def assert_valid_transition(
        from_node: str, 
        to_node: str, 
        routing_token: RoutingToken,
        context: Optional[Dict] = None
    ) -> None:
        """
        Assert a node transition is valid, raising exception if not.
        Use this in node implementations for route enforcement.
        """
        if not RoutingValidator.validate_node_transition(from_node, to_node, routing_token, context):
            raise ValueError(
                f"Invalid route transition: {from_node} -> {to_node} via {routing_token.name}. "
                f"Check routing_map.py for allowed transitions."
            )
    
    @staticmethod
    def get_allowed_tokens_for_node(node_name: str) -> List[RoutingToken]:
        """Get all valid routing tokens for a given node."""
        try:
            node_enum = NodeName(node_name)
            return list(RoutingMatrix.ROUTING_TABLE.get(node_enum, {}).keys())
        except ValueError:
            return []
    
    @staticmethod
    def get_possible_next_nodes(node_name: str) -> List[str]:
        """Get all possible next nodes from a given node."""
        try:
            node_enum = NodeName(node_name)
            transitions = RoutingMatrix.ROUTING_TABLE.get(node_enum, {})
            next_nodes = []
            for next_node in transitions.values():
                if next_node:
                    next_nodes.append(next_node.value)
                else:
                    next_nodes.append("END")
            return list(set(next_nodes))  # Remove duplicates
        except ValueError:
            return []


class GraphRouteEnforcer:
    """
    Runtime route enforcement for conversation graph nodes.
    Integrates with existing graph implementation to prevent invalid transitions.
    """
    
    def __init__(self):
        # Validate routing table on startup
        errors = RoutingValidator.validate_routing_table()
        if errors:
            error_msg = "Routing table validation failed: " + "; ".join(errors)
            logger.error(f"[ROUTING] {error_msg}")
            raise ValueError(error_msg)
        
        logger.info("[ROUTING] ✅ Routing table validation passed")
    
    def enforce_route_decision(
        self,
        current_node: str,
        next_node: str,
        routing_token: RoutingToken,
        context: Optional[Dict] = None
    ) -> str:
        """
        Enforce routing decision and return validated next node.
        
        Args:
            current_node: Current node name
            next_node: Proposed next node name  
            routing_token: Token justifying the transition
            context: Additional routing context
            
        Returns:
            Validated next node name
            
        Raises:
            ValueError: If route is invalid
        """
        # Validate the transition
        RoutingValidator.assert_valid_transition(current_node, next_node, routing_token, context)
        
        # Log the validated transition
        logger.debug(f"[ROUTING] ✅ Validated route: {current_node} -> {next_node} via {routing_token.name}")
        
        return next_node
    
    def get_routing_info(self, node_name: str) -> Dict[str, Any]:
        """Get routing information for debugging and documentation."""
        return {
            'node': node_name,
            'allowed_tokens': [t.name for t in RoutingValidator.get_allowed_tokens_for_node(node_name)],
            'possible_next_nodes': RoutingValidator.get_possible_next_nodes(node_name),
        }


# ===== MODULE EXPORTS =====

__all__ = [
    'RoutingToken',
    'NodeName', 
    'RoutingMatrix',
    'RoutingValidator',
    'GraphRouteEnforcer'
]


# ===== INITIALIZATION =====

# Create global route enforcer instance for use by graph nodes
route_enforcer = GraphRouteEnforcer()

logger.info("[ROUTING] 🗺️ Centralized routing map initialized successfully")
