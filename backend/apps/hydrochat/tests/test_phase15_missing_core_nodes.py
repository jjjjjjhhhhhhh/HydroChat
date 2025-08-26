"""
Phase 15 Tests: Missing Core Nodes Implementation
Test the three missing core nodes: ingest_user_message, summarize_history, finalize_response

Exit Criteria Coverage:
1. Long conversation (>5 turns) maintains context through summary generation
2. All responses pass through finalize_response for consistent formatting and PII masking
3. ingest_user_message sanitizes malicious input and validates message length
4. Summarization uses Gemini API to create coherent conversation history
5. Integration test: Complete flow ingest -> classify -> execute -> finalize with all 16 nodes
6. Response templates match HydroChat.md §25 specifications exactly
"""

import unittest
from unittest.mock import patch, MagicMock, AsyncMock
import json
from datetime import datetime
from collections import deque
import re

import unittest
from unittest.mock import patch, MagicMock, AsyncMock
import json
from datetime import datetime
from collections import deque
import re

from apps.hydrochat.conversation_graph import ConversationGraph, ConversationGraphNodes, GraphState
from apps.hydrochat.state import ConversationState
from apps.hydrochat.enums import Intent, PendingAction, ConfirmationType, DownloadStage
from apps.hydrochat.http_client import HttpClient
from apps.hydrochat.tools import ToolResponse
from apps.hydrochat.utils import mask_nric


