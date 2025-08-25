# Test suite for HydroChat conversation graph
# Tests LangGraph-based conversation orchestrator with patient workflows

import pytest
from unittest.mock import MagicMock, patch
import asyncio
from datetime import datetime

from apps.hydrochat.conversation_graph import (
    ConversationGraph, ConversationGraphNodes, GraphState, LogCategory,
    create_conversation_graph, process_conversation_turn
)
from apps.hydrochat.enums import Intent, PendingAction, ConfirmationType
from apps.hydrochat.state import ConversationState
from apps.hydrochat.tools import ToolResponse
from apps.hydrochat.http_client import HttpClient


class TestGraphState:
    """Test GraphState type definition."""
    
    def test_graph_state_structure(self):
        """Test GraphState has all required fields."""
        state: GraphState = {
            "user_message": "test message",
            "agent_response": "test response",
            "conversation_state": ConversationState(),
            "classified_intent": Intent.CREATE_PATIENT,
            "extracted_fields": {"first_name": "John"},
            "tool_result": None,
            "next_node": "create_patient",
            "should_end": False
        }
        
        # Verify all fields are accessible
        assert state["user_message"] == "test message"
        assert state["agent_response"] == "test response"
        assert isinstance(state["conversation_state"], ConversationState)
        assert state["classified_intent"] == Intent.CREATE_PATIENT
        assert state["extracted_fields"]["first_name"] == "John"
        assert state["tool_result"] is None
        assert state["next_node"] == "create_patient"
        assert state["should_end"] is False


class TestLogCategory:
    """Test logging taxonomy categories."""
    
    def test_log_categories(self):
        """Test all log categories are defined."""
        assert LogCategory.INTENT == "INTENT"
        assert LogCategory.MISSING == "MISSING"
        assert LogCategory.TOOL == "TOOL"
        assert LogCategory.SUCCESS == "SUCCESS"
        assert LogCategory.ERROR == "ERROR"
        assert LogCategory.FLOW == "FLOW"


