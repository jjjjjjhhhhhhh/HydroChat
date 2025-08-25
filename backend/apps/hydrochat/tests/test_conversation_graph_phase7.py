# Test suite for HydroChat Phase 7 - Full Node Inventory Completion
# Tests new conversation nodes: update, delete, get details, scan results with STL confirmation

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from apps.hydrochat.conversation_graph import ConversationGraphNodes, GraphState
from apps.hydrochat.enums import Intent, PendingAction, ConfirmationType, DownloadStage
from apps.hydrochat.state import ConversationState
from apps.hydrochat.tools import ToolResponse


class TestPhase7Nodes:
    """Test Phase 7 conversation nodes."""
    
    @pytest.fixture
    def mock_tool_manager(self):
        """Mock tool manager for testing."""
        return MagicMock()
    
    @pytest.fixture
    def mock_name_cache(self):
        """Mock name cache for testing."""
        return MagicMock()
    
    @pytest.fixture
    def nodes(self, mock_tool_manager, mock_name_cache):
        """Conversation graph nodes instance with mocked dependencies."""
        return ConversationGraphNodes(mock_tool_manager, mock_name_cache)

    @pytest.fixture
    def base_state(self):
        """Base GraphState for testing."""
        return {
            "user_message": "",
            "agent_response": "",
            "conversation_state": ConversationState(),
            "classified_intent": None,
            "extracted_fields": {},
            "tool_result": None,
            "next_node": None,
            "should_end": False
        }


class TestGetPatientDetailsNode:
    """Test get_patient_details_node functionality."""
    
    @pytest.fixture
    def mock_tool_manager(self):
        return MagicMock()
    
    @pytest.fixture
    def mock_name_cache(self):
        return MagicMock()
    
    @pytest.fixture
    def nodes(self, mock_tool_manager, mock_name_cache):
        return ConversationGraphNodes(mock_tool_manager, mock_name_cache)

    @pytest.fixture
    def base_state(self):
        return {
            "user_message": "show patient 5",
            "agent_response": "",
            "conversation_state": ConversationState(),
            "classified_intent": Intent.GET_PATIENT_DETAILS,
            "extracted_fields": {"patient_id": 5},
            "tool_result": None,
            "next_node": None,
            "should_end": False
        }

    def test_get_patient_details_success(self, nodes, base_state):
        """Test successful patient details retrieval."""
        # Mock successful tool execution
        patient_data = {
            "id": 5,
            "first_name": "John",
            "last_name": "Doe", 
            "nric": "S1234567A",
            "date_of_birth": "1990-01-01",
            "contact_no": "+6512345678",
            "details": "Regular patient"
        }
        success_result = ToolResponse(success=True, data=patient_data)
        nodes.tool_manager.execute_tool.return_value = success_result
        
        # Execute node
        result = nodes.get_patient_details_node(base_state)
        
        # Verify results
        assert result["tool_result"].success is True
        assert "Patient Details" in result["agent_response"]
        assert "John Doe" in result["agent_response"]
        assert "S******7A" in result["agent_response"]  # Masked NRIC
        assert "1990-01-01" in result["agent_response"]
        assert "+6512345678" in result["agent_response"]
        assert result["should_end"] is True

    def test_get_patient_details_no_id_provided(self, nodes, base_state):
        """Test patient details request without patient ID."""
        # Remove patient_id from extracted fields
        base_state["extracted_fields"] = {}
        
        # Execute node
        result = nodes.get_patient_details_node(base_state)
        
        # Verify results
        assert "Please specify which patient" in result["agent_response"]
        assert "patient 5" in result["agent_response"]
        assert result["should_end"] is False

    def test_get_patient_details_not_found(self, nodes, base_state):
        """Test patient details for non-existent patient."""
        # Mock failed tool execution (404)
        failure_result = ToolResponse(success=False, error="Patient not found (404)")
        nodes.tool_manager.execute_tool.return_value = failure_result
        
        # Execute node
        result = nodes.get_patient_details_node(base_state)
        
        # Verify results
        assert result["tool_result"].success is False
        assert "Failed to get patient details" in result["agent_response"]
        assert "Would you like to see a list" in result["agent_response"]
        assert result["should_end"] is False

    def test_get_patient_details_handles_list_response(self, nodes, base_state):
        """Test handling when tool returns list instead of single patient."""
        # Mock tool returning list format (edge case)
        patient_list = [{
            "id": 5,
            "first_name": "John",
            "last_name": "Doe",
            "nric": "S1234567A"
        }]
        success_result = ToolResponse(success=True, data=patient_list)
        nodes.tool_manager.execute_tool.return_value = success_result
        
        # Execute node
        result = nodes.get_patient_details_node(base_state)
        
        # Verify results - should handle list and take first item
        assert result["tool_result"].success is True
        assert "John Doe" in result["agent_response"]
        assert result["should_end"] is True


