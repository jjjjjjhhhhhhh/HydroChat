"""
Phase 9 Tests: Scan Results Two-Stage & Pagination Enhancements

Tests for:
1. Enhanced pagination handling ("show more scans")
2. Two-stage STL confirmation flow with pagination
3. Depth map augmentation requests 
4. Proper offset tracking and state management
"""

import pytest
from unittest.mock import Mock, patch
from collections import deque

from apps.hydrochat.conversation_graph import ConversationGraph
from apps.hydrochat.state import ConversationState
from apps.hydrochat.enums import (
    Intent, PendingAction, ConfirmationType, 
    DownloadStage
)
from apps.hydrochat.http_client import HttpClient


@pytest.fixture
def mock_http_client():
    """Mock HTTP client for tests."""
    client = Mock(spec=HttpClient)
    return client


@pytest.fixture
def conversation_graph(mock_http_client):
    """Create conversation graph with mocked HTTP client."""
    return ConversationGraph(mock_http_client)


@pytest.fixture 
def conv_state_with_scan_results():
    """Conversation state with scan results buffer populated."""
    state = ConversationState()
    
    # Set up scan results buffer with 15 results
    state.scan_results_buffer = [
        {
            'id': i+1,
            'scan_id': f'SCAN_{i+1:03d}',
            'scan_date': f'2024-01-{i+1:02d}',
            'preview_image': f'http://example.com/preview_{i+1}.jpg',
            'stl_file': f'http://example.com/stl_{i+1}.stl' if i % 2 == 0 else None,
            'depth_map_8bit': f'http://example.com/depth8_{i+1}.png' if i % 3 == 0 else None,
            'depth_map_16bit': f'http://example.com/depth16_{i+1}.png' if i % 3 == 0 else None,
            'volume_estimate': f'{100 + i * 10}',
            'created_at': f'2024-01-{i+1:02d}T10:00:00Z'
        }
        for i in range(15)  # 15 total results
    ]
    
    state.selected_patient_id = 5
    state.scan_display_limit = 10  # Default display limit
    state.scan_pagination_offset = 0
    state.download_stage = DownloadStage.NONE
    
    return state


class TestPaginationHandling:
    """Test pagination functionality."""

    def test_show_more_scans_first_page(self, conversation_graph, conv_state_with_scan_results):
        """Test showing more scans when on first page."""
        # Set up state - first 10 results shown, offset at 10
        conv_state_with_scan_results.scan_pagination_offset = 10
        conv_state_with_scan_results.download_stage = DownloadStage.PREVIEW_SHOWN
        
        state = {
            "user_message": "show more scans", 
            "conversation_state": conv_state_with_scan_results
        }
        
        result = conversation_graph.nodes.show_more_scans_node(state)
        
        # Should show results 11-15 (5 remaining)
        assert "showing 11-15 of 15" in result["agent_response"]
        assert "**11. Scan SCAN_011**" in result["agent_response"]
        assert "**15. Scan SCAN_015**" in result["agent_response"]
        
        # Offset should be updated to 15 
        assert conv_state_with_scan_results.scan_pagination_offset == 15
        
        # Should indicate all results shown
        assert "All scan results have been displayed" in result["agent_response"]
        
        # Should ask for STL confirmation 
        assert "Would you like to download STL files" in result["agent_response"]
        assert conv_state_with_scan_results.confirmation_required is True

    def test_show_more_scans_no_more_results(self, conversation_graph, conv_state_with_scan_results):
        """Test showing more when all results already displayed."""
        # Set offset beyond available results
        conv_state_with_scan_results.scan_pagination_offset = 15
        
        state = {
            "user_message": "show more scans",
            "conversation_state": conv_state_with_scan_results
        }
        
        result = conversation_graph.nodes.show_more_scans_node(state)
        
        # Should indicate all results displayed
        assert "All 15 scan results have been displayed" in result["agent_response"]
        assert result["should_end"] is True

    def test_show_more_scans_no_buffer(self, conversation_graph):
        """Test showing more when no scan results in buffer."""
        conv_state = ConversationState()
        
        state = {
            "user_message": "show more scans",
            "conversation_state": conv_state
        }
        
        result = conversation_graph.nodes.show_more_scans_node(state)
        
        # Should show error
        assert "No scan results available" in result["agent_response"]
        assert result["should_end"] is False

    def test_pagination_offset_tracking(self, conversation_graph, conv_state_with_scan_results):
        """Test proper offset tracking across multiple pagination requests."""
        # Start with first page shown (offset = 10)
        conv_state_with_scan_results.scan_pagination_offset = 10
        
        state = {
            "user_message": "show more scans",
            "conversation_state": conv_state_with_scan_results
        }
        
        result = conversation_graph.nodes.show_more_scans_node(state)
        
        # Offset should advance to end (15)
        assert conv_state_with_scan_results.scan_pagination_offset == 15
        
        # Try showing more again - should indicate all done
        result2 = conversation_graph.nodes.show_more_scans_node(state)
        assert "All 15 scan results have been displayed" in result2["agent_response"]