class TestConversationGraphNodes:
    """Test individual conversation graph nodes."""
    
    @pytest.fixture
    def mock_http_client(self):
        """Mock HTTP client for testing."""
        return MagicMock(spec=HttpClient)
    
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

    def test_classify_intent_node_create_patient(self, nodes, base_state):
        """Test intent classification for create patient."""
        # Setup
        state = {**base_state}
        state["user_message"] = "create patient John Doe"
        
        # Mock intent classification
        with patch('apps.hydrochat.conversation_graph.classify_intent') as mock_classify, \
             patch('apps.hydrochat.conversation_graph.extract_fields') as mock_extract:
            
            mock_classify.return_value = Intent.CREATE_PATIENT
            mock_extract.return_value = {"first_name": "John", "last_name": "Doe"}
            
            # Execute node
            result = nodes.classify_intent_node(state)
            
            # Verify results
            assert result["classified_intent"] == Intent.CREATE_PATIENT
            assert result["extracted_fields"]["first_name"] == "John"
            assert result["next_node"] == "create_patient"
            assert result["conversation_state"].intent == Intent.CREATE_PATIENT

    def test_classify_intent_node_list_patients(self, nodes, base_state):
        """Test intent classification for list patients."""
        # Setup
        state = {**base_state}
        state["user_message"] = "list all patients"
        
        # Mock intent classification
        with patch('apps.hydrochat.conversation_graph.classify_intent') as mock_classify, \
             patch('apps.hydrochat.conversation_graph.extract_fields') as mock_extract:
            
            mock_classify.return_value = Intent.LIST_PATIENTS
            mock_extract.return_value = {}
            
            # Execute node
            result = nodes.classify_intent_node(state)
            
            # Verify results
            assert result["classified_intent"] == Intent.LIST_PATIENTS
            assert result["next_node"] == "list_patients"
            assert result["conversation_state"].intent == Intent.LIST_PATIENTS

    def test_classify_intent_node_unknown(self, nodes, base_state):
        """Test intent classification for unknown intent."""
        # Setup
        state = {**base_state}
        state["user_message"] = "random gibberish"
        
        # Mock intent classification
        with patch('apps.hydrochat.conversation_graph.classify_intent') as mock_classify, \
             patch('apps.hydrochat.conversation_graph.extract_fields') as mock_extract:
            
            mock_classify.return_value = Intent.UNKNOWN
            mock_extract.return_value = {}
            
            # Execute node
            result = nodes.classify_intent_node(state)
            
            # Verify results
            assert result["classified_intent"] == Intent.UNKNOWN
            assert result["next_node"] == "unknown_intent"
            assert result["conversation_state"].intent == Intent.UNKNOWN

    def test_create_patient_node_missing_fields(self, nodes, base_state):
        """Test create patient node with missing required fields."""
        # Setup
        state = {**base_state}
        state["extracted_fields"] = {"first_name": "John"}  # Missing last_name and nric
        
        # Mock field validation
        with patch('apps.hydrochat.conversation_graph.validate_required_patient_fields') as mock_validate:
            mock_validate.return_value = (False, {"last_name", "nric"})  # Tuple format
            
            # Execute node
            result = nodes.create_patient_node(state)
            
            # Verify results
            assert result["conversation_state"].pending_action == PendingAction.CREATE_PATIENT
            assert "nric" in result["agent_response"].lower()
            assert "last name" in result["agent_response"].lower()
            assert result["next_node"] == "end"
            assert result["should_end"] is False

    def test_create_patient_node_all_fields_present(self, nodes, base_state):
        """Test create patient node with all required fields present."""
        # Setup
        state = {**base_state}
        state["extracted_fields"] = {
            "first_name": "John",
            "last_name": "Doe", 
            "nric": "S1234567A"
        }
        
        # Mock field validation
        with patch('apps.hydrochat.conversation_graph.validate_required_patient_fields') as mock_validate:
            mock_validate.return_value = (True, set())  # No missing fields
            
            # Execute node
            result = nodes.create_patient_node(state)
            
            # Verify results
            assert result["conversation_state"].pending_action == PendingAction.CREATE_PATIENT
            assert result["next_node"] == "execute_create_patient"

    def test_execute_create_patient_node_success(self, nodes, base_state):
        """Test successful patient creation execution."""
        # Setup
        state = {**base_state}
        state["conversation_state"].validated_fields = {
            "first_name": "John",
            "last_name": "Doe",
            "nric": "S1234567A"
        }
        
        # Mock successful tool execution
        success_result = ToolResponse(
            success=True,
            data={"id": 1, "first_name": "John", "last_name": "Doe", "nric": "S1234567A"}
        )
        nodes.tool_manager.execute_tool.return_value = success_result
        
        # Execute node
        result = nodes.execute_create_patient_node(state)
        
        # Verify results
        assert result["tool_result"].success is True
        assert "Successfully created patient" in result["agent_response"]
        assert result["conversation_state"].pending_action == PendingAction.NONE
        assert len(result["conversation_state"].validated_fields) == 0
        assert result["should_end"] is True

    def test_execute_create_patient_node_failure(self, nodes, base_state):
        """Test failed patient creation execution."""
        # Setup
        state = {**base_state}
        state["conversation_state"].validated_fields = {
            "first_name": "John",
            "last_name": "Doe",
            "nric": "S1234567A"
        }
        
        # Mock failed tool execution
        failure_result = ToolResponse(
            success=False,
            error="NRIC already exists"
        )
        nodes.tool_manager.execute_tool.return_value = failure_result
        
        # Execute node
        result = nodes.execute_create_patient_node(state)
        
        # Verify results
        assert result["tool_result"].success is False
        assert "Failed to create patient" in result["agent_response"]
        assert "NRIC already exists" in result["agent_response"]
        assert result["should_end"] is False

    def test_list_patients_node_success(self, nodes, base_state):
        """Test successful patient listing."""
        # Setup
        state = {**base_state}
        
        # Mock successful tool execution
        success_result = ToolResponse(
            success=True,
            data=[
                {"id": 1, "first_name": "John", "last_name": "Doe", "date_of_birth": "1990-01-01"},
                {"id": 2, "first_name": "Jane", "last_name": "Smith", "contact_no": "+6512345678"}
            ]
        )
        nodes.tool_manager.execute_tool.return_value = success_result
        
        # Execute node
        result = nodes.list_patients_node(state)
        
        # Verify results
        assert result["tool_result"].success is True
        assert "Found 2 patient(s)" in result["agent_response"]
        assert "John Doe" in result["agent_response"]
        assert "Jane Smith" in result["agent_response"]
        assert result["should_end"] is True

    def test_list_patients_node_empty(self, nodes, base_state):
        """Test patient listing with no patients."""
        # Setup
        state = {**base_state}
        
        # Mock successful tool execution with empty data
        success_result = ToolResponse(success=True, data=[])
        nodes.tool_manager.execute_tool.return_value = success_result
        
        # Execute node
        result = nodes.list_patients_node(state)
        
        # Verify results
        assert result["tool_result"].success is True
        assert "No patients found" in result["agent_response"]
        assert result["should_end"] is True

    def test_list_patients_node_failure(self, nodes, base_state):
        """Test failed patient listing."""
        # Setup
        state = {**base_state}
        
        # Mock failed tool execution
        failure_result = ToolResponse(
            success=False,
            error="Database connection failed"
        )
        nodes.tool_manager.execute_tool.return_value = failure_result
        
        # Execute node
        result = nodes.list_patients_node(state)
        
        # Verify results
        assert result["tool_result"].success is False
        assert "Failed to list patients" in result["agent_response"]
        assert "Database connection failed" in result["agent_response"]
        assert result["should_end"] is False

    def test_unknown_intent_node(self, nodes, base_state):
        """Test unknown intent handling."""
        # Setup
        state = {**base_state}
        state["user_message"] = "random gibberish"
        
        # Execute node
        result = nodes.unknown_intent_node(state)
        
        # Verify results
        assert "not sure what you'd like me to do" in result["agent_response"]
        assert "Create a patient" in result["agent_response"]
        assert "List patients" in result["agent_response"]
        assert result["should_end"] is False