class TestUpdatePatientNode:
    """Test update_patient_node functionality."""
    
    @pytest.fixture
    def mock_tool_manager(self):
        return MagicMock()
    
    @pytest.fixture
    def mock_name_cache(self):
        return MagicMock()
    
    @pytest.fixture
    def nodes(self, mock_tool_manager, mock_name_cache):
        return ConversationGraphNodes(mock_tool_manager, mock_name_cache)

    @pytest.fixture
    def base_state(self):
        return {
            "user_message": "update patient 5 contact 91234567",
            "agent_response": "",
            "conversation_state": ConversationState(),
            "classified_intent": Intent.UPDATE_PATIENT,
            "extracted_fields": {"patient_id": 5, "contact_no": "91234567"},
            "tool_result": None,
            "next_node": None,
            "should_end": False
        }

    def test_update_patient_with_fields(self, nodes, base_state):
        """Test update patient with provided fields."""
        # Execute node
        result = nodes.update_patient_node(base_state)
        
        # Verify results
        assert result["conversation_state"].pending_action == PendingAction.UPDATE_PATIENT
        assert result["conversation_state"].validated_fields["patient_id"] == 5
        assert result["conversation_state"].validated_fields["contact_no"] == "91234567"
        assert result["next_node"] == "execute_update_patient"

    def test_update_patient_no_id_provided(self, nodes, base_state):
        """Test update patient without patient ID."""
        # Remove patient_id from extracted fields
        base_state["extracted_fields"] = {"contact_no": "91234567"}
        
        # Execute node
        result = nodes.update_patient_node(base_state)
        
        # Verify results
        assert "Please specify which patient" in result["agent_response"]
        assert "update patient 5" in result["agent_response"]
        assert result["should_end"] is False

    def test_update_patient_no_fields_to_update(self, nodes, base_state):
        """Test update patient without any update fields."""
        # Only provide patient_id, no update fields
        base_state["extracted_fields"] = {"patient_id": 5}
        
        # Execute node
        result = nodes.update_patient_node(base_state)
        
        # Verify results
        assert "What would you like to update" in result["agent_response"]
        assert "First name or last name" in result["agent_response"]
        assert "Contact number" in result["agent_response"]
        assert result["should_end"] is False


