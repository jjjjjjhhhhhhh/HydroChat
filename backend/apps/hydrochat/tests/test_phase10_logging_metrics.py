# Phase 10 Tests: Logging & Metrics Finalization for HydroChat

import logging
import json
import pytest
from datetime import datetime
from unittest.mock import Mock, patch, call
from collections import deque

from apps.hydrochat.logging_formatter import (
    HydroChatFormatter, MetricsLogger, setup_hydrochat_logging, metrics_logger
)
from apps.hydrochat.agent_stats import AgentStats, agent_stats
from apps.hydrochat.state import ConversationState
from apps.hydrochat.enums import Intent, PendingAction, ConfirmationType, DownloadStage
from apps.hydrochat.http_client import metrics as http_metrics
from apps.hydrochat.conversation_graph import ConversationGraph, GraphState
from apps.hydrochat.intent_classifier import is_stats_request


class TestHydroChatFormatter:
    """Test structured log formatter with NRIC masking."""
    
    def test_human_readable_formatting(self):
        """Test human-readable log formatting."""
        formatter = HydroChatFormatter(format_mode="human", mask_pii=True)
        
        # Create a log record
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="/path/to/file.py",
            lineno=42,
            msg="[TOOL] Testing log message",
            args=(),
            exc_info=None
        )
        record.module = "test_module"
        record.funcName = "test_function"
        
        formatted = formatter.format(record)
        
        # Should contain timestamp, level, module, and message
        assert "ℹ️ INFO" in formatted
        assert "[test_module]" in formatted
        assert "[TOOL] Testing log message" in formatted
        
    def test_json_formatting(self):
        """Test JSON log formatting."""
        formatter = HydroChatFormatter(format_mode="json", mask_pii=True)
        
        record = logging.LogRecord(
            name="test.logger",
            level=logging.ERROR,
            pathname="/path/to/file.py",
            lineno=42,
            msg="[ERROR] Test error message",
            args=(),
            exc_info=None
        )
        record.module = "test_module"
        record.funcName = "test_function"
        
        formatted = formatter.format(record)
        log_data = json.loads(formatted)
        
        # Verify JSON structure
        assert log_data["level"] == "ERROR"
        assert log_data["category"] == "ERROR"
        assert log_data["message"] == "[ERROR] Test error message"
        assert log_data["module"] == "test_module"
        assert log_data["function"] == "test_function"
        assert log_data["line"] == 42
        
    def test_nric_masking_in_logs(self):
        """Test automatic NRIC masking in log messages."""
        formatter = HydroChatFormatter(format_mode="human", mask_pii=True)
        
        # Test with NRIC in message
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="/path/to/file.py",
            lineno=42,
            msg="Processing patient S1234567A with NRIC T9876543B",
            args=(),
            exc_info=None
        )
        record.module = "test_module"
        record.funcName = "test_function"
        
        formatted = formatter.format(record)
        
        # NRICs should be masked
        assert "S******7A" in formatted
        assert "T******3B" in formatted
        assert "S1234567A" not in formatted
        assert "T9876543B" not in formatted
        
    def test_pii_masking_disabled(self):
        """Test formatter with PII masking disabled."""
        formatter = HydroChatFormatter(format_mode="human", mask_pii=False)
        
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="/path/to/file.py",
            lineno=42,
            msg="Processing patient S1234567A",
            args=(),
            exc_info=None
        )
        record.module = "test_module"
        record.funcName = "test_function"
        
        formatted = formatter.format(record)
        
        # NRIC should NOT be masked when masking disabled
        assert "S1234567A" in formatted
        assert "S******7A" not in formatted