class TestConversationGraph:
    """Test main conversation graph functionality."""
    
    @pytest.fixture
    def mock_http_client(self):
        """Mock HTTP client for testing."""
        return MagicMock(spec=HttpClient)
    
    @pytest.fixture
    def graph(self, mock_http_client):
        """Conversation graph instance with mocked dependencies."""
        with patch('apps.hydrochat.conversation_graph.ToolManager'), \
             patch('apps.hydrochat.conversation_graph.NameResolutionCache'):
            return ConversationGraph(mock_http_client)

    def test_graph_initialization(self, graph, mock_http_client):
        """Test conversation graph initialization."""
        assert graph.http_client == mock_http_client
        assert graph.tool_manager is not None
        assert graph.name_cache is not None
        assert graph.nodes is not None
        assert graph.graph is not None

    @pytest.mark.asyncio
    async def test_process_message_create_patient_success(self, graph):
        """Test processing create patient message successfully."""
        # Setup
        conv_state = ConversationState()
        user_message = "create patient John Doe with NRIC S1234567A"
        
        # Mock the graph execution
        mock_final_state = {
            "conversation_state": conv_state,
            "agent_response": "Successfully created patient: John Doe (ID: 1)",
            "tool_result": ToolResponse(success=True, data={"id": 1})
        }
        
        with patch.object(graph.graph, 'ainvoke') as mock_invoke:
            mock_invoke.return_value = mock_final_state
            
            # Execute
            response, updated_state = await graph.process_message(user_message, conv_state)
            
            # Verify
            assert "Successfully created patient" in response
            assert isinstance(updated_state, ConversationState)

    @pytest.mark.asyncio
    async def test_process_message_error_handling(self, graph):
        """Test error handling during message processing."""
        # Setup
        conv_state = ConversationState()
        user_message = "test message"
        
        # Mock graph execution to raise exception
        with patch.object(graph.graph, 'ainvoke') as mock_invoke:
            mock_invoke.side_effect = Exception("Graph execution failed")
            
            # Execute
            response, updated_state = await graph.process_message(user_message, conv_state)
            
            # Verify error handling
            assert "I encountered an error" in response
            assert "Graph execution failed" in response
            assert updated_state.last_tool_error["error"] == "Graph execution failed"

    def test_process_message_sync(self, graph):
        """Test synchronous wrapper for process_message."""
        # Setup
        conv_state = ConversationState()
        user_message = "list patients"
        
        # Mock the async method
        expected_response = "Found 0 patients"
        
        async def mock_process_message(msg, state):
            return expected_response, state
        
        with patch.object(graph, 'process_message', side_effect=mock_process_message):
            # Execute
            response, updated_state = graph.process_message_sync(user_message, conv_state)
            
            # Verify
            assert response == expected_response
            assert updated_state == conv_state