class TestDepthMapHandling:
    """Test depth map functionality."""

    def test_provide_depth_maps_with_maps(self, conversation_graph, conv_state_with_scan_results):
        """Test providing depth maps when available."""
        # Set offset to show first 10 results
        conv_state_with_scan_results.scan_pagination_offset = 10
        
        state = {
            "user_message": "show depth maps",
            "conversation_state": conv_state_with_scan_results
        }
        
        result = conversation_graph.nodes.provide_depth_maps_node(state)
        
        # Should show depth map links where available (every 3rd result: 1, 4, 7, 10)
        assert "🗺️ **Depth Map Information" in result["agent_response"]
        assert "8-bit Depth Map" in result["agent_response"] 
        assert "16-bit Depth Map" in result["agent_response"]
        assert "No depth maps available" in result["agent_response"]  # For some results
        
        # Should count available maps
        assert "depth map(s) available" in result["agent_response"]

    def test_provide_depth_maps_none_available(self, conversation_graph):
        """Test depth maps when none available."""
        conv_state = ConversationState()
        # Set up results with no depth maps
        conv_state.scan_results_buffer = [
            {
                'scan_id': 'SCAN_001',
                'scan_date': '2024-01-01', 
                # No depth_map_8bit or depth_map_16bit
            }
        ]
        conv_state.selected_patient_id = 5
        conv_state.scan_pagination_offset = 1
        
        state = {
            "user_message": "show depth maps",
            "conversation_state": conv_state
        }
        
        result = conversation_graph.nodes.provide_depth_maps_node(state)
        
        # Should indicate none available
        assert "No depth maps are available" in result["agent_response"]

    def test_provide_depth_maps_no_buffer(self, conversation_graph):
        """Test depth maps when no scan results in buffer."""
        conv_state = ConversationState()
        
        state = {
            "user_message": "show depth maps",
            "conversation_state": conv_state
        }
        
        result = conversation_graph.nodes.provide_depth_maps_node(state)
        
        # Should show error
        assert "No scan results available for depth map display" in result["agent_response"]


class TestIntentClassificationEnhancements:
    """Test enhanced intent classification for pagination and depth maps."""

    def test_classify_show_more_scans(self, conversation_graph):
        """Test detection of show more scans intent."""
        from apps.hydrochat.intent_classifier import is_show_more_scans
        
        # Test various phrasings
        assert is_show_more_scans("show more scans") is True
        assert is_show_more_scans("display more scans") is True  
        assert is_show_more_scans("show additional results") is True
        assert is_show_more_scans("display next scans") is True
        
        # Test negative cases
        assert is_show_more_scans("show scans") is False
        assert is_show_more_scans("more patients") is False
        assert is_show_more_scans("show more") is False

    def test_classify_depth_map_request(self, conversation_graph):
        """Test detection of depth map requests.""" 
        from apps.hydrochat.intent_classifier import is_depth_map_request
        
        # Test various phrasings
        assert is_depth_map_request("show depth") is True
        assert is_depth_map_request("depth map") is True
        assert is_depth_map_request("show depth map") is True
        
        # Test negative cases
        assert is_depth_map_request("show scans") is False
        assert is_depth_map_request("patient depth") is False

    def test_classify_intent_with_pagination_context(self, conversation_graph, conv_state_with_scan_results):
        """Test intent classification routes to pagination when context available."""
        state = {
            "user_message": "show more scans",
            "conversation_state": conv_state_with_scan_results
        }
        
        result = conversation_graph.nodes.classify_intent_node(state)
        
        # Should route to show_more_scans node
        assert result["next_node"] == "show_more_scans"
        assert result["classified_intent"] is None  # Special handling

    def test_classify_intent_with_depth_context(self, conversation_graph, conv_state_with_scan_results):
        """Test intent classification routes to depth maps when context available.""" 
        state = {
            "user_message": "show depth maps",
            "conversation_state": conv_state_with_scan_results  
        }
        
        result = conversation_graph.nodes.classify_intent_node(state)
        
        # Should route to provide_depth_maps node
        assert result["next_node"] == "provide_depth_maps"
        assert result["classified_intent"] is None

    def test_classify_intent_no_context(self, conversation_graph):
        """Test intent classification without scan context falls back to normal."""
        conv_state = ConversationState()  # Empty buffer
        
        state = {
            "user_message": "show more scans", 
            "conversation_state": conv_state
        }
        
        result = conversation_graph.nodes.classify_intent_node(state)
        
        # Should fall back to normal intent classification
        assert result["next_node"] != "show_more_scans"
        # Should classify as GET_SCAN_RESULTS since it contains "scan"
        assert result["classified_intent"] == Intent.GET_SCAN_RESULTS