class TestMetricsLogger:
    """Test metrics logging functionality."""
    
    def test_tool_call_logging(self):
        """Test tool call start/success/error logging."""
        state_metrics = {'total_api_calls': 0, 'successful_ops': 0, 'aborted_ops': 0, 'retries': 0}
        
        with patch('apps.hydrochat.logging_formatter.logging.getLogger') as mock_logger:
            mock_log_instance = Mock()
            mock_logger.return_value = mock_log_instance
            
            metrics_logger_instance = MetricsLogger()
            
            # Test tool call start
            metrics_logger_instance.log_tool_call_start("test_tool", state_metrics)
            mock_log_instance.info.assert_called_with("[TOOL] 🔧 Starting tool call: test_tool")
            
            # Test successful completion
            metrics_logger_instance.log_tool_call_success("test_tool", state_metrics, 1024)
            mock_log_instance.info.assert_called_with("[TOOL] ✅ Tool completed: test_tool (response: 1024 bytes)")
            assert state_metrics['successful_ops'] == 1
            
            # Test error logging
            test_error = Exception("Test error")
            metrics_logger_instance.log_tool_call_error("test_tool", test_error, state_metrics)
            mock_log_instance.error.assert_called_with("[TOOL] ❌ Tool failed: test_tool - Test error")
            assert state_metrics['aborted_ops'] == 1
            
    def test_retry_logging(self):
        """Test retry attempt logging."""
        state_metrics = {'retries': 0}
        
        with patch('apps.hydrochat.logging_formatter.logging.getLogger') as mock_logger:
            mock_log_instance = Mock()
            mock_logger.return_value = mock_log_instance
            
            metrics_logger_instance = MetricsLogger()
            metrics_logger_instance.log_retry_attempt("test_tool", 1, 2, state_metrics)
            
            mock_log_instance.warning.assert_called_with("[TOOL] 🔄 Retry 1/2 for test_tool")
            assert state_metrics['retries'] == 1
            
    def test_metrics_summary_logging(self):
        """Test comprehensive metrics summary logging."""
        state_metrics = {'total_api_calls': 10, 'successful_ops': 8, 'aborted_ops': 2, 'retries': 1}
        http_metrics = {'total_api_calls': 12, 'successful_ops': 10, 'aborted_ops': 2, 'retries': 2}
        
        with patch('apps.hydrochat.logging_formatter.logging.getLogger') as mock_logger:
            mock_log_instance = Mock()
            mock_logger.return_value = mock_log_instance
            
            metrics_logger_instance = MetricsLogger()
            metrics_logger_instance.log_metrics_summary(state_metrics, http_metrics)
            
            # Should log combined metrics summary
            expected_call = "[METRICS] 📊 Calls: 10, Success: 8, Errors: 2, Retries: 1, HTTP Calls: 12, Success: 10, Errors: 2, Retries: 2"
            mock_log_instance.info.assert_called_with(expected_call)


class TestAgentStats:
    """Test agent statistics functionality."""
    
    def create_test_conversation_state(self):
        """Create a test conversation state with sample metrics."""
        state = ConversationState()
        state.metrics = {
            'total_api_calls': 15,
            'successful_ops': 12,
            'aborted_ops': 3,
            'retries': 2
        }
        state.intent = Intent.CREATE_PATIENT
        state.pending_action = PendingAction.NONE
        state.recent_messages = deque(["User: test", "Agent: response"], maxlen=5)
        state.patient_cache = [{"id": 1, "name": "Test Patient"}]
        state.selected_patient_id = 1
        state.scan_results_buffer = [{"id": 1, "scan_id": "test"}]
        return state
        
    def test_generate_stats_summary(self):
        """Test comprehensive stats generation."""
        conv_state = self.create_test_conversation_state()
        
        # Mock HTTP metrics
        with patch('apps.hydrochat.agent_stats.http_metrics', {'total_api_calls': 16, 'successful_ops': 13, 'aborted_ops': 3, 'retries': 2}):
            stats = agent_stats.generate_stats_summary(conv_state)
            
            # Verify structure
            assert 'timestamp' in stats
            assert 'conversation_metrics' in stats
            assert 'http_client_metrics' in stats
            assert 'conversation_state' in stats
            assert 'performance_indicators' in stats
            assert 'session_summary' in stats
            
            # Verify metrics calculation
            conv_metrics = stats['conversation_metrics']
            assert conv_metrics['total_operations'] == 15  # 12 + 3
            assert conv_metrics['successful_operations'] == 12
            assert conv_metrics['aborted_operations'] == 3
            assert conv_metrics['success_rate_percent'] == 80.0  # 12/15 * 100
            
    def test_format_stats_for_user(self):
        """Test user-friendly stats formatting."""
        conv_state = self.create_test_conversation_state()
        
        with patch('apps.hydrochat.agent_stats.http_metrics', {'total_api_calls': 16, 'successful_ops': 13, 'aborted_ops': 3, 'retries': 2}):
            stats = agent_stats.generate_stats_summary(conv_state)
            formatted = agent_stats.format_stats_for_user(stats)
            
            # Should be user-friendly text format
            assert "📊 **HydroChat Agent Statistics**" in formatted
            assert "Operations Summary:" in formatted
            assert "Total Operations: 15" in formatted
            assert "Successful: 12 (80.0%)" in formatted
            assert "HTTP Client Performance:" in formatted
            assert "Current Session:" in formatted
            assert "Create Patient" in formatted  # Intent should be formatted
            
    def test_performance_indicators(self):
        """Test performance warning generation."""
        conv_state = self.create_test_conversation_state()
        # Set high error rate
        conv_state.metrics = {
            'total_api_calls': 10,
            'successful_ops': 6,
            'aborted_ops': 4,  # 40% error rate
            'retries': 8  # High retry count
        }
        
        with patch('apps.hydrochat.agent_stats.http_metrics', {'total_api_calls': 10, 'successful_ops': 6, 'aborted_ops': 4, 'retries': 8}):
            stats = agent_stats.generate_stats_summary(conv_state)
            perf = stats['performance_indicators']
            
            # Should have warnings for high error rate and retry count
            assert len(perf['warnings']) >= 2
            assert any('High error rate' in warning for warning in perf['warnings'])
            assert any('High retry count' in warning for warning in perf['warnings'])
            assert len(perf['recommendations']) > 0
            assert perf['overall_health'] == 'needs_attention'
            
    def test_reset_metrics(self):
        """Test metrics reset functionality."""
        conv_state = self.create_test_conversation_state()
        
        original_metrics = conv_state.metrics.copy()
        
        with patch('apps.hydrochat.agent_stats.http_metrics', {'total_api_calls': 16, 'successful_ops': 13, 'aborted_ops': 3, 'retries': 2}):
            result = agent_stats.reset_metrics(conv_state, reset_http_metrics=True)
            
            # Verify metrics were reset
            assert all(value == 0 for value in conv_state.metrics.values())
            
            # Verify previous values returned
            assert result['previous_state_metrics'] == original_metrics
            assert result['previous_http_metrics'] is not None