class TestPhase15MissingCoreNodes(unittest.TestCase):
    """Test Phase 15 missing core nodes implementation."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.http_client = MagicMock(spec=HttpClient)
        self.graph = ConversationGraph(self.http_client)
        self.nodes = self.graph.nodes
        
        # Create test conversation state
        self.conv_state = ConversationState()
        
        # Sample graph state
        self.graph_state = {
            "user_message": "test message",
            "agent_response": "",
            "conversation_state": self.conv_state,
            "classified_intent": None,
            "extracted_fields": {},
            "tool_result": None,
            "next_node": None,
            "should_end": False
        }

    # ===== INGEST USER MESSAGE TESTS =====
    
    def test_ingest_user_message_normal_input(self):
        """Test normal message ingestion and preprocessing."""
        test_message = "Create patient John Doe with NRIC S1234567A"
        
        state = {
            **self.graph_state,
            "user_message": test_message
        }
        
        result = self.nodes.ingest_user_message_node(state)
        
        # Should sanitize successfully and proceed to classification
        self.assertEqual(result["user_message"], test_message)
        self.assertEqual(result["next_node"], "classify_intent")
        self.assertEqual(result.get("agent_response", ""), "")  # Should be empty for normal flow

    def test_ingest_user_message_empty_input(self):
        """Test handling of empty or whitespace-only messages."""
        test_cases = ["", "   ", "\n\t  \n"]
        
        for empty_message in test_cases:
            with self.subTest(message=repr(empty_message)):
                state = {
                    **self.graph_state,
                    "user_message": empty_message
                }
                
                result = self.nodes.ingest_user_message_node(state)
                
                self.assertEqual(result["next_node"], "end")
                self.assertFalse(result["should_end"])
                self.assertIn("Please provide a message", result["agent_response"])

    def test_ingest_user_message_length_validation(self):
        """Test message length validation to prevent token abuse."""
        # Create message that exceeds MAX_MESSAGE_LENGTH (2000 chars)
        long_message = "A" * 2001
        
        state = {
            **self.graph_state,
            "user_message": long_message
        }
        
        result = self.nodes.ingest_user_message_node(state)
        
        self.assertEqual(result["next_node"], "end")
        self.assertFalse(result["should_end"])
        self.assertIn("Message too long", result["agent_response"])
        self.assertIn("2001 characters", result["agent_response"])

    def test_ingest_user_message_security_sanitization(self):
        """Test sanitization of potentially malicious input patterns."""
        malicious_patterns = [
            "Create patient <script>alert('xss')</script> John",
            "List patients javascript:void(0)",
            "Show patients data:text/html,<script>alert(1)</script>",
            "Update patient eval(malicious_code)",
            "Delete patient exec(dangerous_function)"
        ]
        
        for malicious_input in malicious_patterns:
            with self.subTest(message=malicious_input):
                state = {
                    **self.graph_state,
                    "user_message": malicious_input
                }
                
                result = self.nodes.ingest_user_message_node(state)
                
                # Should sanitize but not reject entirely
                sanitized_message = result["user_message"]
                self.assertIn("[sanitized]", sanitized_message)
                self.assertEqual(result["next_node"], "classify_intent")

    def test_ingest_user_message_cancellation_detection(self):
        """Test early cancellation detection during message ingestion."""
        cancellation_messages = [
            "cancel",
            "abort operation", 
            "stop this",
            "reset everything",
            "CANCEL current action"
        ]
        
        for cancel_msg in cancellation_messages:
            with self.subTest(message=cancel_msg):
                state = {
                    **self.graph_state,
                    "user_message": cancel_msg
                }
                
                result = self.nodes.ingest_user_message_node(state)
                self.assertEqual(result["next_node"], "handle_cancellation")
                self.assertEqual(result.get("agent_response", ""), "")  # Should be empty for cancellation    # ===== SUMMARIZE HISTORY TESTS =====
    
    def test_summarize_history_insufficient_messages(self):
        """Test that summarization is skipped when <5 messages."""
        # Add only 3 messages
        for i in range(3):
            self.conv_state.recent_messages.append(f"Message {i+1}")
        
        state = {
            **self.graph_state,
            "conversation_state": self.conv_state
        }
        
        result = self.nodes.summarize_history_node(state)
        
        self.assertEqual(result["next_node"], "finalize_response")
        self.assertEqual(len(self.conv_state.recent_messages), 3)  # Unchanged
        self.assertEqual(self.conv_state.history_summary, "")  # No summary created

    @patch('apps.hydrochat.gemini_client.GeminiClient')
    def test_summarize_history_with_gemini_success(self, mock_gemini_class):
        """Test successful history summarization using Gemini API."""
        # Set up 5 messages to trigger summarization
        for i in range(5):
            self.conv_state.recent_messages.append(f"Turn {i+1}: Patient management task")
        
        # Mock Gemini client response
        mock_client = MagicMock()
        mock_gemini_class.return_value = mock_client
        mock_client.api_key = "test_key"
        
        # Mock successful API response
        mock_api_response = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": json.dumps({
                            "salient_patients": [123],
                            "pending_action": "CREATE_PATIENT", 
                            "unresolved_fields": ["first_name"],
                            "last_result": "Patient creation in progress"
                        })
                    }]
                }
            }]
        }
        
        # Create async mock
        async def mock_call_gemini(prompt):
            return mock_api_response
        
        mock_client._call_gemini_api = AsyncMock(side_effect=mock_call_gemini)
        
        state = {
            **self.graph_state,
            "conversation_state": self.conv_state
        }
        
        result = self.nodes.summarize_history_node(state)
        
        # Should proceed to finalization
        self.assertEqual(result["next_node"], "finalize_response")
        
        # Should have created structured summary
        self.assertNotEqual(self.conv_state.history_summary, "")
        summary_data = json.loads(self.conv_state.history_summary)
        self.assertIn("salient_patients", summary_data)
        self.assertIn("pending_action", summary_data)
        
        # Should have reduced message count to make room
        self.assertEqual(len(self.conv_state.recent_messages), 1)  # Keep last message

    @patch('apps.hydrochat.gemini_client.GeminiClient')
    def test_summarize_history_gemini_unavailable(self, mock_gemini_class):
        """Test fallback summarization when Gemini API is unavailable."""
        # Set up 5 messages
        for i in range(5):
            self.conv_state.recent_messages.append(f"Turn {i+1}: Patient task")
        
        # Set some context in conversation state
        self.conv_state.selected_patient_id = 456
        self.conv_state.pending_action = PendingAction.UPDATE_PATIENT
        self.conv_state.pending_fields.add("contact_no")
        self.conv_state.intent = Intent.UPDATE_PATIENT
        
        # Mock client with no API key
        mock_client = MagicMock()
        mock_gemini_class.return_value = mock_client
        mock_client.api_key = None
        
        state = {
            **self.graph_state,
            "conversation_state": self.conv_state
        }
        
        result = self.nodes.summarize_history_node(state)
        
        # Should proceed to finalization
        self.assertEqual(result["next_node"], "finalize_response")
        
        # Should have created fallback summary
        self.assertNotEqual(self.conv_state.history_summary, "")
        summary_data = json.loads(self.conv_state.history_summary)
        
        # Verify fallback summary structure
        self.assertEqual(summary_data["salient_patients"], [456])
        self.assertEqual(summary_data["pending_action"], "UPDATE_PATIENT")
        self.assertEqual(summary_data["unresolved_fields"], ["contact_no"])
        self.assertIn("UPDATE_PATIENT", summary_data["last_result"])

    @patch('apps.hydrochat.gemini_client.GeminiClient')
    def test_summarize_history_gemini_api_error(self, mock_gemini_class):
        """Test fallback when Gemini API call fails."""
        # Set up 5 messages
        for i in range(5):
            self.conv_state.recent_messages.append(f"Turn {i+1}: Task")
        
        # Mock client that throws exception
        mock_client = MagicMock()
        mock_gemini_class.return_value = mock_client
        mock_client.api_key = "test_key"
        
        # Mock API call that raises exception
        async def mock_call_error(prompt):
            raise Exception("API error")
        
        mock_client._call_gemini_api = AsyncMock(side_effect=mock_call_error)
        
        state = {
            **self.graph_state,
            "conversation_state": self.conv_state
        }
        
        result = self.nodes.summarize_history_node(state)
        
        # Should still proceed to finalization 
        self.assertEqual(result["next_node"], "finalize_response")
        
        # Should have created fallback summary despite API error
        self.assertNotEqual(self.conv_state.history_summary, "")

    # ===== FINALIZE RESPONSE TESTS =====
    
    def test_finalize_response_basic_functionality(self):
        """Test basic response finalization without special formatting."""
        basic_response = "Here is your patient information."
        
        state = {
            **self.graph_state,
            "agent_response": basic_response
        }
        
        result = self.nodes.finalize_response_node(state)
        
        self.assertEqual(result["next_node"], "end")
        self.assertTrue(result["should_end"])
        self.assertEqual(result["agent_response"], basic_response)  # No changes needed

    def test_finalize_response_empty_response_handling(self):
        """Test handling of empty agent responses."""
        state = {
            **self.graph_state,
            "agent_response": ""
        }
        
        result = self.nodes.finalize_response_node(state)
        
        self.assertEqual(result["next_node"], "end")
        self.assertTrue(result["should_end"])
        self.assertIn("couldn't process your request", result["agent_response"])

    def test_finalize_response_pii_masking_enforcement(self):
        """Test that unmasked NRICs are caught and masked in final response."""
        # Response with unmasked NRIC that somehow got through
        response_with_nric = "Patient S1234567A has been updated successfully."
        
        state = {
            **self.graph_state,
            "agent_response": response_with_nric
        }
        
        result = self.nodes.finalize_response_node(state)
        
        final_response = result["agent_response"]
        
        # Should not contain unmasked NRIC
        self.assertNotIn("S1234567A", final_response)
        # Should contain masked version
        self.assertIn("S******7A", final_response)

    def test_finalize_response_template_application_create_patient(self):
        """Test response template application for successful patient creation."""
        # Mock successful creation tool result
        mock_tool_result = ToolResponse(
            success=True,
            data={
                "id": 123,
                "first_name": "John",
                "last_name": "Doe",
                "nric": "S1234567A",
                "date_of_birth": "1990-01-01",
                "contact_no": "91234567"
            },
            error=None
        )
        
        self.conv_state.intent = Intent.CREATE_PATIENT
        
        state = {
            **self.graph_state,
            "agent_response": "Patient created",
            "tool_result": mock_tool_result,
            "conversation_state": self.conv_state
        }
        
        result = self.nodes.finalize_response_node(state)
        
        final_response = result["agent_response"]
        
        # Should use template per §25
        self.assertIn("Created patient #123", final_response)
        self.assertIn("John Doe", final_response)
        self.assertIn("S******7A", final_response)  # Masked NRIC (6 asterisks + last 2 chars)
        self.assertIn("DOB: 1990-01-01", final_response)
        self.assertIn("Contact: 91234567", final_response)

    def test_finalize_response_template_application_update_patient(self):
        """Test response template application for successful patient update."""
        # Set up update context
        self.conv_state.intent = Intent.UPDATE_PATIENT
        self.conv_state.validated_fields = {
            "patient_id": 456,
            "contact_no": "98765432",
            "details": "Updated information"
        }
        
        mock_tool_result = ToolResponse(
            success=True,
            data={
                "id": 456,
                "first_name": "Jane",
                "last_name": "Smith", 
                "contact_no": "98765432",
                "details": "Updated information"
            },
            error=None
        )
        
        state = {
            **self.graph_state,
            "agent_response": "Patient updated",
            "tool_result": mock_tool_result,
            "conversation_state": self.conv_state
        }
        
        result = self.nodes.finalize_response_node(state)
        
        final_response = result["agent_response"]
        
        # Should use update template per §25
        self.assertIn("Updated patient #456", final_response)
        self.assertIn("changed Contact No, Details", final_response)

    def test_finalize_response_template_application_delete_patient(self):
        """Test response template application for successful patient deletion."""
        self.conv_state.intent = Intent.DELETE_PATIENT
        self.conv_state.validated_fields = {"patient_id": 789}
        
        mock_tool_result = ToolResponse(
            success=True,
            data=None,
            error=None
        )
        
        state = {
            **self.graph_state,
            "agent_response": "Patient deleted",
            "tool_result": mock_tool_result,
            "conversation_state": self.conv_state
        }
        
        result = self.nodes.finalize_response_node(state)
        
        final_response = result["agent_response"]
        
        # Should use deletion template per §25
        self.assertIn("✅ Deleted patient #789", final_response)

    def test_finalize_response_contextual_footer_addition(self):
        """Test addition of helpful contextual information."""
        # Set up pending workflow
        self.conv_state.pending_action = PendingAction.CREATE_PATIENT
        self.conv_state.confirmation_required = False
        
        state = {
            **self.graph_state,
            "agent_response": "Please provide the patient's first name.",
            "conversation_state": self.conv_state
        }
        
        result = self.nodes.finalize_response_node(state)
        
        final_response = result["agent_response"]
        
        # Should add cancellation guidance
        self.assertIn("cancel", final_response.lower())

    # ===== INTEGRATION TESTS =====
    
    def test_complete_flow_ingest_to_finalize(self):
        """Test complete 16-node flow from ingest to finalization."""
        # This test verifies the complete graph execution path
        
        # Execute a simple list patients workflow
        with patch.object(self.nodes.tool_manager, 'execute_tool') as mock_execute:
            mock_execute.return_value = ToolResponse(
                success=True,
                data=[{"id": 1, "first_name": "Test", "last_name": "Patient"}],
                error=None
            )
            
            # Process message through complete graph
            response, updated_state = self.graph.process_message_sync(
                "list all patients",
                self.conv_state
            )
            
            # Verify that the graph processed the message successfully
            self.assertIsNotNone(response)
            self.assertIn("Found 1 patient", response)
            
            # Verify that the state was updated properly  
            self.assertEqual(updated_state.intent, Intent.LIST_PATIENTS)
            
            # Verify that we went through all major phases:
            # 1. Message ingested and processed (no error in response)
            # 2. Intent was classified (Intent.LIST_PATIENTS)
            # 3. Tool was executed (mock was called)
            # 4. Response was finalized (contains template formatting)
            
            mock_execute.assert_called_once()
            self.assertIn("📋", response)  # List template formatting applied

    def test_long_conversation_maintains_context_through_summary(self):
        """Test that conversations >5 turns maintain context through summarization."""
        # Set up a conversation state with >5 messages to trigger summarization
        for i in range(6):
            self.conv_state.recent_messages.append(f"Turn {i+1}: Patient operation")
        
        # Mock Gemini client for summarization
        with patch('apps.hydrochat.gemini_client.GeminiClient') as mock_gemini_class:
            mock_client = MagicMock()
            mock_gemini_class.return_value = mock_client
            mock_client.api_key = "test_key"
            
            # Mock API response
            mock_summary_result = json.dumps({
                "salient_patients": [1],
                "pending_action": "CREATE_PATIENT",
                "unresolved_fields": [],
                "last_result": "Multiple patient operations completed"
            })
            
            # Mock the synchronous summarization method
            def mock_summarize_conversation(conv_state):
                conv_state.history_summary = mock_summary_result
                return mock_summary_result
            
            mock_client.summarize_conversation = mock_summarize_conversation
            
            # Test summarization node directly
            state = {
                **self.graph_state,
                "conversation_state": self.conv_state
            }
            
            result = self.nodes.summarize_history_node(state)
            
            # Should have history summary
            self.assertNotEqual(self.conv_state.history_summary, "")
            
            # Should have reduced message count 
            self.assertLessEqual(len(self.conv_state.recent_messages), 3)
            
            # Should proceed to finalization
            self.assertEqual(result["next_node"], "finalize_response")    # ===== ROUTING AND STATE MANAGEMENT TESTS =====
    
    def test_route_to_summarization_check(self):
        """Test routing logic for summarization check."""
        # Test case 1: Less than 5 messages -> finalize_response
        self.conv_state.recent_messages.clear()
        for i in range(3):
            self.conv_state.recent_messages.append(f"Message {i}")
        
        state = {
            **self.graph_state,
            "conversation_state": self.conv_state
        }
        
        route = self.graph._route_to_summarization_check(state)
        self.assertEqual(route, "finalize_response")
        
        # Test case 2: 5 or more messages -> summarize_history
        for i in range(3, 6):  # Add 2 more to reach 5
            self.conv_state.recent_messages.append(f"Message {i}")
        
        route = self.graph._route_to_summarization_check(state)
        self.assertEqual(route, "summarize_history")

    def test_route_from_ingest_message(self):
        """Test routing from ingest message node."""
        # Test normal classification route
        state = {**self.graph_state, "next_node": "classify_intent"}
        route = self.graph._route_from_ingest_message(state)
        self.assertEqual(route, "classify_intent")
        
        # Test cancellation route
        state = {**self.graph_state, "next_node": "handle_cancellation"}
        route = self.graph._route_from_ingest_message(state)
        self.assertEqual(route, "handle_cancellation")
        
        # Test default route
        state = {**self.graph_state, "next_node": None}
        route = self.graph._route_from_ingest_message(state)
        self.assertEqual(route, "classify_intent")

    # ===== ERROR HANDLING TESTS =====
    
    def test_error_handling_in_graph_execution(self):
        """Test that graph execution errors are handled gracefully with finalization."""
        # Force an error during graph execution by providing invalid state
        with patch.object(self.graph.graph, 'ainvoke', side_effect=Exception("Graph error")):
            response, updated_state = self.graph.process_message_sync(
                "test message",
                self.conv_state
            )
            
            # Should return error response with basic finalization applied
            self.assertIn("error", response.lower())
            
            # Should have error logged in state
            self.assertIsNotNone(updated_state.last_tool_error)
            if updated_state.last_tool_error:
                self.assertIn("Graph error", updated_state.last_tool_error["error"])

    def test_basic_finalization_pii_masking(self):
        """Test that basic finalization applies PII masking."""
        error_response = "Error processing patient S9876543Z request"
        
        finalized = self.graph._apply_basic_finalization(error_response, self.conv_state)
        
        # Should mask NRIC even in error messages
        self.assertNotIn("S9876543Z", finalized)
        self.assertIn("S******3Z", finalized)


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)
