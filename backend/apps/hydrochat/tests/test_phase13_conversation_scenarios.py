# Phase 13 Tests: Full Conversation Scenario Tests (All Intents)
# Comprehensive end-to-end conversation flows testing all agent intents

import pytest
from unittest.mock import MagicMock

from apps.hydrochat.conversation_graph import create_conversation_graph, process_conversation_turn
from apps.hydrochat.state import ConversationState  
from apps.hydrochat.enums import Intent, PendingAction, ConfirmationType, DownloadStage
from apps.hydrochat.http_client import HttpClient
from apps.hydrochat.tools import ToolResponse


class TestFullConversationScenarios:
    """Test complete conversation flows for all intents"""

    def test_create_patient_flow_integration(self):
        """Test: CREATE_PATIENT intent integration with field extraction"""
        
        mock_http_client = MagicMock(spec=HttpClient)
        # Mock the raw HTTP response, not ToolResponse
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            'id': 123,
            'first_name': 'John',
            'last_name': 'Doe', 
            'nric': 'S1234567A'
        }
        mock_http_client.request.return_value = mock_response
        
        graph = create_conversation_graph(mock_http_client)
        state = ConversationState()
        
        # Process message through full conversation pipeline
        response, updated_state = process_conversation_turn(
            graph=graph,
            user_message="Create new patient John",
            conversation_state=state
        )
        
        # Should identify intent as CREATE_PATIENT
        assert updated_state.intent == Intent.CREATE_PATIENT
        # Response should prompt for missing fields
        assert any(field in response.lower() for field in ["last name", "nric"])

    def test_list_patients_flow_integration(self):
        """Test: LIST_PATIENTS intent integration"""
        
        mock_http_client = MagicMock(spec=HttpClient)
        # Mock the raw HTTP response, not ToolResponse
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {'id': 1, 'first_name': 'John', 'last_name': 'Doe', 'nric': 'S1234567A'},
            {'id': 2, 'first_name': 'Jane', 'last_name': 'Smith', 'nric': 'T9876543B'}
        ]
        mock_http_client.request.return_value = mock_response
        
        graph = create_conversation_graph(mock_http_client)
        state = ConversationState()
        
        response, updated_state = process_conversation_turn(
            graph=graph,
            user_message="List all patients", 
            conversation_state=state
        )
        
        # Should identify intent and call list endpoint
        assert updated_state.intent == Intent.LIST_PATIENTS
        # Response should contain patient information
        assert "john" in response.lower() and "jane" in response.lower()


class TestPerformanceBenchmarks:
    """Test performance requirements and timing constraints"""
    
    def test_response_time_under_threshold(self):
        """Test: Response time stays under reasonable threshold"""
        import time
        
        mock_http_client = MagicMock(spec=HttpClient)
        # Mock the raw HTTP response, not ToolResponse
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'id': 123, 'first_name': 'John', 'last_name': 'Doe', 'nric': 'S1234567A'}
        mock_http_client.request.return_value = mock_response
        
        graph = create_conversation_graph(mock_http_client)
        state = ConversationState()
        
        start_time = time.time()
        
        response, updated_state = process_conversation_turn(
            graph=graph,
            user_message="List all patients",
            conversation_state=state
        )
        
        elapsed_time = time.time() - start_time
        
        # Should complete within reasonable time (excluding network)
        # 2 seconds is generous for local processing
        assert elapsed_time < 2.0, f"Response took {elapsed_time:.2f}s, expected < 2.0s"
        assert len(response) > 0  # Sanity check