class TestStatsIntentClassification:
    """Test stats command recognition in intent classification."""
    
    def test_stats_pattern_recognition(self):
        """Test various stats command patterns."""
        # Test positive cases
        assert is_stats_request("show stats")
        assert is_stats_request("agent statistics")
        assert is_stats_request("performance metrics")
        assert is_stats_request("system status")
        assert is_stats_request("give me a summary")
        assert is_stats_request("what are the stats?")
        
        # Test negative cases
        assert not is_stats_request("create patient")
        assert not is_stats_request("show patient details")
        assert not is_stats_request("list patients")
        assert not is_stats_request("scan results")


class TestConversationGraphStatsIntegration:
    """Test stats integration in conversation graph."""
    
    @pytest.fixture
    def mock_http_client(self):
        """Mock HTTP client for testing."""
        client = Mock()
        client.request.return_value = Mock(status_code=200, json=lambda: {"test": "data"})
        return client
        
    def test_stats_node_execution(self, mock_http_client):
        """Test stats node in conversation graph."""
        # Create conversation graph with mock client
        graph = ConversationGraph(mock_http_client)
        
        # Create test state with stats request
        conv_state = ConversationState()
        conv_state.metrics = {
            'total_api_calls': 5,
            'successful_ops': 4,
            'aborted_ops': 1,
            'retries': 0
        }
        
        state: GraphState = {
            "user_message": "show agent stats",
            "conversation_state": conv_state,
            "agent_response": "",
            "classified_intent": None,
            "extracted_fields": {},
            "tool_result": None,
            "next_node": "",
            "should_end": False
        }
        
        # Execute stats node directly
        result = graph.nodes.provide_agent_stats_node(state)
        
        # Verify response
        assert result["should_end"] is True
        assert "📊 **HydroChat Agent Statistics**" in result["agent_response"] or "📊 **Basic Agent Statistics**" in result["agent_response"]
        
    def test_stats_intent_routing(self, mock_http_client):
        """Test that stats requests route to stats node."""
        graph = ConversationGraph(mock_http_client)
        
        # Create state with stats request
        conv_state = ConversationState()
        
        state: GraphState = {
            "user_message": "show me the statistics",
            "conversation_state": conv_state,
            "agent_response": "",
            "classified_intent": None,
            "extracted_fields": {},
            "tool_result": None,
            "next_node": "",
            "should_end": False
        }
        
        # Execute intent classification
        result = graph.nodes.classify_intent_node(state)
        
        # Should route to stats node
        assert result["next_node"] == "provide_agent_stats"
        assert result["classified_intent"] is None  # Special handling


