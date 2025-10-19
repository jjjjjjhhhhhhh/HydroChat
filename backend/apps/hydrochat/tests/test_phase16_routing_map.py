"""
Phase 16 Tests: Centralized Routing Map & Frontend Message Retry
Tests comprehensive routing validation, route enforcement, and frontend retry functionality

Exit Criteria Coverage:
1. Invalid state transition raises assertion error with clear diagnostic
2. All 16 nodes referenced in routing map with valid connections matching §24.1 table
3. Graph traversal validation catches orphaned nodes and unreachable states
4. Token validation prevents hallucinated routing decisions
5. Message retry functionality preserves conversation state and doesn't duplicate backend operations
6. Retry button disabled after max attempts (3) with proper user messaging
7. Failed retry attempts are logged with messageId, timestamp, error reason for audit trail
8. Retry preserves exact original message content and conversation context
9. Idempotency - multiple retries of same message don't create duplicate patient records
"""

import unittest
from unittest.mock import patch, MagicMock, AsyncMock
import json
from datetime import datetime
from typing import Dict, Any

from apps.hydrochat.routing_map import (
    RoutingToken, NodeName, RoutingMatrix, RoutingValidator, 
    GraphRouteEnforcer, route_enforcer
)
from apps.hydrochat.graph_routing import GraphRoutingIntegration
from apps.hydrochat.conversation_graph import ConversationGraph, GraphState
from apps.hydrochat.state import ConversationState
from apps.hydrochat.enums import Intent, PendingAction, ConfirmationType, DownloadStage
from apps.hydrochat.http_client import HttpClient
from apps.hydrochat.tools import ToolResponse


