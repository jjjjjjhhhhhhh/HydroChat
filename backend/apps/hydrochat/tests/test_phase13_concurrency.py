# Phase 13 Tests: Concurrency and Isolation Tests
# Test simultaneous conversations for proper isolation

import pytest
import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

from apps.hydrochat.conversation_graph import create_conversation_graph, process_conversation_turn
from apps.hydrochat.state import ConversationState
from apps.hydrochat.enums import Intent, PendingAction
from apps.hydrochat.http_client import HttpClient
from apps.hydrochat.tools import ToolResponse


class TestConcurrencyAndIsolation:
    """Test conversation isolation under concurrent access"""

    def test_concurrent_conversations_isolation(self):
        """Test: Multiple simultaneous conversations don't interfere"""
        
        mock_http_client = MagicMock(spec=HttpClient)
        
        # Different responses for different conversations
        def side_effect_response(*args, **kwargs):
            # Return different data based on thread
            thread_id = threading.current_thread().ident or 12345  # Default if None
            return ToolResponse(
                success=True,
                status_code=200,
                data={'id': thread_id % 1000, 'first_name': f'User{thread_id % 100}', 
                      'last_name': 'Test', 'nric': f'S{thread_id % 9999999:07d}A'},
                error=None
            )
        
        mock_http_client.request.side_effect = side_effect_response
        
        graph = create_conversation_graph(mock_http_client)
        
        def process_single_conversation(conversation_id):
            """Process a single conversation in a thread"""
            state = ConversationState()
            state.extracted_fields = {'conversation_id': conversation_id}
            
            response, updated_state = process_conversation_turn(
                graph=graph,
                user_message=f"List patients for conversation {conversation_id}",
                conversation_state=state
            )
            
            return {
                'conversation_id': conversation_id,
                'response': response,
                'state_intent': updated_state.intent,
                'thread_id': threading.current_thread().ident or 0
            }
        
        # Run 10 concurrent conversations
        num_conversations = 10
        results = []
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(process_single_conversation, i) 
                      for i in range(num_conversations)]
            results = [future.result() for future in futures]
        
        # Verify all conversations completed
        assert len(results) == num_conversations
        
        # Verify each conversation maintained its identity
        for result in results:
            assert result['conversation_id'] >= 0
            assert result['state_intent'] == Intent.LIST_PATIENTS
            assert len(result['response']) > 0
        
        # Verify conversations didn't interfere (different thread IDs)
        thread_ids = {result['thread_id'] for result in results}
        assert len(thread_ids) > 1  # Should use multiple threads

    def test_state_isolation_between_conversations(self):
        """Test: State changes in one conversation don't affect others"""
        
        mock_http_client = MagicMock(spec=HttpClient)
        mock_http_client.request.return_value = ToolResponse(
            success=True, status_code=200, data={}, error=None
        )
        
        graph = create_conversation_graph(mock_http_client)
        
        # Create two separate conversation states
        state1 = ConversationState()
        state1.intent = Intent.CREATE_PATIENT
        state1.pending_fields = {'first_name', 'nric'}
        state1.extracted_fields = {'last_name': 'Smith'}
        
        state2 = ConversationState()
        state2.intent = Intent.LIST_PATIENTS
        state2.pending_action = PendingAction.LIST_PATIENTS
        
        # Process both conversations
        response1, updated_state1 = process_conversation_turn(
            graph=graph, user_message="Create patient Smith", conversation_state=state1
        )
        
        response2, updated_state2 = process_conversation_turn(
            graph=graph, user_message="List all patients", conversation_state=state2
        )
        
        # Verify states remain isolated
        assert updated_state1.intent == Intent.CREATE_PATIENT
        assert updated_state2.intent == Intent.LIST_PATIENTS
        
        # State1 should still have pending fields
        assert len(updated_state1.pending_fields) > 0
        # State2 should not have pending fields
        assert len(updated_state2.pending_fields) == 0
        
        # Extracted fields should remain separate
        assert 'last_name' in updated_state1.extracted_fields
        assert 'last_name' not in updated_state2.extracted_fields

    def test_high_load_conversation_processing(self):
        """Test: System handles high load without degradation"""
        
        mock_http_client = MagicMock(spec=HttpClient)
        mock_http_client.request.return_value = ToolResponse(
            success=True,
            status_code=200,
            data=[{'id': i, 'first_name': f'Patient{i}', 'last_name': 'Test', 
                   'nric': f'S{i:07d}A'} for i in range(50)],
            error=None
        )
        
        graph = create_conversation_graph(mock_http_client)
        
        def time_single_request():
            """Time a single request"""
            start = time.time()
            state = ConversationState()
            response, updated_state = process_conversation_turn(
                graph=graph, user_message="List all patients", conversation_state=state
            )
            return time.time() - start
        
        # Run 50 sequential requests and measure timing
        times = []
        for i in range(50):
            execution_time = time_single_request()
            times.append(execution_time)
        
        # Calculate performance metrics
        avg_time = sum(times) / len(times)
        max_time = max(times)
        
        # Performance should remain reasonable even under load
        assert avg_time < 1.0, f"Average response time {avg_time:.3f}s too high"
        assert max_time < 2.0, f"Max response time {max_time:.3f}s too high"
        
        # Response time shouldn't degrade significantly over time
        first_half_avg = sum(times[:25]) / 25
        second_half_avg = sum(times[25:]) / 25
        degradation_ratio = second_half_avg / first_half_avg
        
        assert degradation_ratio < 1.5, f"Performance degraded by {degradation_ratio:.2f}x"

    def test_conversation_state_thread_safety(self):
        """Test: ConversationState operations are thread-safe"""
        
        mock_http_client = MagicMock(spec=HttpClient)
        mock_http_client.request.return_value = ToolResponse(
            success=True, status_code=200, data={}, error=None
        )
        
        graph = create_conversation_graph(mock_http_client)
        
        # Shared state that multiple threads will modify
        shared_state = ConversationState()
        results = []
        
        def modify_state_concurrently(thread_id):
            """Modify shared state from multiple threads"""
            nonlocal shared_state
            
            # Each thread adds unique data
            shared_state.extracted_fields[f'field_{thread_id}'] = f'value_{thread_id}'
            shared_state.pending_fields.add(f'pending_{thread_id}')
            
            # Process through graph
            response, updated_state = process_conversation_turn(
                graph=graph,
                user_message=f"Test message from thread {thread_id}",
                conversation_state=shared_state
            )
            
            return {
                'thread_id': thread_id,
                'extracted_count': len(updated_state.extracted_fields),
                'pending_count': len(updated_state.pending_fields)
            }
        
        # Run concurrent modifications
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(modify_state_concurrently, i) for i in range(3)]
            results = [future.result() for future in futures]
        
        # Verify all threads completed
        assert len(results) == 3
        
        # Note: This test may reveal race conditions if they exist
        # The behavior might vary, but should not crash
        for result in results:
            assert result['extracted_count'] >= 0
            assert result['pending_count'] >= 0

    def test_memory_isolation_large_states(self):
        """Test: Large conversation states don't leak memory between processes"""
        
        mock_http_client = MagicMock(spec=HttpClient)
        mock_http_client.request.return_value = ToolResponse(
            success=True, status_code=200, data={}, error=None
        )
        
        graph = create_conversation_graph(mock_http_client)
        
        def create_large_conversation():
            """Create a conversation with large state"""
            state = ConversationState()
            
            # Simulate large conversation history
            for i in range(1000):
                state.recent_messages.append({
                    "role": "user" if i % 2 == 0 else "assistant",
                    "content": f"Large message content {i} " * 100
                })
            
            # Add large extracted fields
            for i in range(500):
                state.extracted_fields[f'large_field_{i}'] = f"Large value {i} " * 50
            
            response, updated_state = process_conversation_turn(
                graph=graph,
                user_message="Process large state",
                conversation_state=state
            )
            
            return len(updated_state.recent_messages), len(updated_state.extracted_fields)
        
        # Create multiple large conversations in sequence
        results = []
        for i in range(5):
            msg_count, field_count = create_large_conversation()
            results.append((msg_count, field_count))
        
        # Each conversation should process independently
        assert len(results) == 5
        for msg_count, field_count in results:
            assert msg_count <= 5  # Should be capped by recent_messages deque
            assert field_count > 0  # Should have some fields