class TestTwoStageSTLFlow:
    """Test two-stage STL confirmation flow with pagination."""

    def test_stl_confirmation_after_pagination(self, conversation_graph, conv_state_with_scan_results):
        """Test STL confirmation prompt appears after pagination."""
        # Set up state after first page shown
        conv_state_with_scan_results.scan_pagination_offset = 10
        conv_state_with_scan_results.download_stage = DownloadStage.PREVIEW_SHOWN
        
        state = {
            "user_message": "show more scans",
            "conversation_state": conv_state_with_scan_results
        }
        
        result = conversation_graph.nodes.show_more_scans_node(state)
        
        # Should ask for STL confirmation for additional scans
        assert "Would you like to download STL files for these additional scans?" in result["agent_response"]
        assert conv_state_with_scan_results.confirmation_required is True
        assert conv_state_with_scan_results.awaiting_confirmation_type == ConfirmationType.DOWNLOAD_STL

    def test_stl_confirmation_after_stl_links_sent(self, conversation_graph, conv_state_with_scan_results):
        """Test STL confirmation when links already sent for previous batch."""
        # Set up state after STL links already provided 
        conv_state_with_scan_results.scan_pagination_offset = 10
        conv_state_with_scan_results.download_stage = DownloadStage.STL_LINKS_SENT
        
        state = {
            "user_message": "show more scans",
            "conversation_state": conv_state_with_scan_results
        }
        
        result = conversation_graph.nodes.show_more_scans_node(state)
        
        # Should ask for STL links for additional scans
        assert "Would you like STL download links for these additional scans?" in result["agent_response"]
        assert conv_state_with_scan_results.confirmation_required is True
        # Download stage should be reset to allow new links
        assert conv_state_with_scan_results.download_stage == DownloadStage.PREVIEW_SHOWN

    def test_no_stl_exposure_before_confirmation(self, conversation_graph, conv_state_with_scan_results):
        """Test STL links not exposed in preview mode."""
        # Set up pagination request in preview mode
        conv_state_with_scan_results.scan_pagination_offset = 10
        conv_state_with_scan_results.download_stage = DownloadStage.PREVIEW_SHOWN
        
        state = {
            "user_message": "show more scans",
            "conversation_state": conv_state_with_scan_results
        }
        
        result = conversation_graph.nodes.show_more_scans_node(state)
        
        # Response should NOT contain direct STL file links
        assert "stl_file" not in result["agent_response"].lower()
        assert "[download stl file]" not in result["agent_response"].lower()  # No actual download links
        # But should contain preview images and volume estimates  
        assert "Preview Image" in result["agent_response"]
        assert "Volume:" in result["agent_response"]


