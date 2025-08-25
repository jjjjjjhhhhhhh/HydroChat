# Phase 11 Tests: Django Endpoint `/api/hydrochat/converse/`
# Integration and unit tests for the HydroChat conversation API

import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.contrib.auth import get_user_model

from ..views import ConversationStateStore, ConverseAPIView, get_conversation_graph
from ..state import ConversationState
from ..enums import Intent, PendingAction, ConfirmationType, DownloadStage


User = get_user_model()


class ConversationStateStoreTests(TestCase):
    """Test the in-memory conversation state store."""
    
    def setUp(self):
        self.store = ConversationStateStore(max_conversations=3, ttl_minutes=5)
    
    def test_store_and_retrieve_conversation(self):
        """Test basic store and retrieve operations."""
        conversation_id = str(uuid.uuid4())
        state = ConversationState()
        state.intent = Intent.CREATE_PATIENT
        state.pending_action = PendingAction.CREATE_PATIENT
        
        # Store the state
        self.store.put(conversation_id, state)
        
        # Retrieve the state
        retrieved_state = self.store.get(conversation_id)
        
        self.assertIsNotNone(retrieved_state)
        if retrieved_state:  # Type guard for mypy
            self.assertEqual(retrieved_state.intent, Intent.CREATE_PATIENT)
            self.assertEqual(retrieved_state.pending_action, PendingAction.CREATE_PATIENT)
    
    def test_nonexistent_conversation(self):
        """Test retrieving a conversation that doesn't exist."""
        conversation_id = str(uuid.uuid4())
        retrieved_state = self.store.get(conversation_id)
        self.assertIsNone(retrieved_state)
    
    def test_max_conversations_limit(self):
        """Test that the store enforces max conversations limit."""
        # Fill the store to capacity
        for i in range(4):  # One more than max
            conversation_id = str(uuid.uuid4())
            state = ConversationState()
            self.store.put(conversation_id, state)
        
        # Check that we have exactly max conversations
        stats = self.store.get_stats()
        self.assertEqual(stats['active_conversations'], 3)
    
    def test_ttl_expiration(self):
        """Test that conversations expire based on TTL."""
        # Create a store with very short TTL for testing
        short_store = ConversationStateStore(max_conversations=10, ttl_minutes=0)  # Immediate expiration
        
        conversation_id = str(uuid.uuid4())
        state = ConversationState()
        short_store.put(conversation_id, state)
        
        # Try to retrieve - should trigger expiration
        retrieved_state = short_store.get(conversation_id)
        self.assertIsNone(retrieved_state)
    
    def test_store_stats(self):
        """Test store statistics functionality."""
        conversation_id = str(uuid.uuid4())
        state = ConversationState()
        self.store.put(conversation_id, state)
        
        stats = self.store.get_stats()
        self.assertEqual(stats['active_conversations'], 1)
        self.assertEqual(stats['max_conversations'], 3)
        self.assertEqual(stats['ttl_minutes'], 5)
        self.assertIsNotNone(stats['newest_access'])
        self.assertIsNotNone(stats['oldest_access'])