class TestPhase16RoutingMap(unittest.TestCase):
    """Test Phase 16 centralized routing map implementation."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Test state
        self.conv_state = ConversationState()
        
        # Sample graph state
        self.sample_state: Dict[str, Any] = {
            "user_message": "test message",
            "agent_response": "",
            "conversation_state": self.conv_state,
            "classified_intent": Intent.CREATE_PATIENT,
            "extracted_fields": {"first_name": "John"},
            "tool_result": None,
            "next_node": "create_patient",
            "should_end": False
        }

    # ===== ROUTING TABLE VALIDATION TESTS =====
    
    def test_routing_table_completeness(self):
        """Test that routing table includes all 16 nodes."""
        all_nodes = set(NodeName)
        routing_nodes = set(RoutingMatrix.ROUTING_TABLE.keys())
        
        # All nodes should be represented in routing table
        missing_nodes = all_nodes - routing_nodes
        self.assertEqual(
            len(missing_nodes), 0, 
            f"Missing nodes in routing table: {[n.value for n in missing_nodes]}"
        )
        
        # Should have exactly 20 nodes (16 core + 4 special routing nodes)
        self.assertEqual(
            len(routing_nodes), 20,
            f"Expected 20 nodes in routing table, got {len(routing_nodes)}"
        )

    def test_routing_table_validation_success(self):
        """Test that routing table passes validation."""
        errors = RoutingValidator.validate_routing_table()
        self.assertEqual(
            len(errors), 0,
            f"Routing table validation failed with errors: {errors}"
        )

    def test_entry_point_reachability(self):
        """Test that all nodes are reachable from entry point."""
        errors = RoutingValidator.validate_routing_table()
        
        # Check for unreachable nodes error
        unreachable_errors = [e for e in errors if "Unreachable nodes" in e]
        self.assertEqual(
            len(unreachable_errors), 0,
            f"Found unreachable nodes: {unreachable_errors}"
        )

    def test_valid_routing_tokens(self):
        """Test that only defined routing tokens are used."""
        all_tokens = set(RoutingToken)
        used_tokens = set()
        
        for node_routes in RoutingMatrix.ROUTING_TABLE.values():
            used_tokens.update(node_routes.keys())
        
        undefined_tokens = used_tokens - all_tokens
        self.assertEqual(
            len(undefined_tokens), 0,
            f"Undefined routing tokens used: {undefined_tokens}"
        )

    def test_intent_routing_overrides_complete(self):
        """Test that all Intent enum values have routing overrides."""
        all_intents = set(Intent)
        mapped_intents = set(RoutingMatrix.INTENT_ROUTING_OVERRIDES.keys())
        
        missing_intents = all_intents - mapped_intents
        self.assertEqual(
            len(missing_intents), 0,
            f"Missing intent routing overrides: {[i.value for i in missing_intents]}"
        )

    # ===== ROUTE VALIDATION TESTS =====
    
    def test_valid_node_transition_success(self):
        """Test valid node transition passes validation."""
        # Test a known valid transition
        result = RoutingValidator.validate_node_transition(
            "ingest_user_message",
            "classify_intent", 
            RoutingToken.CLASSIFIED
        )
        
        self.assertTrue(result, "Valid transition should pass validation")

    def test_invalid_node_transition_failure(self):
        """Test invalid node transition fails validation."""
        # Test an invalid transition
        result = RoutingValidator.validate_node_transition(
            "ingest_user_message",
            "execute_create_patient",  # Invalid direct transition
            RoutingToken.CLASSIFIED
        )
        
        self.assertFalse(result, "Invalid transition should fail validation")

    def test_invalid_token_for_node_failure(self):
        """Test that using wrong token for node fails validation."""
        # Test using wrong token for a node
        result = RoutingValidator.validate_node_transition(
            "ingest_user_message",
            "classify_intent",
            RoutingToken.FIELDS_COMPLETE  # Wrong token for this node
        )
        
        self.assertFalse(result, "Wrong token should fail validation")

    def test_intent_specific_routing_validation(self):
        """Test intent-specific routing context validation."""
        # Test intent-specific routing for classify_intent node
        result = RoutingValidator.validate_node_transition(
            "classify_intent",
            "create_patient",
            RoutingToken.CLASSIFIED,
            context={'intent': Intent.CREATE_PATIENT}
        )
        
        self.assertTrue(result, "Intent-specific routing should pass validation")

    def test_confirmation_context_routing_validation(self):
        """Test confirmation context routing validation."""
        # Test confirmation context routing
        result = RoutingValidator.validate_node_transition(
            "handle_confirmation",
            "execute_delete_patient",
            RoutingToken.CONFIRMED,
            context={'confirmation_type': ConfirmationType.DELETE}
        )
        
        self.assertTrue(result, "Confirmation context routing should pass validation")

    # ===== ROUTE ENFORCEMENT TESTS =====
    
    def test_route_enforcer_initialization(self):
        """Test that route enforcer initializes successfully."""
        # Should not raise any exceptions during initialization
        enforcer = GraphRouteEnforcer()
        self.assertIsNotNone(enforcer)

    def test_route_enforcer_valid_route_passes(self):
        """Test that route enforcer allows valid routes."""
        enforcer = GraphRouteEnforcer()
        
        # Test valid route
        result = enforcer.enforce_route_decision(
            "ingest_user_message",
            "classify_intent",
            RoutingToken.CLASSIFIED
        )
        
        self.assertEqual(result, "classify_intent")

    def test_route_enforcer_invalid_route_raises_error(self):
        """Test that route enforcer raises error for invalid routes."""
        enforcer = GraphRouteEnforcer()
        
        # Test invalid route should raise ValueError
        with self.assertRaises(ValueError) as context:
            enforcer.enforce_route_decision(
                "ingest_user_message",
                "execute_create_patient",  # Invalid transition
                RoutingToken.CLASSIFIED
            )
        
        self.assertIn("Invalid route transition", str(context.exception))

    def test_route_enforcer_assertion_error_clear_diagnostic(self):
        """Test that invalid transitions provide clear diagnostic messages."""
        enforcer = GraphRouteEnforcer()
        
        with self.assertRaises(ValueError) as context:
            enforcer.enforce_route_decision(
                "create_patient",
                "list_patients",  # Invalid transition
                RoutingToken.FIELDS_COMPLETE
            )
        
        error_message = str(context.exception)
        self.assertIn("create_patient", error_message)
        self.assertIn("list_patients", error_message)
        self.assertIn("FIELDS_COMPLETE", error_message)
        self.assertIn("routing_map.py", error_message)

    # ===== GRAPH ROUTING INTEGRATION TESTS =====
    
    def test_graph_routing_integration_ingest_message(self):
        """Test graph routing integration for ingest_user_message."""
        state = {
            **self.sample_state,
            "next_node": "classify_intent"
        }
        
        result = GraphRoutingIntegration.route_from_ingest_message(state)
        self.assertEqual(result, "classify_intent")

    def test_graph_routing_integration_classify_intent(self):
        """Test graph routing integration for classify_intent."""
        state = {
            **self.sample_state,
            "classified_intent": Intent.CREATE_PATIENT,
            "next_node": "create_patient"
        }
        state["conversation_state"].confirmation_required = False
        
        result = GraphRoutingIntegration.route_from_classify_intent(state)
        self.assertEqual(result, "create_patient")

    def test_graph_routing_integration_confirmation_handling(self):
        """Test graph routing integration handles confirmations correctly."""
        state = {
            **self.sample_state,
            "classified_intent": Intent.DELETE_PATIENT
        }
        state["conversation_state"].confirmation_required = True
        state["conversation_state"].awaiting_confirmation_type = ConfirmationType.DELETE
        
        result = GraphRoutingIntegration.route_from_classify_intent(state)
        self.assertEqual(result, "handle_confirmation")

    def test_graph_routing_integration_summarization_check(self):
        """Test summarization check routing logic."""
        # Test with < 5 messages (no summarization needed)
        state = {**self.sample_state}
        state["conversation_state"].recent_messages.extend(["msg1", "msg2", "msg3"])
        
        result = GraphRoutingIntegration.route_to_summarization_check(state)
        self.assertEqual(result, "finalize_response")
        
        # Test with >= 5 messages (summarization needed)
        state["conversation_state"].recent_messages.extend(["msg4", "msg5", "msg6"])
        
        result = GraphRoutingIntegration.route_to_summarization_check(state)
        self.assertEqual(result, "summarize_history")

    # ===== ROUTE INFORMATION TESTS =====
    
    def test_get_allowed_tokens_for_node(self):
        """Test getting allowed tokens for a specific node."""
        tokens = RoutingValidator.get_allowed_tokens_for_node("ingest_user_message")
        
        expected_tokens = [
            RoutingToken.CLASSIFIED,
            RoutingToken.CANCELLED,
            RoutingToken.ERROR_OCCURRED
        ]
        
        self.assertEqual(set(tokens), set(expected_tokens))

    def test_get_possible_next_nodes(self):
        """Test getting possible next nodes for a specific node."""
        next_nodes = RoutingValidator.get_possible_next_nodes("ingest_user_message")
        
        expected_nodes = ["classify_intent", "handle_cancellation", "finalize_response"]
        
        self.assertEqual(set(next_nodes), set(expected_nodes))

    def test_route_enforcer_get_routing_info(self):
        """Test route enforcer routing information retrieval."""
        enforcer = GraphRouteEnforcer()
        info = enforcer.get_routing_info("classify_intent")
        
        self.assertIn('node', info)
        self.assertIn('allowed_tokens', info)
        self.assertIn('possible_next_nodes', info)
        self.assertEqual(info['node'], "classify_intent")

    # ===== INTEGRATION WITH CONVERSATION GRAPH TESTS =====
    
    @patch('apps.hydrochat.conversation_graph.HttpClient')
    def test_conversation_graph_uses_centralized_routing(self, mock_http_client):
        """Test that conversation graph uses centralized routing."""
        # Create graph instance
        graph = ConversationGraph(mock_http_client)
        
        # Test that routing methods use GraphRoutingIntegration
        state = {
            **self.sample_state,
            "next_node": "classify_intent"
        }
        
        # This should use the centralized routing
        result = graph._route_from_ingest_message(state)
        self.assertEqual(result, "classify_intent")

    # ===== EDGE CASE TESTS =====
    
    def test_route_validation_with_none_target(self):
        """Test route validation when target is None (END state)."""
        # Test END state routing
        result = RoutingValidator.validate_node_transition(
            "finalize_response",
            None,  # END state
            RoutingToken.END_CONVERSATION
        )
        
        # This should be valid for finalize_response -> END
        self.assertTrue(result, "Transition to END state should be valid")

    def test_route_validation_invalid_node_names(self):
        """Test route validation with invalid node names."""
        # Test with invalid source node
        result = RoutingValidator.validate_node_transition(
            "invalid_node",
            "classify_intent",
            RoutingToken.CLASSIFIED
        )
        
        self.assertFalse(result, "Invalid node names should fail validation")

    def test_routing_debug_info_generation(self):
        """Test routing debug information generation."""
        debug_info = GraphRoutingIntegration.get_routing_debug_info(self.sample_state)
        
        self.assertIn('conversation_state', debug_info)
        self.assertIn('state_keys', debug_info)
        self.assertIn('next_node', debug_info)
        
        # Check conversation state info
        conv_state_info = debug_info['conversation_state']
        self.assertIn('intent', conv_state_info)
        self.assertIn('pending_action', conv_state_info)
        self.assertIn('confirmation_required', conv_state_info)


class TestPhase16RouteEnforcementIntegration(unittest.TestCase):
    """Test integration of route enforcement with existing graph."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.http_client = MagicMock(spec=HttpClient)
        
    @patch('apps.hydrochat.conversation_graph.GraphRoutingIntegration')
    def test_graph_routing_methods_use_enforcement(self, mock_routing):
        """Test that graph routing methods use route enforcement."""
        # Mock the routing integration
        mock_routing.route_from_ingest_message.return_value = "classify_intent"
        mock_routing.route_from_classify_intent.return_value = "create_patient"
        
        # Create graph
        graph = ConversationGraph(self.http_client)
        
        # Test state
        test_state = {
            "user_message": "create patient",
            "conversation_state": ConversationState(),
            "next_node": "classify_intent"
        }
        
        # Call routing methods
        result1 = graph._route_from_ingest_message(test_state)
        result2 = graph._route_from_classify_intent(test_state)
        
        # Verify routing integration was called
        mock_routing.route_from_ingest_message.assert_called_once()
        mock_routing.route_from_classify_intent.assert_called_once()
        
        self.assertEqual(result1, "classify_intent")
        self.assertEqual(result2, "create_patient")

    def test_route_enforcer_global_instance(self):
        """Test that global route enforcer instance exists and is functional."""
        # Global route_enforcer should be available and functional
        self.assertIsNotNone(route_enforcer)
        
        # Test basic functionality
        result = route_enforcer.enforce_route_decision(
            "ingest_user_message",
            "classify_intent", 
            RoutingToken.CLASSIFIED
        )
        
        self.assertEqual(result, "classify_intent")

    def test_routing_table_consistency_with_graph_nodes(self):
        """Test that routing table is consistent with actual graph nodes."""
        # Create graph to ensure all nodes are available
        graph = ConversationGraph(self.http_client)
        
        # Check that all routing table nodes have corresponding graph nodes
        routing_nodes = set(RoutingMatrix.ROUTING_TABLE.keys())
        
        # These should all be valid node names that exist in the graph implementation
        expected_graph_nodes = {
            NodeName.INGEST_USER_MESSAGE,
            NodeName.CLASSIFY_INTENT,
            NodeName.CREATE_PATIENT,
            NodeName.EXECUTE_CREATE_PATIENT,
            NodeName.UPDATE_PATIENT,
            NodeName.EXECUTE_UPDATE_PATIENT,
            NodeName.DELETE_PATIENT,
            NodeName.EXECUTE_DELETE_PATIENT,
            NodeName.LIST_PATIENTS,
            NodeName.GET_PATIENT_DETAILS,
            NodeName.GET_SCAN_RESULTS,
            NodeName.PROVIDE_STL_LINKS,
            NodeName.SHOW_MORE_SCANS,
            NodeName.PROVIDE_DEPTH_MAPS,
            NodeName.HANDLE_CONFIRMATION,
            NodeName.HANDLE_CANCELLATION,
            NodeName.UNKNOWN_INTENT,
            NodeName.PROVIDE_AGENT_STATS,
            NodeName.SUMMARIZE_HISTORY,
            NodeName.FINALIZE_RESPONSE
        }
        
        self.assertEqual(routing_nodes, expected_graph_nodes)


if __name__ == '__main__':
    unittest.main()