class TestExecuteUpdatePatientNode:
    """Test execute_update_patient_node functionality."""
    
    @pytest.fixture
    def mock_tool_manager(self):
        return MagicMock()
    
    @pytest.fixture
    def mock_name_cache(self):
        return MagicMock()
    
    @pytest.fixture
    def nodes(self, mock_tool_manager, mock_name_cache):
        return ConversationGraphNodes(mock_tool_manager, mock_name_cache)

    @pytest.fixture
    def base_state(self):
        conv_state = ConversationState()
        conv_state.validated_fields = {
            "patient_id": 5,
            "contact_no": "91234567",
            "first_name": "John"
        }
        return {
            "user_message": "",
            "agent_response": "",
            "conversation_state": conv_state,
            "classified_intent": Intent.UPDATE_PATIENT,
            "extracted_fields": {},
            "tool_result": None,
            "next_node": None,
            "should_end": False
        }

    def test_execute_update_patient_success(self, nodes, base_state):
        """Test successful patient update execution."""
        # Mock successful tool execution
        updated_patient = {
            "id": 5,
            "first_name": "John",
            "last_name": "Doe",
            "contact_no": "91234567"
        }
        success_result = ToolResponse(success=True, data=updated_patient)
        nodes.tool_manager.execute_tool.return_value = success_result
        
        # Execute node
        result = nodes.execute_update_patient_node(base_state)
        
        # Verify results
        assert result["tool_result"].success is True
        assert "Successfully updated patient" in result["agent_response"]
        assert "John Doe" in result["agent_response"]
        assert "Contact No: 91234567" in result["agent_response"]  # Match actual format
        assert result["conversation_state"].pending_action == PendingAction.NONE
        assert len(result["conversation_state"].validated_fields) == 0
        assert result["should_end"] is True

    def test_execute_update_patient_failure(self, nodes, base_state):
        """Test failed patient update execution."""
        # Mock failed tool execution
        failure_result = ToolResponse(success=False, error="Validation error: Invalid contact number")
        nodes.tool_manager.execute_tool.return_value = failure_result
        
        # Execute node
        result = nodes.execute_update_patient_node(base_state)
        
        # Verify results
        assert result["tool_result"].success is False
        assert "Failed to update patient" in result["agent_response"]
        assert "Invalid contact number" in result["agent_response"]
        assert result["conversation_state"].pending_action == PendingAction.NONE
        assert result["should_end"] is False

    def test_execute_update_patient_handles_list_response(self, nodes, base_state):
        """Test handling when update returns list instead of single patient."""
        # Mock tool returning list format (edge case)
        updated_patient_list = [{
            "id": 5,
            "first_name": "John",
            "last_name": "Doe",
            "contact_no": "91234567"
        }]
        success_result = ToolResponse(success=True, data=updated_patient_list)
        nodes.tool_manager.execute_tool.return_value = success_result
        
        # Execute node
        result = nodes.execute_update_patient_node(base_state)
        
        # Verify results - should handle list and take first item
        assert result["tool_result"].success is True
        assert "John Doe" in result["agent_response"]
        assert result["should_end"] is True


class TestDeletePatientNode:
    """Test delete_patient_node functionality."""
    
    @pytest.fixture
    def mock_tool_manager(self):
        return MagicMock()
    
    @pytest.fixture
    def mock_name_cache(self):
        return MagicMock()
    
    @pytest.fixture
    def nodes(self, mock_tool_manager, mock_name_cache):
        return ConversationGraphNodes(mock_tool_manager, mock_name_cache)

    @pytest.fixture
    def base_state(self):
        return {
            "user_message": "delete patient 5",
            "agent_response": "",
            "conversation_state": ConversationState(),
            "classified_intent": Intent.DELETE_PATIENT,
            "extracted_fields": {"patient_id": 5},
            "tool_result": None,
            "next_node": None,
            "should_end": False
        }

    def test_delete_patient_confirmation_request(self, nodes, base_state):
        """Test delete patient requests confirmation."""
        # Execute node
        result = nodes.delete_patient_node(base_state)
        
        # Verify results
        assert result["conversation_state"].pending_action == PendingAction.DELETE_PATIENT
        assert result["conversation_state"].validated_fields["patient_id"] == 5
        assert result["conversation_state"].confirmation_required is True
        assert result["conversation_state"].awaiting_confirmation_type == ConfirmationType.DELETE
        assert "Confirmation Required" in result["agent_response"]
        assert "permanently delete" in result["agent_response"]
        assert "patient ID 5" in result["agent_response"]
        assert "yes" in result["agent_response"].lower()
        assert "no" in result["agent_response"].lower()
        assert result["should_end"] is False

    def test_delete_patient_no_id_provided(self, nodes, base_state):
        """Test delete patient without patient ID."""
        # Remove patient_id from extracted fields
        base_state["extracted_fields"] = {}
        
        # Execute node
        result = nodes.delete_patient_node(base_state)
        
        # Verify results
        assert "Please specify which patient" in result["agent_response"]
        assert "delete patient 5" in result["agent_response"]
        assert result["should_end"] is False


