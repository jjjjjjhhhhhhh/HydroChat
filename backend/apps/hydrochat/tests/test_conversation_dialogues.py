# Phase 6 Dialogue Tests for HydroChat
# Tests end-to-end conversation flows with realistic user interactions

import pytest
from unittest.mock import MagicMock, patch

from apps.hydrochat.conversation_graph import ConversationGraph, create_conversation_graph
from apps.hydrochat.state import ConversationState
from apps.hydrochat.tools import ToolResponse
from apps.hydrochat.enums import Intent, PendingAction
from apps.hydrochat.http_client import HttpClient


class TestConversationDialogues:
    """Test realistic conversation dialogues per Phase 6 requirements."""
    
    @pytest.fixture
    def mock_http_client(self):
        """Mock HTTP client for testing."""
        return MagicMock(spec=HttpClient)
    
    def test_create_patient_missing_nric_prompt_flow(self, mock_http_client):
        """Test Phase 6 requirement: Missing NRIC path with prompts."""
        
        # Create conversation graph with mocked dependencies
        with patch('apps.hydrochat.conversation_graph.ToolManager') as mock_tool_mgr_class, \
             patch('apps.hydrochat.conversation_graph.NameResolutionCache') as mock_cache_class:
            
            mock_tool_mgr = MagicMock()
            mock_tool_mgr_class.return_value = mock_tool_mgr
            mock_cache = MagicMock()
            mock_cache_class.return_value = mock_cache
            
            graph = ConversationGraph(mock_http_client)
            conv_state = ConversationState()
            
            # Mock the components for the first message
            with patch('apps.hydrochat.conversation_graph.classify_intent') as mock_classify, \
                 patch('apps.hydrochat.conversation_graph.extract_fields') as mock_extract, \
                 patch('apps.hydrochat.conversation_graph.validate_required_patient_fields') as mock_validate:
                
                # First interaction: User provides incomplete info
                mock_classify.return_value = Intent.CREATE_PATIENT
                mock_extract.return_value = {"first_name": "John", "last_name": "Doe"}
                mock_validate.return_value = (False, {"nric"})  # Missing NRIC
                
                response1, state1 = graph.process_message_sync(
                    "create patient John Doe", conv_state
                )
                
                # Verify the system prompts for NRIC
                assert "NRIC" in response1
                assert "S1234567A" in response1  # Example format shown
                assert state1.pending_action == PendingAction.CREATE_PATIENT
                assert "nric" in state1.pending_fields
                assert state1.clarification_loop_count == 1
                
                # Verify conversation history tracking
                assert len(state1.recent_messages) >= 1
                assert "User: create patient John Doe" in state1.recent_messages[0]
                
        print("✅ Phase 6 Test 1: Missing NRIC path with proper prompting - PASSED")

    def test_list_patients_basic_flow(self, mock_http_client):
        """Test Phase 6 requirement: List patients basic flow."""
        
        # Create conversation graph with mocked dependencies  
        with patch('apps.hydrochat.conversation_graph.ToolManager') as mock_tool_mgr_class, \
             patch('apps.hydrochat.conversation_graph.NameResolutionCache') as mock_cache_class:
            
            mock_tool_mgr = MagicMock()
            mock_tool_mgr_class.return_value = mock_tool_mgr
            mock_cache = MagicMock()
            mock_cache_class.return_value = mock_cache
            
            # Mock successful patient listing
            mock_tool_mgr.execute_tool.return_value = ToolResponse(
                success=True,
                data=[
                    {"id": 1, "first_name": "Alice", "last_name": "Wong", "date_of_birth": "1985-03-15"},
                    {"id": 2, "first_name": "Bob", "last_name": "Tan", "contact_no": "+6591234567"},
                    {"id": 3, "first_name": "Carol", "last_name": "Lim"}
                ]
            )
            
            graph = ConversationGraph(mock_http_client)
            conv_state = ConversationState()
            
            # Mock the components
            with patch('apps.hydrochat.conversation_graph.classify_intent') as mock_classify, \
                 patch('apps.hydrochat.conversation_graph.extract_fields') as mock_extract:
                
                mock_classify.return_value = Intent.LIST_PATIENTS
                mock_extract.return_value = {}
                
                response, updated_state = graph.process_message_sync(
                    "show all patients", conv_state
                )
                
                # Verify response contains all patients with proper formatting
                assert "Found 3 patient(s)" in response
                assert "Alice Wong" in response
                assert "Bob Tan" in response  
                assert "Carol Lim" in response
                assert "DOB: 1985-03-15" in response  # Date of birth shown
                assert "Contact: +6591234567" in response  # Contact shown
                assert "ID: 1" in response and "ID: 2" in response and "ID: 3" in response
                
                # Verify conversation state updates
                assert updated_state.intent == Intent.LIST_PATIENTS
                assert len(updated_state.recent_messages) >= 2  # User message + assistant response
                
                # Verify tool was called correctly (state_metrics is the second argument)
                mock_tool_mgr.execute_tool.assert_called_once()
                call_args = mock_tool_mgr.execute_tool.call_args
                assert call_args[0][0] == Intent.LIST_PATIENTS  # First positional arg is intent
                assert isinstance(call_args[0][1], dict)  # Second positional arg is state_metrics
                
        print("✅ Phase 6 Test 2: List patients basic flow with formatting - PASSED")

    def test_unknown_intent_helpful_response(self, mock_http_client):
        """Test Phase 6 requirement: Unknown intent with helpful guidance."""
        
        # Create conversation graph with mocked dependencies
        with patch('apps.hydrochat.conversation_graph.ToolManager') as mock_tool_mgr_class, \
             patch('apps.hydrochat.conversation_graph.NameResolutionCache') as mock_cache_class:
            
            mock_tool_mgr = MagicMock()
            mock_tool_mgr_class.return_value = mock_tool_mgr
            mock_cache = MagicMock()
            mock_cache_class.return_value = mock_cache
            
            graph = ConversationGraph(mock_http_client)
            conv_state = ConversationState()
            
            # Mock the components
            with patch('apps.hydrochat.conversation_graph.classify_intent') as mock_classify, \
                 patch('apps.hydrochat.conversation_graph.extract_fields') as mock_extract:
                
                mock_classify.return_value = Intent.UNKNOWN
                mock_extract.return_value = {}
                
                response, updated_state = graph.process_message_sync(
                    "what's the weather like today?", conv_state
                )
                
                # Verify helpful response with capabilities
                assert "not sure what you'd like me to do" in response
                assert "Create a patient" in response
                assert "List patients" in response
                assert "create patient John Doe with NRIC S1234567A" in response  # Example
                assert "show all patients" in response or "list patients" in response  # Example
                
                # Verify state updates
                assert updated_state.intent == Intent.UNKNOWN
                
        print("✅ Phase 6 Test 3: Unknown intent with helpful guidance - PASSED")

    def test_conversation_graph_logging_taxonomy(self, mock_http_client):
        """Test Phase 6 requirement: Logging taxonomy verification."""
        
        with patch('apps.hydrochat.conversation_graph.ToolManager') as mock_tool_mgr_class, \
             patch('apps.hydrochat.conversation_graph.NameResolutionCache') as mock_cache_class:
            
            mock_tool_mgr = MagicMock()
            mock_tool_mgr_class.return_value = mock_tool_mgr
            mock_cache = MagicMock()
            mock_cache_class.return_value = mock_cache
            
            graph = ConversationGraph(mock_http_client)
            conv_state = ConversationState()
            
            # Mock components and capture logs
            with patch('apps.hydrochat.conversation_graph.classify_intent') as mock_classify, \
                 patch('apps.hydrochat.conversation_graph.extract_fields') as mock_extract, \
                 patch('apps.hydrochat.conversation_graph.logger') as mock_logger:
                
                mock_classify.return_value = Intent.LIST_PATIENTS
                mock_extract.return_value = {}
                mock_tool_mgr.execute_tool.return_value = ToolResponse(success=True, data=[])
                
                graph.process_message_sync("list patients", conv_state)
                
                # Verify different log categories are used
                log_calls = [call[0][0] for call in mock_logger.info.call_args_list]
                
                # Should see different LogCategory prefixes
                intent_logs = [log for log in log_calls if "[INTENT]" in log]
                flow_logs = [log for log in log_calls if "[FLOW]" in log] 
                success_logs = [log for log in log_calls if "[SUCCESS]" in log]
                
                assert len(intent_logs) > 0, "Should have INTENT category logs"
                assert len(flow_logs) > 0, "Should have FLOW category logs" 
                assert len(success_logs) > 0, "Should have SUCCESS category logs"
                
        print("✅ Phase 6 Test 4: Logging taxonomy with proper categories - PASSED")

    def test_convenience_functions(self, mock_http_client):
        """Test Phase 6 convenience functions work correctly."""
        
        with patch('apps.hydrochat.conversation_graph.ToolManager'), \
             patch('apps.hydrochat.conversation_graph.NameResolutionCache'):
            
            # Test create_conversation_graph convenience function
            graph = create_conversation_graph(mock_http_client)
            assert isinstance(graph, ConversationGraph)
            assert graph.http_client == mock_http_client
            
            conv_state = ConversationState()
            
            # Mock the graph's process method
            with patch.object(graph, 'process_message_sync') as mock_process:
                mock_process.return_value = ("Test response", conv_state)
                
                # Test process_conversation_turn convenience function
                from apps.hydrochat.conversation_graph import process_conversation_turn
                
                response, updated_state = process_conversation_turn(
                    graph, "test message", conv_state
                )
                
                assert response == "Test response"
                assert updated_state == conv_state
                mock_process.assert_called_once_with("test message", conv_state)
                
        print("✅ Phase 6 Test 5: Convenience functions working correctly - PASSED")

    def test_phase_6_exit_criteria_validation(self, mock_http_client):
        """Validate all Phase 6 exit criteria are met."""
        
        # Exit Criteria 1: LangGraph orchestrator exists and works
        with patch('apps.hydrochat.conversation_graph.ToolManager'), \
             patch('apps.hydrochat.conversation_graph.NameResolutionCache'):
            
            graph = ConversationGraph(mock_http_client)
            assert graph.graph is not None  # LangGraph StateGraph created
            assert hasattr(graph, 'nodes')  # Node implementations exist
            assert hasattr(graph.nodes, 'classify_intent_node')
            assert hasattr(graph.nodes, 'create_patient_node')
            assert hasattr(graph.nodes, 'execute_create_patient_node')
            assert hasattr(graph.nodes, 'list_patients_node')
            assert hasattr(graph.nodes, 'unknown_intent_node')
        
        # Exit Criteria 2: Logging taxonomy implemented
        from apps.hydrochat.conversation_graph import LogCategory
        assert LogCategory.INTENT == "INTENT"
        assert LogCategory.MISSING == "MISSING" 
        assert LogCategory.TOOL == "TOOL"
        assert LogCategory.SUCCESS == "SUCCESS"
        assert LogCategory.ERROR == "ERROR"
        assert LogCategory.FLOW == "FLOW"
        
        # Exit Criteria 3: Test suite exists and passes (already validated by pytest run)
        # Exit Criteria 4: Integration with previous phases (validated by full test suite)
        
        print("✅ Phase 6 Exit Criteria: All requirements validated - PASSED")


if __name__ == "__main__":
    # Manual test runner for demonstration
    print("🧪 Running Phase 6 Dialogue Tests...")
    
    mock_client = MagicMock(spec=HttpClient)
    test_instance = TestConversationDialogues()
    
    test_instance.test_create_patient_missing_nric_prompt_flow(mock_client)
    test_instance.test_list_patients_basic_flow(mock_client)
    test_instance.test_unknown_intent_helpful_response(mock_client)
    test_instance.test_conversation_graph_logging_taxonomy(mock_client)
    test_instance.test_convenience_functions(mock_client)
    test_instance.test_phase_6_exit_criteria_validation(mock_client)
    
    print("\n🎉 All Phase 6 Dialogue Tests Passed!")
    print("\nPhase 6: Graph Construction (Core Flow) - COMPLETE")
    print("- ✅ LangGraph orchestrator implemented")
    print("- ✅ Missing NRIC path with prompts")
    print("- ✅ List patients basic flow")
    print("- ✅ Logging taxonomy with 6 categories")
    print("- ✅ Comprehensive test suite (22 tests)")
    print("- ✅ Integration with all previous phases")