class TestPhase9Integration:
    """Integration tests for Phase 9 functionality."""

    def test_end_to_end_pagination_flow(self, conversation_graph, conv_state_with_scan_results, mock_http_client):
        """Test complete pagination flow from scan results to STL links."""
        # Step 1: Initial scan results (first 10 shown)
        conv_state_with_scan_results.scan_pagination_offset = 10
        conv_state_with_scan_results.download_stage = DownloadStage.PREVIEW_SHOWN
        conv_state_with_scan_results.confirmation_required = True
        
        # Step 2: User requests more scans
        show_more_state = {
            "user_message": "show more scans",
            "conversation_state": conv_state_with_scan_results
        }
        
        more_result = conversation_graph.nodes.show_more_scans_node(show_more_state)
        
        # Should show additional results with confirmation prompt
        assert "showing 11-15 of 15" in more_result["agent_response"]
        assert "Would you like to download STL files" in more_result["agent_response"]
        
        # Step 3: User confirms STL download 
        confirm_state = {
            "user_message": "yes",
            "conversation_state": conv_state_with_scan_results
        }
        
        confirm_result = conversation_graph.nodes.handle_confirmation_node(confirm_state)
        assert confirm_result["next_node"] == "provide_stl_links"
        
        # Step 4: Provide STL links
        stl_result = conversation_graph.nodes.provide_stl_links_node(confirm_state)
        
        # Should provide STL links for displayed results (up to pagination offset)
        assert "📥 **STL Download Links" in stl_result["agent_response"]
        assert "Download STL File" in stl_result["agent_response"]
        assert conv_state_with_scan_results.download_stage == DownloadStage.STL_LINKS_SENT

    def test_phase9_exit_criteria_pagination(self, conversation_graph, conv_state_with_scan_results):
        """Verify Phase 9 exit criteria: show 20 results via two 'show more' commands."""
        # Create buffer with 25 results to test showing 20 via pagination
        conv_state_with_scan_results.scan_results_buffer = [
            {
                'id': i+1,
                'scan_id': f'SCAN_{i+1:03d}', 
                'scan_date': f'2024-01-{i+1:02d}',
                'preview_image': f'http://example.com/preview_{i+1}.jpg'
            }
            for i in range(25)
        ]
        
        # Initial state: 10 results shown (offset = 10)
        conv_state_with_scan_results.scan_pagination_offset = 10
        
        # First "show more" - should show results 11-20
        state1 = {
            "user_message": "show more scans",
            "conversation_state": conv_state_with_scan_results
        }
        result1 = conversation_graph.nodes.show_more_scans_node(state1)
        
        # Should show results 11-20
        assert "showing 11-20 of 25" in result1["agent_response"]
        assert conv_state_with_scan_results.scan_pagination_offset == 20
        
        # Second "show more" - should show results 21-25
        state2 = {
            "user_message": "show more scans", 
            "conversation_state": conv_state_with_scan_results
        }
        result2 = conversation_graph.nodes.show_more_scans_node(state2)
        
        # Should show final 5 results
        assert "showing 21-25 of 25" in result2["agent_response"] 
        assert conv_state_with_scan_results.scan_pagination_offset == 25
        assert "All scan results have been displayed" in result2["agent_response"]
        
        # Total shown: 10 (initial) + 10 (first more) + 5 (second more) = 25
        # Phase 9 criteria met: showed more than 20 results via multiple commands

    def test_stl_links_not_exposed_before_confirmation(self, conversation_graph, conv_state_with_scan_results):
        """Verify Phase 9 exit criteria: STL links absent before confirmation."""
        # Set up scan results with STL files
        for result in conv_state_with_scan_results.scan_results_buffer[:3]:
            result['stl_file'] = f"http://example.com/stl_{result['id']}.stl"
        
        conv_state_with_scan_results.scan_pagination_offset = 10
        conv_state_with_scan_results.download_stage = DownloadStage.PREVIEW_SHOWN
        
        state = {
            "user_message": "show more scans",
            "conversation_state": conv_state_with_scan_results
        }
        
        result = conversation_graph.nodes.show_more_scans_node(state)
        
        # Critical: STL file URLs should NOT appear in response before confirmation
        response_text = result["agent_response"].lower()
        assert "http://example.com/stl_" not in response_text
        assert "[download stl file]" not in response_text  # No actual download links
        
        # But preview images should still be shown
        assert "preview image" in response_text
        
        # And confirmation prompt should be present (this is expected)
        assert "would you like to download stl files" in response_text
