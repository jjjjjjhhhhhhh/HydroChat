# Phase 10: Structured Logging & Metrics for HydroChat

import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, Optional, Union

from .utils import mask_nric


class HydroChatFormatter(logging.Formatter):
    """
    Structured log formatter that enforces NRIC masking and provides
    both human-readable and JSON output modes.
    """
    
    def __init__(self, format_mode: str = "human", mask_pii: bool = True):
        """
        Initialize formatter.
        
        Args:
            format_mode: "human" for bracketed taxonomy format, "json" for structured JSON
            mask_pii: Whether to automatically mask NRIC patterns in log messages
        """
        super().__init__()
        self.format_mode = format_mode.lower()
        self.mask_pii = mask_pii
        
        # NRIC pattern for automatic masking - same as validation but for detection
        self.nric_pattern = re.compile(r'\b[STFG]\d{7}[A-Z]\b')
        
    def format(self, record: logging.LogRecord) -> str:
        """Format the log record with masking and structure."""
        # Apply PII masking if enabled
        if self.mask_pii:
            record.msg = self._mask_nric_in_message(str(record.msg))
            
        # Extract structured information from the log record
        log_data = self._extract_log_data(record)
        
        if self.format_mode == "json":
            return json.dumps(log_data, default=str, separators=(',', ':'))
        else:
            return self._format_human_readable(record, log_data)
    
    def _mask_nric_in_message(self, message: str) -> str:
        """Automatically mask any NRIC patterns found in the message."""
        def mask_match(match):
            nric = match.group(0)
            return mask_nric(nric)
        
        return self.nric_pattern.sub(mask_match, message)
    
    def _extract_log_data(self, record: logging.LogRecord) -> Dict[str, Any]:
        """Extract structured data from the log record."""
        # Parse taxonomy category from message if present
        category = None
        if hasattr(record, 'msg') and isinstance(record.msg, str):
            category_match = re.match(r'^\[([A-Z_]+)\]', str(record.msg))
            if category_match:
                category = category_match.group(1)
        
        log_data = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'category': category,
            'message': str(record.msg),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        # Add any extra fields set on the record
        for key, value in record.__dict__.items():
            if key not in ['name', 'msg', 'args', 'levelname', 'levelno', 'pathname',
                          'filename', 'module', 'lineno', 'funcName', 'created',
                          'msecs', 'relativeCreated', 'thread', 'threadName',
                          'processName', 'process', 'getMessage', 'exc_info',
                          'exc_text', 'stack_info']:
                log_data[f'extra_{key}'] = value
        
        return log_data
    
    def _format_human_readable(self, record: logging.LogRecord, log_data: Dict[str, Any]) -> str:
        """Format for human-readable output (existing bracketed taxonomy style)."""
        timestamp = log_data['timestamp'].split('T')[1].split('.')[0]  # HH:MM:SS format
        level_emoji = self._get_level_emoji(record.levelno)
        
        # Basic format: timestamp level [module] message
        base_msg = f"{timestamp} {level_emoji}{record.levelname:<7} [{record.module}] {record.getMessage()}"
        
        # Add exception info if present
        if record.exc_info:
            base_msg += f"\n{self.formatException(record.exc_info)}"
            
        return base_msg
    
    def _get_level_emoji(self, level: int) -> str:
        """Get emoji for log level."""
        if level >= logging.ERROR:
            return "❌ "
        elif level >= logging.WARNING:
            return "⚠️ "
        elif level >= logging.INFO:
            return "ℹ️ "
        else:
            return "🐛 "


class MetricsLogger:
    """
    Centralized metrics tracking and reporting for HydroChat operations.
    Integrates with existing HTTP client metrics and conversation state metrics.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.metrics")
        
    def log_tool_call_start(self, tool_name: str, state_metrics: Dict[str, int]) -> None:
        """Log the start of a tool call with current metrics."""
        self.logger.info(f"[TOOL] 🔧 Starting tool call: {tool_name}")
        self.logger.debug(f"[TOOL] Current metrics: {self._format_metrics_summary(state_metrics)}")
    
    def log_tool_call_success(self, tool_name: str, state_metrics: Dict[str, int], 
                             response_size: Optional[int] = None) -> None:
        """Log successful tool completion."""
        size_info = f" (response: {response_size} bytes)" if response_size else ""
        self.logger.info(f"[TOOL] ✅ Tool completed: {tool_name}{size_info}")
        
        # Increment successful ops counter
        state_metrics['successful_ops'] += 1
        
    def log_tool_call_error(self, tool_name: str, error: Exception, 
                           state_metrics: Dict[str, int]) -> None:
        """Log tool error with metrics update."""
        self.logger.error(f"[TOOL] ❌ Tool failed: {tool_name} - {error}")
        
        # Increment aborted ops counter
        state_metrics['aborted_ops'] += 1
        
    def log_retry_attempt(self, tool_name: str, attempt: int, max_retries: int,
                         state_metrics: Dict[str, int]) -> None:
        """Log retry attempts."""
        self.logger.warning(f"[TOOL] 🔄 Retry {attempt}/{max_retries} for {tool_name}")
        
        # Increment retry counter
        state_metrics['retries'] += 1
        
    def log_metrics_summary(self, state_metrics: Dict[str, int], 
                           http_metrics: Optional[Dict[str, int]] = None) -> None:
        """Log comprehensive metrics summary."""
        summary = self._format_metrics_summary(state_metrics)
        if http_metrics:
            http_summary = self._format_metrics_summary(http_metrics, prefix="HTTP")
            summary += f", {http_summary}"
            
        self.logger.info(f"[METRICS] 📊 {summary}")
        
    def _format_metrics_summary(self, metrics: Dict[str, int], prefix: str = "") -> str:
        """Format metrics dict into readable summary."""
        prefix_str = f"{prefix} " if prefix else ""
        return f"{prefix_str}Calls: {metrics.get('total_api_calls', 0)}, " \
               f"Success: {metrics.get('successful_ops', 0)}, " \
               f"Errors: {metrics.get('aborted_ops', 0)}, " \
               f"Retries: {metrics.get('retries', 0)}"


def setup_hydrochat_logging(
    level: Union[str, int] = logging.INFO,
    format_mode: str = "human",
    mask_pii: bool = True,
    logger_name: str = "apps.hydrochat"
) -> logging.Logger:
    """
    Configure structured logging for HydroChat with proper masking.
    
    Args:
        level: Logging level (INFO, DEBUG, etc.)
        format_mode: "human" or "json" formatting
        mask_pii: Enable automatic NRIC masking
        logger_name: Root logger name to configure
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(logger_name)
    
    # Remove existing handlers to avoid duplicates
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Create and configure handler with our formatter
    handler = logging.StreamHandler()
    formatter = HydroChatFormatter(format_mode=format_mode, mask_pii=mask_pii)
    handler.setFormatter(formatter)
    
    logger.addHandler(handler)
    logger.setLevel(level)
    
    # Prevent propagation to root logger to avoid duplicate messages
    logger.propagate = False
    
    return logger


# Global metrics logger instance for use across the application
metrics_logger = MetricsLogger()