class TestConversationFlows:
    """Integration tests for complete conversation flows."""
    
    @pytest.fixture
    def mock_http_client(self):
        """Mock HTTP client for testing."""
        return MagicMock(spec=HttpClient)

    def test_create_patient_flow_missing_nric(self, mock_http_client):
        """Test create patient flow with missing NRIC prompting user."""
        # Create graph with mocked dependencies
        with patch('apps.hydrochat.conversation_graph.ToolManager') as mock_tool_mgr, \
             patch('apps.hydrochat.conversation_graph.NameResolutionCache') as mock_cache:
            
            graph = ConversationGraph(mock_http_client)
            conv_state = ConversationState()
            
            # Mock intent classification
            with patch('apps.hydrochat.conversation_graph.classify_intent') as mock_classify, \
                 patch('apps.hydrochat.conversation_graph.extract_fields') as mock_extract, \
                 patch('apps.hydrochat.conversation_graph.validate_required_patient_fields') as mock_validate:
                
                mock_classify.return_value = Intent.CREATE_PATIENT
                mock_extract.return_value = {"first_name": "John", "last_name": "Doe"}
                mock_validate.return_value = (False, {"nric"})  # Missing NRIC
                
                # Execute
                response, updated_state = graph.process_message_sync(
                    "create patient John Doe", conv_state
                )
                
                # Verify missing NRIC prompt
                assert "NRIC" in response
                assert "S1234567A" in response  # Example format
                assert updated_state.pending_action == PendingAction.CREATE_PATIENT
                assert "nric" in updated_state.pending_fields

    def test_create_patient_flow_complete_success(self, mock_http_client):
        """Test complete create patient flow with success."""
        # Create graph with mocked dependencies
        with patch('apps.hydrochat.conversation_graph.ToolManager') as mock_tool_mgr_class, \
             patch('apps.hydrochat.conversation_graph.NameResolutionCache') as mock_cache_class:
            
            # Setup mock tool manager instance
            mock_tool_mgr = MagicMock()
            mock_tool_mgr_class.return_value = mock_tool_mgr
            mock_tool_mgr.execute_tool.return_value = ToolResponse(
                success=True,
                data={"id": 1, "first_name": "John", "last_name": "Doe", "nric": "S1234567A"}
            )
            
            # Setup mock name cache instance
            mock_cache = MagicMock()
            mock_cache_class.return_value = mock_cache
            
            graph = ConversationGraph(mock_http_client)
            conv_state = ConversationState()
            
            # Mock intent classification and validation
            with patch('apps.hydrochat.conversation_graph.classify_intent') as mock_classify, \
                 patch('apps.hydrochat.conversation_graph.extract_fields') as mock_extract, \
                 patch('apps.hydrochat.conversation_graph.validate_required_patient_fields') as mock_validate:
                
                mock_classify.return_value = Intent.CREATE_PATIENT
                mock_extract.return_value = {
                    "first_name": "John", 
                    "last_name": "Doe", 
                    "nric": "S1234567A"
                }
                mock_validate.return_value = (True, set())  # No missing fields
                
                # Execute
                response, updated_state = graph.process_message_sync(
                    "create patient John Doe with NRIC S1234567A", conv_state
                )
                
                # Verify successful creation
                assert "Successfully created patient" in response
                assert "John Doe" in response
                assert "ID: 1" in response
                assert updated_state.pending_action == PendingAction.NONE

    def test_list_patients_flow(self, mock_http_client):
        """Test list patients flow."""
        # Create graph with mocked dependencies
        with patch('apps.hydrochat.conversation_graph.ToolManager') as mock_tool_mgr_class, \
             patch('apps.hydrochat.conversation_graph.NameResolutionCache') as mock_cache_class:
            
            # Setup mock tool manager instance
            mock_tool_mgr = MagicMock()
            mock_tool_mgr_class.return_value = mock_tool_mgr
            mock_tool_mgr.execute_tool.return_value = ToolResponse(
                success=True,
                data=[
                    {"id": 1, "first_name": "John", "last_name": "Doe"},
                    {"id": 2, "first_name": "Jane", "last_name": "Smith"}
                ]
            )
            
            # Setup mock name cache instance
            mock_cache = MagicMock()
            mock_cache_class.return_value = mock_cache
            
            graph = ConversationGraph(mock_http_client)
            conv_state = ConversationState()
            
            # Mock intent classification
            with patch('apps.hydrochat.conversation_graph.classify_intent') as mock_classify, \
                 patch('apps.hydrochat.conversation_graph.extract_fields') as mock_extract:
                
                mock_classify.return_value = Intent.LIST_PATIENTS
                mock_extract.return_value = {}
                
                # Execute
                response, updated_state = graph.process_message_sync(
                    "list all patients", conv_state
                )
                
                # Verify patient listing
                assert "Found 2 patient(s)" in response
                assert "John Doe" in response
                assert "Jane Smith" in response