class TestLoggingSetup:
    """Test logging configuration and setup."""
    
    def test_setup_hydrochat_logging(self):
        """Test logging setup with custom formatter."""
        logger = setup_hydrochat_logging(
            level=logging.DEBUG,
            format_mode="human",
            mask_pii=True,
            logger_name="test.hydrochat"
        )
        
        assert logger.level == logging.DEBUG
        assert len(logger.handlers) == 1
        assert isinstance(logger.handlers[0].formatter, HydroChatFormatter)
        assert logger.propagate is False
        
    def test_logging_pii_protection(self):
        """Test that raw NRICs are not logged."""
        # This test validates the Phase 10 exit criteria requirement
        logger = setup_hydrochat_logging(logger_name="test.pii.protection")
        
        # Capture log output
        with patch.object(logger, 'info') as mock_info:
            # Create formatter manually to test
            formatter = HydroChatFormatter(format_mode="human", mask_pii=True)
            
            # Create log record with NRIC
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="/test.py",
                lineno=1,
                msg="Patient NRIC: S1234567A",
                args=(),
                exc_info=None
            )
            record.module = "test"
            record.funcName = "test"
            
            formatted = formatter.format(record)
            
            # Verify raw NRIC is not present
            assert "S1234567A" not in formatted
            assert "S******7A" in formatted


# Phase 10 Exit Criteria Test
class TestPhase10ExitCriteria:
    """Verify all Phase 10 exit criteria are met."""
    
    def test_structured_log_formatter_implemented(self):
        """Test: Structured log formatter + mask enforcement."""
        formatter = HydroChatFormatter(format_mode="json", mask_pii=True)
        assert formatter is not None
        assert formatter.mask_pii is True
        
        # Test NRIC masking
        record = logging.LogRecord("test", logging.INFO, "/test.py", 1, "NRIC S1234567A", (), None)
        record.module = "test"
        record.funcName = "test"
        formatted = formatter.format(record)
        
        log_data = json.loads(formatted)
        assert "S******7A" in log_data["message"]
        assert "S1234567A" not in log_data["message"]
        
    def test_agent_stats_command_implemented(self):
        """Test: Agent stats command implementation."""
        conv_state = ConversationState()
        conv_state.metrics = {'total_api_calls': 10, 'successful_ops': 8, 'aborted_ops': 2, 'retries': 1}
        
        stats = agent_stats.generate_stats_summary(conv_state)
        formatted = agent_stats.format_stats_for_user(stats)
        
        assert "Agent Statistics" in formatted
        assert "Total Operations:" in formatted
        assert "HTTP Client Performance:" in formatted
        
    def test_metrics_increments_for_tool_calls(self):
        """Test: Metrics increments for each tool call & retry."""
        state_metrics = {'successful_ops': 0, 'aborted_ops': 0, 'retries': 0}
        
        # Test success increment
        metrics_logger.log_tool_call_success("test_tool", state_metrics)
        assert state_metrics['successful_ops'] == 1
        
        # Test error increment
        metrics_logger.log_tool_call_error("test_tool", Exception("test"), state_metrics)
        assert state_metrics['aborted_ops'] == 1
        
        # Test retry increment
        metrics_logger.log_retry_attempt("test_tool", 1, 2, state_metrics)
        assert state_metrics['retries'] == 1
        
    def test_stats_output_after_series_of_calls(self):
        """Test: stats output after series of calls (exit criteria)."""
        conv_state = ConversationState()
        
        # Simulate series of calls
        conv_state.metrics['total_api_calls'] = 5
        conv_state.metrics['successful_ops'] = 4
        conv_state.metrics['aborted_ops'] = 1
        conv_state.metrics['retries'] = 2
        
        # Generate stats
        stats = agent_stats.generate_stats_summary(conv_state)
        formatted = agent_stats.format_stats_for_user(stats)
        
        # Verify stats reflect the series of calls
        assert "Total Operations: 5" in formatted
        assert "Successful: 4 (80.0%)" in formatted
        assert "Failed: 1" in formatted
        assert "Retry Attempts: 2" in formatted
        
    def test_raw_nric_absent_from_logs(self):
        """Test: PII leakage prevention - raw NRIC absent (exit criteria)."""
        formatter = HydroChatFormatter(format_mode="human", mask_pii=True)
        
        # Test multiple NRIC formats
        test_nrics = ["S1234567A", "T9876543B", "F5555555C", "G1111111Z"]
        
        for nric in test_nrics:
            record = logging.LogRecord("test", logging.INFO, "/test.py", 1, f"Processing {nric}", (), None)
            record.module = "test"
            record.funcName = "test"
            
            formatted = formatter.format(record)
            
            # Raw NRIC must be absent
            assert nric not in formatted, f"Raw NRIC {nric} found in log output"
            
            # Masked version should be present
            expected_mask = f"{nric[0]}******{nric[-2:]}"
            assert expected_mask in formatted, f"Expected masked NRIC {expected_mask} not found"
