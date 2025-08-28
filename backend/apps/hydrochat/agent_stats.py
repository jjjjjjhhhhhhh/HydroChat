# Phase 10: Agent Stats Command Implementation for HydroChat
# Phase 14: Extended with Gemini API metrics per §17

from typing import Dict, Any, Optional, List
from datetime import datetime
import logging

from .state import ConversationState
from .http_client import metrics as http_metrics
from .logging_formatter import metrics_logger


class AgentStats:
    """
    Agent statistics command implementation for HydroChat.
    Provides comprehensive metrics about conversation state and HTTP operations.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
    def generate_stats_summary(self, conversation_state: ConversationState) -> Dict[str, Any]:
        """
        Generate comprehensive statistics summary from conversation state.
        
        Args:
            conversation_state: Current conversation state with metrics
            
        Returns:
            Dictionary containing formatted statistics
        """
        self.logger.debug("[STATS] 📊 Generating agent statistics summary")
        
        # Extract metrics from different sources
        state_metrics = conversation_state.metrics.copy()
        http_metrics_copy = http_metrics.copy()
        
        # Phase 14: Extract Gemini API metrics per §17
        gemini_metrics = {}
        try:
            from .gemini_client import get_gemini_metrics
            gemini_metrics = get_gemini_metrics()
        except ImportError:
            self.logger.debug("[STATS] Gemini client not available, skipping LLM metrics")
        
        # Calculate derived metrics
        total_operations = state_metrics.get('successful_ops', 0) + state_metrics.get('aborted_ops', 0)
        success_rate = (state_metrics.get('successful_ops', 0) / total_operations * 100) if total_operations > 0 else 0
        
        # Analyze conversation flow
        conversation_analysis = self._analyze_conversation_state(conversation_state)
        
        # Build comprehensive stats response
        stats = {
            'timestamp': datetime.now().isoformat(),
            'conversation_metrics': {
                'total_operations': total_operations,
                'successful_operations': state_metrics.get('successful_ops', 0),
                'aborted_operations': state_metrics.get('aborted_ops', 0),
                'success_rate_percent': round(success_rate, 1),
                'retry_attempts': state_metrics.get('retries', 0),
                'total_api_calls': state_metrics.get('total_api_calls', 0)
            },
            'http_client_metrics': {
                'total_requests': http_metrics_copy.get('total_api_calls', 0),
                'successful_requests': http_metrics_copy.get('successful_ops', 0),
                'failed_requests': http_metrics_copy.get('aborted_ops', 0),
                'retry_attempts': http_metrics_copy.get('retries', 0)
            },
            'llm_api_metrics': {
                'total_calls': gemini_metrics.get('successful_calls', 0) + gemini_metrics.get('failed_calls', 0),
                'successful_calls': gemini_metrics.get('successful_calls', 0),
                'failed_calls': gemini_metrics.get('failed_calls', 0),
                'total_tokens_used': gemini_metrics.get('total_tokens_used', 0),
                'estimated_cost_usd': round(gemini_metrics.get('total_cost_usd', 0), 4),
                'last_call_timestamp': gemini_metrics.get('last_call_timestamp')
            },
            'conversation_state': conversation_analysis,
            'performance_indicators': self._generate_performance_indicators(state_metrics, http_metrics_copy),
            'session_summary': self._generate_session_summary(conversation_state)
        }
        
        self.logger.info(f"[STATS] ✅ Stats generated - {total_operations} ops, {success_rate:.1f}% success rate")
        
        return stats
    
    def format_stats_for_user(self, stats: Dict[str, Any]) -> str:
        """
        Format statistics into user-friendly text response.
        
        Args:
            stats: Statistics dictionary from generate_stats_summary
            
        Returns:
            Formatted text response for user
        """
        conv_metrics = stats['conversation_metrics']
        http_metrics = stats['http_client_metrics']
        session = stats['session_summary']
        perf = stats['performance_indicators']
        
        response = "📊 **HydroChat Agent Statistics**\n\n"
        
        # Operation Summary
        response += "**Operations Summary:**\n"
        response += f"• Total Operations: {conv_metrics['total_operations']}\n"
        response += f"• Successful: {conv_metrics['successful_operations']} ({conv_metrics['success_rate_percent']}%)\n"
        response += f"• Failed: {conv_metrics['aborted_operations']}\n"
        response += f"• Retry Attempts: {conv_metrics['retry_attempts']}\n\n"
        
        # HTTP Performance
        response += "**HTTP Client Performance:**\n"
        response += f"• Total Requests: {http_metrics['total_requests']}\n"
        response += f"• Successful: {http_metrics['successful_requests']}\n"
        response += f"• Failed: {http_metrics['failed_requests']}\n"
        response += f"• Retries: {http_metrics['retry_attempts']}\n\n"
        
        # Session Information
        response += "**Current Session:**\n"
        response += f"• Intent: {session['current_intent']}\n"
        response += f"• Pending Action: {session['pending_action']}\n"
        response += f"• Messages Processed: {session['messages_processed']}\n"
        response += f"• Cache Status: {session['cache_status']}\n"
        
        if session['selected_patient']:
            response += f"• Selected Patient: {session['selected_patient']}\n"
            
        if session['scan_results_available']:
            response += f"• Scan Results: {session['scan_results_count']} available\n"
            
        response += f"• Confirmation Required: {'Yes' if session['awaiting_confirmation'] else 'No'}\n\n"
        
        # Performance Indicators
        if perf['warnings'] or perf['recommendations']:
            response += "**Performance Notes:**\n"
            for warning in perf['warnings']:
                response += f"⚠️ {warning}\n"
            for rec in perf['recommendations']:
                response += f"💡 {rec}\n"
        
        return response.strip()
    
    def _analyze_conversation_state(self, state: ConversationState) -> Dict[str, Any]:
        """Analyze current conversation state for insights."""
        return {
            'current_intent': state.intent.name,
            'pending_action': state.pending_action.name,
            'has_pending_fields': len(state.pending_fields) > 0,
            'pending_field_count': len(state.pending_fields),
            'clarification_count': state.clarification_loop_count,
            'cache_entries': len(state.patient_cache),
            'disambiguation_options': len(state.disambiguation_options),
            'confirmation_required': state.confirmation_required,
            'confirmation_type': state.awaiting_confirmation_type.name,
            'download_stage': state.download_stage.name,
            'scan_results_buffer_size': len(state.scan_results_buffer),
            'pagination_offset': state.scan_pagination_offset
        }
    
    def _generate_session_summary(self, state: ConversationState) -> Dict[str, Any]:
        """Generate user-facing session summary."""
        return {
            'current_intent': state.intent.name.replace('_', ' ').title(),
            'pending_action': state.pending_action.name.replace('_', ' ').title(),
            'messages_processed': len(state.recent_messages),
            'cache_status': f"{len(state.patient_cache)} patients cached" if state.patient_cache else "No cache",
            'selected_patient': f"ID {state.selected_patient_id}" if state.selected_patient_id else None,
            'awaiting_confirmation': state.confirmation_required,
            'confirmation_type': state.awaiting_confirmation_type.name.replace('_', ' ').title(),
            'scan_results_available': len(state.scan_results_buffer) > 0,
            'scan_results_count': len(state.scan_results_buffer),
            'current_page_offset': state.scan_pagination_offset if state.scan_results_buffer else None
        }
    
    def _generate_performance_indicators(self, state_metrics: Dict[str, int], 
                                       http_metrics: Dict[str, int]) -> Dict[str, Any]:
        """Generate performance warnings and recommendations."""
        warnings = []
        recommendations = []
        
        # Check error rates
        total_ops = state_metrics.get('successful_ops', 0) + state_metrics.get('aborted_ops', 0)
        if total_ops > 0:
            error_rate = state_metrics.get('aborted_ops', 0) / total_ops
            if error_rate > 0.2:  # More than 20% error rate
                warnings.append(f"High error rate: {error_rate:.1%} of operations failed")
                
        # Check retry frequency
        if state_metrics.get('retries', 0) > 5:
            warnings.append(f"High retry count: {state_metrics['retries']} attempts")
            recommendations.append("Consider checking network connectivity")
            
        # Check HTTP vs conversation metrics alignment
        http_calls = http_metrics.get('total_api_calls', 0)
        conv_calls = state_metrics.get('total_api_calls', 0)
        if abs(http_calls - conv_calls) > 2:  # Allow small discrepancy
            warnings.append("Metrics discrepancy detected between HTTP client and conversation state")
            
        return {
            'warnings': warnings,
            'recommendations': recommendations,
            'overall_health': 'good' if not warnings else 'needs_attention'
        }
    
    def reset_metrics(self, conversation_state: ConversationState, 
                     reset_http_metrics: bool = False) -> Dict[str, Any]:
        """
        Reset metrics counters and return previous values.
        
        Args:
            conversation_state: State object to reset metrics for
            reset_http_metrics: Whether to also reset global HTTP metrics
            
        Returns:
            Dictionary with previous metric values before reset
        """
        self.logger.info("[STATS] 🔄 Resetting agent metrics")
        
        # Capture current values
        previous_state_metrics = conversation_state.metrics.copy()
        previous_http_metrics = http_metrics.copy() if reset_http_metrics else None
        
        # Reset state metrics
        conversation_state.metrics = {
            'total_api_calls': 0,
            'retries': 0,
            'successful_ops': 0,
            'aborted_ops': 0
        }
        
        # Reset HTTP metrics if requested
        if reset_http_metrics:
            http_metrics.clear()
            http_metrics.update({
                'total_api_calls': 0,
                'retries': 0,
                'successful_ops': 0,
                'aborted_ops': 0,
            })
            
        self.logger.info("[STATS] ✅ Metrics reset completed")
        
        return {
            'previous_state_metrics': previous_state_metrics,
            'previous_http_metrics': previous_http_metrics
        }


# Global agent stats instance
agent_stats = AgentStats()