class TestExecuteDeletePatientNode:
    """Test execute_delete_patient_node functionality."""
    
    @pytest.fixture
    def mock_tool_manager(self):
        return MagicMock()
    
    @pytest.fixture
    def mock_name_cache(self):
        return MagicMock()
    
    @pytest.fixture
    def nodes(self, mock_tool_manager, mock_name_cache):
        return ConversationGraphNodes(mock_tool_manager, mock_name_cache)

    @pytest.fixture
    def base_state(self):
        conv_state = ConversationState()
        conv_state.validated_fields = {"patient_id": 5}
        conv_state.confirmation_required = True
        conv_state.awaiting_confirmation_type = ConfirmationType.DELETE
        return {
            "user_message": "yes",
            "agent_response": "",
            "conversation_state": conv_state,
            "classified_intent": Intent.DELETE_PATIENT,
            "extracted_fields": {},
            "tool_result": None,
            "next_node": None,
            "should_end": False
        }

    def test_execute_delete_patient_success(self, nodes, base_state):
        """Test successful patient deletion execution."""
        # Mock successful tool execution
        success_result = ToolResponse(success=True, data=None)
        nodes.tool_manager.execute_tool.return_value = success_result
        
        # Execute node
        result = nodes.execute_delete_patient_node(base_state)
        
        # Verify results
        assert result["tool_result"].success is True
        assert "Successfully deleted patient ID 5" in result["agent_response"]
        assert result["conversation_state"].pending_action == PendingAction.NONE
        assert len(result["conversation_state"].validated_fields) == 0
        assert result["conversation_state"].confirmation_required is False
        assert result["conversation_state"].awaiting_confirmation_type == ConfirmationType.NONE
        assert result["should_end"] is True

    def test_execute_delete_patient_failure(self, nodes, base_state):
        """Test failed patient deletion execution."""
        # Mock failed tool execution
        failure_result = ToolResponse(success=False, error="Cannot delete: patient has active scans")
        nodes.tool_manager.execute_tool.return_value = failure_result
        
        # Execute node
        result = nodes.execute_delete_patient_node(base_state)
        
        # Verify results
        assert result["tool_result"].success is False
        assert "Failed to delete patient" in result["agent_response"]
        assert "patient has active scans" in result["agent_response"]
        assert result["conversation_state"].pending_action == PendingAction.NONE
        assert result["should_end"] is False