class TestConvenienceFunctions:
    """Test convenience functions."""
    
    @pytest.fixture
    def mock_http_client(self):
        """Mock HTTP client for testing."""
        return MagicMock(spec=HttpClient)

    def test_create_conversation_graph(self, mock_http_client):
        """Test creating conversation graph via convenience function."""
        with patch('apps.hydrochat.conversation_graph.ToolManager'), \
             patch('apps.hydrochat.conversation_graph.NameResolutionCache'):
            
            graph = create_conversation_graph(mock_http_client)
            
            assert isinstance(graph, ConversationGraph)
            assert graph.http_client == mock_http_client

    def test_process_conversation_turn(self, mock_http_client):
        """Test processing conversation turn via convenience function."""
        with patch('apps.hydrochat.conversation_graph.ToolManager'), \
             patch('apps.hydrochat.conversation_graph.NameResolutionCache'):
            
            graph = create_conversation_graph(mock_http_client)
            conv_state = ConversationState()
            
            # Mock the graph's sync method
            expected_response = "Test response"
            with patch.object(graph, 'process_message_sync') as mock_process:
                mock_process.return_value = (expected_response, conv_state)
                
                # Execute
                response, updated_state = process_conversation_turn(
                    graph, "test message", conv_state
                )
                
                # Verify
                assert response == expected_response
                assert updated_state == conv_state
                mock_process.assert_called_once_with("test message", conv_state)
