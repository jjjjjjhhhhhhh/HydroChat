# Phase 8 Tests: Error Handling & Validation Loops
# Tests for 400 validation parsing, 404 enhanced handling, clarification loop guards, and cancellation

import pytest
from unittest.mock import AsyncMock, MagicMock
from collections import deque

from apps.hydrochat.conversation_graph import ConversationGraph, ConversationGraphNodes, GraphState  
from apps.hydrochat.state import ConversationState
from apps.hydrochat.enums import Intent, PendingAction, ConfirmationType, DownloadStage
from apps.hydrochat.tools import ToolManager, ToolResponse
from apps.hydrochat.http_client import HttpClient
from apps.hydrochat.name_cache import NameResolutionCache


class TestPhase8ErrorHandling:
    """Test Phase 8 error handling and validation loop enhancements."""

    @pytest.fixture
    def http_client(self):
        """Mock HTTP client for testing."""
        return MagicMock(spec=HttpClient)

    @pytest.fixture 
    def tool_manager(self, http_client):
        """Mock tool manager for testing."""
        return MagicMock(spec=ToolManager)

    @pytest.fixture
    def name_cache(self):
        """Mock name resolution cache for testing."""
        return MagicMock(spec=NameResolutionCache)

    @pytest.fixture
    def nodes(self, tool_manager, name_cache):
        """Create conversation nodes for testing."""
        return ConversationGraphNodes(tool_manager, name_cache)

    @pytest.fixture
    def conversation_state(self):
        """Create fresh conversation state for testing."""
        return ConversationState()

    def test_cancel_intent_classification(self, nodes, conversation_state):
        """Test that cancellation commands are properly classified and handled."""
        from apps.hydrochat.intent_classifier import classify_intent
        
        # Test various cancellation phrases
        cancel_phrases = ["cancel", "abort", "stop", "quit", "exit", "reset"]
        for phrase in cancel_phrases:
            intent = classify_intent(phrase)
            assert intent == Intent.CANCEL, f"Failed to classify '{phrase}' as CANCEL intent"
            
        # Test in context
        intent = classify_intent("cancel this operation")
        assert intent == Intent.CANCEL

    def test_handle_cancellation_node_with_active_workflow(self, nodes, conversation_state):
        """Test cancellation handling when there's an active workflow."""
        # Set up active workflow state
        conversation_state.pending_action = PendingAction.CREATE_PATIENT
        conversation_state.pending_fields = {"first_name", "nric"}
        conversation_state.clarification_loop_count = 1
        conversation_state.validated_fields = {"last_name": "Smith"}
        
        state = {
            "user_message": "cancel",
            "conversation_state": conversation_state
        }
        
        result = nodes.handle_cancellation_node(state)
        
        # Verify state was reset
        assert conversation_state.pending_action == PendingAction.NONE
        assert len(conversation_state.pending_fields) == 0
        assert conversation_state.clarification_loop_count == 0
        assert len(conversation_state.validated_fields) == 0
        assert not conversation_state.confirmation_required
        
        # Verify response indicates cancellation occurred
        assert "cancelled" in result["agent_response"].lower()
        assert "reset" in result["agent_response"].lower()
        assert result["should_end"] == False
        assert conversation_state.metrics['aborted_ops'] == 1

    def test_handle_cancellation_node_no_active_workflow(self, nodes, conversation_state):
        """Test cancellation handling when there's no active workflow."""
        # Ensure clean state
        assert conversation_state.pending_action == PendingAction.NONE
        assert len(conversation_state.pending_fields) == 0
        
        state = {
            "user_message": "cancel", 
            "conversation_state": conversation_state
        }
        
        result = nodes.handle_cancellation_node(state)
        
        # Verify appropriate response for no active workflow
        assert "no active operation" in result["agent_response"].lower()
        assert result["should_end"] == False
        assert conversation_state.metrics['aborted_ops'] == 0

    def test_clarification_loop_guard_create_patient(self, nodes, conversation_state):
        """Test clarification loop guard prevents infinite loops during patient creation."""
        # Set up state with existing clarification attempt
        conversation_state.clarification_loop_count = 1
        conversation_state.validated_fields = {"first_name": "John"}  # Missing last_name and nric
        
        state = {
            "user_message": "create patient",
            "conversation_state": conversation_state,
            "extracted_fields": {}
        }
        
        result = nodes.create_patient_node(state)
        
        # Verify loop guard triggered
        assert "taking too long" in result["agent_response"].lower()
        assert "cancel" in result["agent_response"].lower()
        assert result["next_node"] == "end"
        assert result["should_end"] == False

    def test_400_validation_error_handling_create_patient(self, nodes, conversation_state, tool_manager):
        """Test 400 validation error parsing and field repopulation for patient creation."""
        # Set up validated fields
        conversation_state.validated_fields = {
            "first_name": "John",
            "last_name": "Doe", 
            "nric": "INVALIDNRIC"  # This will cause validation error
        }
        
        # Mock tool response with 400 validation error
        tool_response = ToolResponse(
            success=False,
            error="nric: Invalid NRIC format",
            status_code=400,
            validation_errors={"nric": ["Invalid NRIC format", "Must be exactly 9 characters"]}
        )
        tool_manager.execute_tool.return_value = tool_response
        
        state = {
            "user_message": "create patient John Doe INVALIDNRIC",
            "conversation_state": conversation_state
        }
        
        result = nodes.execute_create_patient_node(state)
        
        # Verify validation error handling
        assert not result["tool_result"].success
        assert result["next_node"] == "create_patient"  # Routes back for correction
        assert "correct the following issues" in result["agent_response"]
        assert "nric: Invalid NRIC format" in result["agent_response"]
        
        # Verify pending fields repopulated
        assert "nric" in conversation_state.pending_fields

    def test_400_validation_error_handling_update_patient(self, nodes, conversation_state, tool_manager):
        """Test 400 validation error parsing and field repopulation for patient update."""
        # Set up validated fields for update
        conversation_state.validated_fields = {
            "patient_id": 5,
            "contact_no": "invalid_contact"  # This will cause validation error
        }
        
        # Mock tool response with 400 validation error
        tool_response = ToolResponse(
            success=False,
            error="contact_no: Invalid contact number format", 
            status_code=400,
            validation_errors={"contact_no": ["Must contain only digits, +, -, and spaces"]}
        )
        tool_manager.execute_tool.return_value = tool_response
        
        state = {
            "user_message": "update patient 5 contact invalid_contact",
            "conversation_state": conversation_state
        }
        
        result = nodes.execute_update_patient_node(state)
        
        # Verify validation error handling
        assert not result["tool_result"].success
        assert result["next_node"] == "update_patient"  # Routes back for correction
        assert "correct the following issues" in result["agent_response"]
        assert "contact_no:" in result["agent_response"]
        
        # Verify pending fields repopulated and patient ID preserved
        assert "contact_no" in conversation_state.pending_fields
        assert conversation_state.validated_fields.get("patient_id") == 5

    def test_enhanced_404_handling_get_patient_details(self, nodes, conversation_state, tool_manager):
        """Test enhanced 404 error handling with helpful options."""
        conversation_state.validated_fields = {"patient_id": 999}
        
        # Mock tool response with 404 error
        tool_response = ToolResponse(
            success=False,
            error="Patient with ID 999 not found",
            status_code=404
        )
        tool_manager.execute_tool.return_value = tool_response
        
        state = {
            "user_message": "show patient 999",
            "conversation_state": conversation_state,
            "extracted_fields": {}
        }
        
        result = nodes.get_patient_details_node(state)
        
        # Verify enhanced 404 response
        assert "Patient not found" in result["agent_response"]
        assert "Helpful options" in result["agent_response"] 
        assert "list patients" in result["agent_response"]
        assert "cancel" in result["agent_response"]
        assert result["should_end"] == False

    def test_enhanced_404_handling_get_scan_results(self, nodes, conversation_state, tool_manager):
        """Test enhanced 404 error handling for scan results."""
        conversation_state.validated_fields = {"patient_id": 999}
        
        # Mock tool response with 404 error
        tool_response = ToolResponse(
            success=False,
            error="Patient with ID 999 not found",
            status_code=404
        )
        tool_manager.execute_tool.return_value = tool_response
        
        state = {
            "user_message": "show scans for patient 999", 
            "conversation_state": conversation_state,
            "extracted_fields": {}
        }
        
        result = nodes.get_scan_results_node(state)
        
        # Verify enhanced 404 response
        assert "Patient ID 999 not found" in result["agent_response"]
        assert "Helpful options" in result["agent_response"]
        assert "list patients" in result["agent_response"]
        assert "cancel" in result["agent_response"]
        assert conversation_state.pending_action == PendingAction.NONE  # State reset

    def test_validation_error_parsing_multiple_fields(self):
        """Test parsing of validation errors with multiple field issues."""
        from apps.hydrochat.tools import PatientTools
        from unittest.mock import MagicMock
        
        # Mock HTTP response with multiple validation errors
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "nric": ["This field is required.", "Invalid format."],
            "first_name": ["Ensure this field has at most 50 characters."],
            "contact_no": ["Invalid contact number format"]
        }
        
        tools = PatientTools(MagicMock())
        result = tools._parse_400_validation_error(mock_response)
        
        # Verify parsing results
        assert "nric: This field is required., Invalid format." in result['summary']
        assert "first_name: Ensure this field has at most 50 characters." in result['summary']
        assert "contact_no: Invalid contact number format" in result['summary']
        
        assert result['field_errors']['nric'] == ["This field is required.", "Invalid format."]
        assert result['field_errors']['first_name'] == ["Ensure this field has at most 50 characters."]
        assert result['field_errors']['contact_no'] == ["Invalid contact number format"]

    def test_validation_error_parsing_malformed_response(self):
        """Test graceful handling of malformed validation error responses."""
        from apps.hydrochat.tools import PatientTools
        from unittest.mock import MagicMock
        
        # Mock HTTP response with malformed JSON
        mock_response = MagicMock()
        mock_response.json.side_effect = Exception("Invalid JSON")
        
        tools = PatientTools(MagicMock())
        result = tools._parse_400_validation_error(mock_response)
        
        # Verify graceful fallback
        assert result['summary'] == "Validation error (unable to parse details)"
        assert result['field_errors'] == {}

    def test_cancel_intent_routing_in_workflow(self, nodes, name_cache, tool_manager, http_client):
        """Test that CANCEL intent is properly routed to handle_cancellation node."""
        conversation_graph = ConversationGraph(http_client)
        
        # Test intent routing through nodes instance
        next_node = nodes._determine_next_node_from_intent(Intent.CANCEL)
        assert next_node == "handle_cancellation"

    def test_clarification_loop_guard_threshold(self, nodes, conversation_state):
        """Test that clarification loop guard activates at the correct threshold."""
        # Test that it allows first clarification
        conversation_state.clarification_loop_count = 0
        conversation_state.validated_fields = {"first_name": "John"}  # Missing required fields
        
        state = {
            "user_message": "create patient John",
            "conversation_state": conversation_state,
            "extracted_fields": {}
        }
        
        result = nodes.create_patient_node(state)
        
        # Should proceed with clarification, not trigger guard
        assert "taking too long" not in result["agent_response"].lower()
        assert "Please provide" in result["agent_response"]  # Normal clarification prompt
        
        # Test that it blocks second clarification  
        conversation_state.clarification_loop_count = 1
        
        result = nodes.create_patient_node(state)
        
        # Should trigger guard
        assert "taking too long" in result["agent_response"].lower()
        assert "cancel" in result["agent_response"].lower()

    def test_tool_response_enhanced_fields(self):
        """Test that enhanced ToolResponse fields work correctly."""
        # Test successful response
        success_response = ToolResponse(
            success=True,
            data={"id": 1, "name": "John Doe"},
            nric_masked=True
        )
        assert success_response.status_code is None
        assert success_response.validation_errors is None
        assert success_response.retryable == False
        
        # Test validation error response
        error_response = ToolResponse(
            success=False,
            error="Validation failed",
            status_code=400,
            validation_errors={"nric": ["Invalid format"]},
            retryable=False
        )
        assert error_response.status_code == 400
        assert error_response.validation_errors == {"nric": ["Invalid format"]}
        assert error_response.retryable == False