class TestGetScanResultsNode:
    """Test get_scan_results_node functionality."""
    
    @pytest.fixture
    def mock_tool_manager(self):
        return MagicMock()
    
    @pytest.fixture
    def mock_name_cache(self):
        return MagicMock()
    
    @pytest.fixture
    def nodes(self, mock_tool_manager, mock_name_cache):
        return ConversationGraphNodes(mock_tool_manager, mock_name_cache)

    @pytest.fixture
    def base_state(self):
        return {
            "user_message": "show scans for patient 5",
            "agent_response": "",
            "conversation_state": ConversationState(),
            "classified_intent": Intent.GET_SCAN_RESULTS,
            "extracted_fields": {"patient_id": 5},
            "tool_result": None,
            "next_node": None,
            "should_end": False
        }

    def test_get_scan_results_success_with_stl_confirmation(self, nodes, base_state):
        """Test successful scan results retrieval with STL confirmation."""
        # Mock successful tool execution with scan results
        scan_results = [
            {
                "scan_id": "scan_001",
                "scan_date": "2024-01-15T10:30:00Z",
                "preview_image": "https://example.com/preview1.jpg",
                "stl_file": "https://example.com/scan1.stl",
                "volume_estimate": "150.5 mm³"
            },
            {
                "scan_id": "scan_002", 
                "scan_date": "2024-01-20T14:15:00Z",
                "preview_image": "https://example.com/preview2.jpg",
                "stl_file": "https://example.com/scan2.stl",
                "volume_estimate": "200.3 mm³"
            }
        ]
        success_result = ToolResponse(success=True, data=scan_results)
        nodes.tool_manager.execute_tool.return_value = success_result
        
        # Execute node
        result = nodes.get_scan_results_node(base_state)
        
        # Verify results
        assert result["tool_result"].success is True
        assert "Scan Results for Patient ID 5" in result["agent_response"]
        assert "(2 result(s))" in result["agent_response"]
        assert "Scan scan_001" in result["agent_response"]
        assert "2024-01-15" in result["agent_response"]
        assert "Volume: 150.5 mm³" in result["agent_response"]
        assert "preview1.jpg" in result["agent_response"]
        # Should NOT contain STL links in preview stage
        assert "scan1.stl" not in result["agent_response"]
        
        # Verify stage setup for STL confirmation
        assert result["conversation_state"].download_stage == DownloadStage.PREVIEW_SHOWN
        assert result["conversation_state"].confirmation_required is True
        assert result["conversation_state"].awaiting_confirmation_type == ConfirmationType.DOWNLOAD_STL
        assert "Would you like to download STL files" in result["agent_response"]
        assert result["should_end"] is False

    def test_get_scan_results_no_results(self, nodes, base_state):
        """Test scan results with no results found."""
        # Mock successful tool execution with empty results
        success_result = ToolResponse(success=True, data=[])
        nodes.tool_manager.execute_tool.return_value = success_result
        
        # Execute node
        result = nodes.get_scan_results_node(base_state)
        
        # Verify results
        assert result["tool_result"].success is True
        assert "No scan results found for patient ID 5" in result["agent_response"]
        assert result["conversation_state"].pending_action == PendingAction.NONE
        assert result["should_end"] is True

    def test_get_scan_results_no_patient_id(self, nodes, base_state):
        """Test scan results request without patient ID."""
        # Remove patient_id from extracted fields
        base_state["extracted_fields"] = {}
        
        # Execute node
        result = nodes.get_scan_results_node(base_state)
        
        # Verify results
        assert "Please specify which patient's scan results" in result["agent_response"]
        assert "show scans for patient 5" in result["agent_response"]
        assert result["should_end"] is False

    def test_get_scan_results_handles_dict_response(self, nodes, base_state):
        """Test handling when tool returns dict response (paginated)."""
        # Mock tool returning dict format (paginated response)
        scan_data = {
            "results": [
                {
                    "scan_id": "scan_001",
                    "scan_date": "2024-01-15",
                    "preview_image": "https://example.com/preview1.jpg"
                }
            ],
            "count": 1
        }
        success_result = ToolResponse(success=True, data=scan_data)
        nodes.tool_manager.execute_tool.return_value = success_result
        
        # Execute node
        result = nodes.get_scan_results_node(base_state)
        
        # Verify results - should handle dict and extract results
        assert result["tool_result"].success is True
        assert "Scan Results for Patient ID 5" in result["agent_response"]
        assert "scan_001" in result["agent_response"]