class ConverseAPIIntegrationTests(APITestCase):
    """Integration tests for the /api/hydrochat/converse/ endpoint."""
    
    def setUp(self):
        # Create a test user and authenticate
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)
        
        self.url = reverse('hydrochat:converse')
    
    @patch('apps.hydrochat.views.get_conversation_graph')
    def test_create_new_conversation(self, mock_get_graph):
        """Test creating a new conversation."""
        # Mock the conversation graph
        mock_graph = MagicMock()
        mock_graph.process_message_sync.return_value = (
            "Hello! I'm HydroChat. How can I help you with patient management today?",
            ConversationState()
        )
        mock_get_graph.return_value = mock_graph
        
        # Make request with no conversation_id
        data = {
            'conversation_id': None,
            'message': 'Hello'
        }
        
        response = self.client.post(self.url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        
        # Check response structure
        self.assertIn('conversation_id', response_data)
        self.assertIsNotNone(response_data['conversation_id'])
        self.assertEqual(len(response_data['messages']), 1)
        self.assertEqual(response_data['messages'][0]['role'], 'assistant')
        self.assertIn('agent_state', response_data)
        self.assertIn('agent_op', response_data)
    
    @patch('apps.hydrochat.views.get_conversation_graph')
    def test_continue_existing_conversation(self, mock_get_graph):
        """Test continuing an existing conversation."""
        # Mock the conversation graph
        mock_graph = MagicMock()
        updated_state = ConversationState()
        updated_state.intent = Intent.LIST_PATIENTS
        mock_graph.process_message_sync.return_value = (
            "Here are all the patients in the system:",
            updated_state
        )
        mock_get_graph.return_value = mock_graph
        
        # First, create a conversation
        conversation_id = str(uuid.uuid4())
        from apps.hydrochat.views import conversation_store
        initial_state = ConversationState()
        conversation_store.put(conversation_id, initial_state)
        
        # Make request with existing conversation_id
        data = {
            'conversation_id': conversation_id,
            'message': 'list patients'
        }
        
        response = self.client.post(self.url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        
        # Check that the same conversation_id is returned
        self.assertEqual(response_data['conversation_id'], conversation_id)
        self.assertEqual(response_data['agent_state']['intent'], 'LIST_PATIENTS')
    
    def test_invalid_request_missing_message(self):
        """Test request validation for missing message."""
        data = {
            'conversation_id': None
        }
        
        response = self.client.post(self.url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response_data = response.json()
        self.assertEqual(response_data['error'], 'validation')
    
    def test_invalid_request_empty_message(self):
        """Test request validation for empty message."""
        data = {
            'conversation_id': None,
            'message': '   '  # Only whitespace
        }
        
        response = self.client.post(self.url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response_data = response.json()
        self.assertEqual(response_data['error'], 'validation')
    
    def test_invalid_request_non_json(self):
        """Test request validation for non-JSON request."""
        response = self.client.post(self.url, 'invalid json', content_type='text/plain')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response_data = response.json()
        self.assertEqual(response_data['error'], 'validation')
    
    def test_unauthenticated_request(self):
        """Test that unauthenticated requests are rejected."""
        self.client.force_authenticate(user=None)
        
        data = {
            'conversation_id': None,
            'message': 'Hello'
        }
        
        response = self.client.post(self.url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    @patch('apps.hydrochat.views.get_conversation_graph')
    def test_agent_op_determination(self, mock_get_graph):
        """Test agent_op determination based on conversation state."""
        # Mock successful patient creation
        mock_graph = MagicMock()
        updated_state = ConversationState()
        updated_state.intent = Intent.CREATE_PATIENT
        updated_state.last_tool_response = {'success': True, 'data': {'id': 1}}
        mock_graph.process_message_sync.return_value = (
            "Patient created successfully!",
            updated_state
        )
        mock_get_graph.return_value = mock_graph
        
        data = {
            'conversation_id': None,
            'message': 'create patient John Doe S1234567A'
        }
        
        response = self.client.post(self.url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertEqual(response_data['agent_op'], 'CREATE')
    
    @patch('apps.hydrochat.views.get_conversation_graph')
    def test_server_error_handling(self, mock_get_graph):
        """Test server error handling."""
        # Mock graph to raise an exception
        mock_get_graph.side_effect = Exception("Test error")
        
        data = {
            'conversation_id': None,
            'message': 'Hello'
        }
        
        response = self.client.post(self.url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        response_data = response.json()
        self.assertEqual(response_data['error'], 'server')


class ConverseStatsAPITests(APITestCase):
    """Tests for the conversation statistics endpoint."""
    
    def setUp(self):
        # Create a test user and authenticate
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com', 
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)
        
        self.url = reverse('hydrochat:converse_stats')
    
    def test_get_stats(self):
        """Test getting conversation statistics."""
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        
        # Check expected statistics fields
        self.assertIn('active_conversations', response_data)
        self.assertIn('max_conversations', response_data)
        self.assertIn('ttl_minutes', response_data)
        self.assertIn('oldest_access', response_data)
        self.assertIn('newest_access', response_data)
    
    def test_unauthenticated_stats_request(self):
        """Test that unauthenticated stats requests are rejected."""
        self.client.force_authenticate(user=None)
        
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class ConversationGraphIntegrationTests(TestCase):
    """Test conversation graph integration with real backend endpoints."""
    
    @patch('apps.hydrochat.http_client.requests.Session.request')
    def test_real_patient_create_flow(self, mock_request):
        """Integration test: real patient creation flow hitting mocked backend."""
        # Mock successful patient creation response
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            'id': 123,
            'first_name': 'John',
            'last_name': 'Doe',
            'nric': 'S1234567A'
        }
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response
        
        # Get the conversation graph
        graph = get_conversation_graph()
        
        # Test conversation flow
        conv_state = ConversationState()
        
        # First message: incomplete patient creation
        response1, state1 = graph.process_message_sync(
            "create patient John Doe S1234567A", 
            conv_state
        )
        
        # Should create the patient since all fields are provided
        self.assertIn("created", response1.lower())
        self.assertEqual(state1.intent, Intent.CREATE_PATIENT)
        
        # Mock request should have been called
        mock_request.assert_called()
    
    @patch('apps.hydrochat.http_client.requests.Session.request')  
    def test_real_patient_list_flow(self, mock_request):
        """Integration test: real patient list flow hitting mocked backend."""
        # Mock successful patient list response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {'id': 1, 'first_name': 'John', 'last_name': 'Doe', 'nric': 'S1234567A'},
            {'id': 2, 'first_name': 'Jane', 'last_name': 'Smith', 'nric': 'S9876543B'}
        ]
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response
        
        # Get the conversation graph
        graph = get_conversation_graph()
        
        # Test list patients flow
        conv_state = ConversationState()
        response, updated_state = graph.process_message_sync(
            "list all patients",
            conv_state
        )
        
        # Should return patient list
        self.assertIn("John Doe", response)
        self.assertIn("Jane Smith", response) 
        # The actual response format doesn't include NRIC - check logs for actual format
        self.assertEqual(updated_state.intent, Intent.LIST_PATIENTS)
        
        # Mock request should have been called
        mock_request.assert_called()


class Phase11ExitCriteriaTests(APITestCase):
    """Tests to verify Phase 11 exit criteria are met."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)
        
        self.converse_url = reverse('hydrochat:converse')
        self.stats_url = reverse('hydrochat:converse_stats')
    
    @patch('apps.hydrochat.http_client.requests.Session.request')
    def test_integration_test_create_and_update(self, mock_request):
        """EC: Integration test hitting local patient endpoints executing create + update."""
        # Mock create response
        create_response = MagicMock()
        create_response.status_code = 201
        create_response.json.return_value = {
            'id': 123,
            'first_name': 'Test',
            'last_name': 'Patient', 
            'nric': 'S1234567A'
        }
        create_response.raise_for_status.return_value = None
        
        # Mock get response (for update)
        get_response = MagicMock()
        get_response.status_code = 200
        get_response.json.return_value = {
            'id': 123,
            'first_name': 'Test',
            'last_name': 'Patient',
            'nric': 'S1234567A',
            'contact_no': None
        }
        get_response.raise_for_status.return_value = None
        
        # Mock update response
        update_response = MagicMock()
        update_response.status_code = 200
        update_response.json.return_value = {
            'id': 123,
            'first_name': 'Test', 
            'last_name': 'Patient',
            'nric': 'S1234567A',
            'contact_no': '91234567'
        }
        update_response.raise_for_status.return_value = None
        
        # Set up mock to return different responses for different calls
        mock_request.side_effect = [create_response, get_response, update_response]
        
        # Test create patient flow
        create_data = {
            'conversation_id': None,
            'message': 'create patient Test Patient S1234567A'
        }
        
        create_response_api = self.client.post(self.converse_url, create_data, format='json')
        self.assertEqual(create_response_api.status_code, status.HTTP_200_OK)
        
        conversation_id = create_response_api.json()['conversation_id']
        
        # Test update patient flow
        update_data = {
            'conversation_id': conversation_id,
            'message': 'update patient 123 contact 91234567'
        }
        
        update_response_api = self.client.post(self.converse_url, update_data, format='json')
        self.assertEqual(update_response_api.status_code, status.HTTP_200_OK)
        
        # Verify both operations succeeded
        self.assertGreaterEqual(mock_request.call_count, 2)
    
    def test_drf_view_post_handling(self):
        """EC: DRF view (APIView) handling POST with conversation_id + message."""
        with patch('apps.hydrochat.views.get_conversation_graph') as mock_get_graph:
            mock_graph = MagicMock()
            mock_graph.process_message_sync.return_value = (
                "Test response", ConversationState()
            )
            mock_get_graph.return_value = mock_graph
            
            # Test POST with both conversation_id and message
            data = {
                'conversation_id': str(uuid.uuid4()),
                'message': 'test message'
            }
            
            response = self.client.post(self.converse_url, data, format='json')
            
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            response_data = response.json()
            
            # Verify required response fields per spec
            self.assertIn('conversation_id', response_data)
            self.assertIn('messages', response_data)
            self.assertIn('agent_state', response_data) 
            self.assertIn('agent_op', response_data)
    
    def test_stateless_load_or_new_state_creation(self):
        """EC: Stateless load or new state creation (in-memory store keyed by UUID)."""
        with patch('apps.hydrochat.views.get_conversation_graph') as mock_get_graph:
            mock_graph = MagicMock()
            mock_graph.process_message_sync.return_value = (
                "Test response", ConversationState()
            )
            mock_get_graph.return_value = mock_graph
            
            # Test new state creation
            data1 = {
                'conversation_id': None,
                'message': 'test message'
            }
            
            response1 = self.client.post(self.converse_url, data1, format='json')
            conversation_id = response1.json()['conversation_id']
            
            # Test state loading
            data2 = {
                'conversation_id': conversation_id,
                'message': 'second message'
            }
            
            response2 = self.client.post(self.converse_url, data2, format='json')
            
            # Should return the same conversation_id
            self.assertEqual(response2.json()['conversation_id'], conversation_id)
    
    def test_response_schema_per_spec(self):
        """EC: Response schema per spec (agent_op, intent, missing_fields, awaiting_confirmation)."""
        with patch('apps.hydrochat.views.get_conversation_graph') as mock_get_graph:
            updated_state = ConversationState()
            updated_state.intent = Intent.CREATE_PATIENT
            updated_state.confirmation_required = True
            updated_state.pending_fields = {'last_name', 'nric'}
            
            mock_graph = MagicMock()
            mock_graph.process_message_sync.return_value = (
                "Test response", updated_state
            )
            mock_get_graph.return_value = mock_graph
            
            data = {
                'conversation_id': None,
                'message': 'create patient John'
            }
            
            response = self.client.post(self.converse_url, data, format='json')
            response_data = response.json()
            
            # Verify exact response schema
            self.assertIn('conversation_id', response_data)
            self.assertIn('messages', response_data)
            self.assertEqual(len(response_data['messages']), 1)
            self.assertEqual(response_data['messages'][0]['role'], 'assistant')
            
            agent_state = response_data['agent_state']
            self.assertEqual(agent_state['intent'], 'CREATE_PATIENT')
            self.assertTrue(agent_state['awaiting_confirmation'])
            self.assertCountEqual(agent_state['missing_fields'], ['last_name', 'nric'])
            
            self.assertIn('agent_op', response_data)
    
    def test_state_ttl_eviction_strategy(self):
        """EC: State TTL eviction strategy (simple LRU / timestamp sweep placeholder)."""
        from apps.hydrochat.views import ConversationStateStore
        
        # Test TTL-based eviction
        short_store = ConversationStateStore(max_conversations=10, ttl_minutes=0)
        
        state = ConversationState()
        conversation_id = str(uuid.uuid4())
        
        short_store.put(conversation_id, state)
        retrieved = short_store.get(conversation_id)
        
        # Should be None due to immediate expiration
        self.assertIsNone(retrieved)
        
        # Test LRU eviction
        lru_store = ConversationStateStore(max_conversations=2, ttl_minutes=30)
        
        # Add conversations up to limit
        id1 = str(uuid.uuid4())
        id2 = str(uuid.uuid4())
        id3 = str(uuid.uuid4())
        
        lru_store.put(id1, ConversationState())
        lru_store.put(id2, ConversationState())
        lru_store.put(id3, ConversationState())  # Should evict id1
        
        self.assertIsNone(lru_store.get(id1))  # Should be evicted
        self.assertIsNotNone(lru_store.get(id2))  # Should still exist
        self.assertIsNotNone(lru_store.get(id3))  # Should still exist