class TestProvideSTLLinksNode:
    """Test provide_stl_links_node functionality."""
    
    @pytest.fixture
    def mock_tool_manager(self):
        return MagicMock()
    
    @pytest.fixture
    def mock_name_cache(self):
        return MagicMock()
    
    @pytest.fixture
    def nodes(self, mock_tool_manager, mock_name_cache):
        return ConversationGraphNodes(mock_tool_manager, mock_name_cache)

    @pytest.fixture
    def base_state(self):
        conv_state = ConversationState()
        conv_state.scan_results_buffer = [
            {
                "scan_id": "scan_001",
                "scan_date": "2024-01-15",
                "stl_file": "https://example.com/scan1.stl"
            },
            {
                "scan_id": "scan_002",
                "scan_date": "2024-01-20", 
                "stl_file": "https://example.com/scan2.stl"
            },
            {
                "scan_id": "scan_003",
                "scan_date": "2024-01-25",
                "stl_file": None  # No STL available
            }
        ]
        conv_state.selected_patient_id = 5
        conv_state.download_stage = DownloadStage.PREVIEW_SHOWN
        conv_state.confirmation_required = True
        conv_state.awaiting_confirmation_type = ConfirmationType.DOWNLOAD_STL
        
        return {
            "user_message": "yes",
            "agent_response": "",
            "conversation_state": conv_state,
            "classified_intent": Intent.GET_SCAN_RESULTS,
            "extracted_fields": {},
            "tool_result": None,
            "next_node": None,
            "should_end": False
        }

    def test_provide_stl_links_success(self, nodes, base_state):
        """Test providing STL download links successfully."""
        # Execute node
        result = nodes.provide_stl_links_node(base_state)
        
        # Verify results
        assert "STL Download Links for Patient ID 5" in result["agent_response"]
        assert "Scan scan_001" in result["agent_response"]
        assert "https://example.com/scan1.stl" in result["agent_response"]
        assert "Scan scan_002" in result["agent_response"]
        assert "https://example.com/scan2.stl" in result["agent_response"]
        assert "Scan scan_003" in result["agent_response"]
        assert "No STL file available" in result["agent_response"]
        assert "2 STL file(s) ready for download" in result["agent_response"]
        
        # Verify state updates
        assert result["conversation_state"].download_stage == DownloadStage.STL_LINKS_SENT
        assert result["conversation_state"].confirmation_required is False
        assert result["conversation_state"].awaiting_confirmation_type == ConfirmationType.NONE
        assert result["should_end"] is True

    def test_provide_stl_links_no_buffer(self, nodes, base_state):
        """Test providing STL links with empty scan results buffer."""
        # Clear scan results buffer
        base_state["conversation_state"].scan_results_buffer = []
        
        # Execute node
        result = nodes.provide_stl_links_node(base_state)
        
        # Verify results
        assert "No scan results available for download" in result["agent_response"]
        assert result["conversation_state"].pending_action == PendingAction.NONE
        assert result["conversation_state"].download_stage == DownloadStage.NONE
        assert result["should_end"] is False

    def test_provide_stl_links_no_stl_files(self, nodes, base_state):
        """Test providing STL links when no STL files are available."""
        # Set scan results with no STL files
        base_state["conversation_state"].scan_results_buffer = [
            {
                "scan_id": "scan_001",
                "scan_date": "2024-01-15",
                "stl_file": None
            },
            {
                "scan_id": "scan_002", 
                "scan_date": "2024-01-20",
                "stl_file": ""  # Empty string
            }
        ]
        
        # Execute node
        result = nodes.provide_stl_links_node(base_state)
        
        # Verify results
        assert "STL Download Links for Patient ID 5" in result["agent_response"]
        assert "No STL file available" in result["agent_response"]
        assert "No STL files are available for download" in result["agent_response"]
        assert result["should_end"] is True


class TestHandleConfirmationNode:
    """Test handle_confirmation_node functionality."""
    
    @pytest.fixture
    def mock_tool_manager(self):
        return MagicMock()
    
    @pytest.fixture
    def mock_name_cache(self):
        return MagicMock()
    
    @pytest.fixture
    def nodes(self, mock_tool_manager, mock_name_cache):
        return ConversationGraphNodes(mock_tool_manager, mock_name_cache)

    def test_handle_delete_confirmation_yes(self):
        """Test handling delete confirmation with yes response."""
        conv_state = ConversationState()
        conv_state.confirmation_required = True
        conv_state.awaiting_confirmation_type = ConfirmationType.DELETE
        conv_state.validated_fields = {"patient_id": 5}
        
        state = {
            "user_message": "yes",
            "agent_response": "",
            "conversation_state": conv_state,
            "classified_intent": None,
            "extracted_fields": {},
            "tool_result": None,
            "next_node": None,
            "should_end": False
        }
        
        nodes = ConversationGraphNodes(MagicMock(), MagicMock())
        
        # Execute node
        result = nodes.handle_confirmation_node(state)
        
        # Verify results
        assert result["next_node"] == "execute_delete_patient"

    def test_handle_delete_confirmation_no(self):
        """Test handling delete confirmation with no response."""
        conv_state = ConversationState()
        conv_state.confirmation_required = True
        conv_state.awaiting_confirmation_type = ConfirmationType.DELETE
        conv_state.validated_fields = {"patient_id": 5}
        
        state = {
            "user_message": "no",
            "agent_response": "",
            "conversation_state": conv_state,
            "classified_intent": None,
            "extracted_fields": {},
            "tool_result": None,
            "next_node": None,
            "should_end": False
        }
        
        nodes = ConversationGraphNodes(MagicMock(), MagicMock())
        
        # Execute node
        result = nodes.handle_confirmation_node(state)
        
        # Verify results
        assert "Patient deletion cancelled" in result["agent_response"]
        assert result["conversation_state"].pending_action == PendingAction.NONE
        assert result["conversation_state"].confirmation_required is False
        assert result["should_end"] is True

    def test_handle_stl_confirmation_yes(self):
        """Test handling STL download confirmation with yes response."""
        conv_state = ConversationState()
        conv_state.confirmation_required = True
        conv_state.awaiting_confirmation_type = ConfirmationType.DOWNLOAD_STL
        
        state = {
            "user_message": "yes please",
            "agent_response": "",
            "conversation_state": conv_state,
            "classified_intent": None,
            "extracted_fields": {},
            "tool_result": None,
            "next_node": None,
            "should_end": False
        }
        
        nodes = ConversationGraphNodes(MagicMock(), MagicMock())
        
        # Execute node
        result = nodes.handle_confirmation_node(state)
        
        # Verify results
        assert result["next_node"] == "provide_stl_links"

    def test_handle_stl_confirmation_no(self):
        """Test handling STL download confirmation with no response."""
        conv_state = ConversationState()
        conv_state.confirmation_required = True
        conv_state.awaiting_confirmation_type = ConfirmationType.DOWNLOAD_STL
        conv_state.scan_results_buffer = [{"scan_id": "test"}]
        
        state = {
            "user_message": "no thanks",
            "agent_response": "",
            "conversation_state": conv_state,
            "classified_intent": None,
            "extracted_fields": {},
            "tool_result": None,
            "next_node": None,
            "should_end": False
        }
        
        nodes = ConversationGraphNodes(MagicMock(), MagicMock())
        
        # Execute node
        result = nodes.handle_confirmation_node(state)
        
        # Verify results
        assert "Scan results displayed without download links" in result["agent_response"]
        assert result["conversation_state"].pending_action == PendingAction.NONE
        assert result["conversation_state"].download_stage == DownloadStage.NONE
        assert len(result["conversation_state"].scan_results_buffer) == 0
        assert result["should_end"] is True

    def test_handle_ambiguous_confirmation(self):
        """Test handling ambiguous confirmation response."""
        conv_state = ConversationState()
        conv_state.confirmation_required = True
        conv_state.awaiting_confirmation_type = ConfirmationType.DELETE
        conv_state.validated_fields = {"patient_id": 5}
        
        state = {
            "user_message": "maybe later",
            "agent_response": "",
            "conversation_state": conv_state,
            "classified_intent": None,
            "extracted_fields": {},
            "tool_result": None,
            "next_node": None,
            "should_end": False
        }
        
        nodes = ConversationGraphNodes(MagicMock(), MagicMock())
        
        # Execute node
        result = nodes.handle_confirmation_node(state)
        
        # Verify results
        assert "Please respond clearly" in result["agent_response"]
        assert "Delete patient ID 5" in result["agent_response"]
        assert "yes" in result["agent_response"].lower()
        assert "no" in result["agent_response"].lower()
        assert result["should_end"] is False

    def test_handle_no_confirmation_required(self):
        """Test handling confirmation when none is required."""
        conv_state = ConversationState()
        conv_state.confirmation_required = False
        
        state = {
            "user_message": "yes",
            "agent_response": "",
            "conversation_state": conv_state,
            "classified_intent": None,
            "extracted_fields": {},
            "tool_result": None,
            "next_node": None,
            "should_end": False
        }
        
        nodes = ConversationGraphNodes(MagicMock(), MagicMock())
        
        # Mock unknown_intent_node method
        with patch.object(nodes, 'unknown_intent_node') as mock_unknown:
            mock_unknown.return_value = {
                **state,
                "agent_response": "I'm not sure what you'd like me to do"
            }
            
            # Execute node
            result = nodes.handle_confirmation_node(state)
            
            # Verify it delegates to unknown_intent_node
            mock_unknown.assert_called_once_with(state)


class TestPhase7IntegrationFlows:
    """Integration tests for Phase 7 conversation flows."""
    
    def test_complete_update_flow(self):
        """Test complete patient update flow from intent to execution."""
        # This would test the full flow through multiple nodes
        # Implementation would require more complex setup
        pass
    
    def test_complete_delete_flow_with_confirmation(self):
        """Test complete patient deletion flow with user confirmation."""
        # This would test delete -> confirmation -> execution
        pass
    
    def test_complete_scan_results_flow_with_stl_download(self):
        """Test complete scan results flow with STL download confirmation."""
        # This would test scan results -> preview -> STL confirmation -> links
        pass
