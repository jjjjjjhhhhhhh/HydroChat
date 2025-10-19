"""
Phase 17: Performance Tracking and Response Time Monitoring
Provides decorators and utilities for tracking conversation response times and performance metrics.
"""

import time
import asyncio
import logging
from functools import wraps
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable
from collections import deque

logger = logging.getLogger(__name__)


class PerformanceMetrics:
    """
    Tracks performance metrics with retention policy.
    Enforces max entries and TTL-based expiration.
    """
    
    def __init__(self, max_entries: int = 1000, ttl_hours: int = 24):
        """
        Initialize performance metrics tracker.
        
        Args:
            max_entries: Maximum number of entries to retain
            ttl_hours: Time-to-live for entries in hours
        """
        if max_entries <= 0:
            raise ValueError(f"max_entries must be positive, got: {max_entries}")
        if ttl_hours <= 0:
            raise ValueError(f"ttl_hours must be positive, got: {ttl_hours}")
        
        self.max_entries = max_entries
        self.ttl_hours = ttl_hours
        self.response_times: deque = deque(maxlen=max_entries)
        self.last_cleanup_time: Optional[datetime] = None
    
    def add_response_time(
        self,
        operation: str,
        duration: float,
        timestamp: datetime,
        exceeded_threshold: bool,
        error: Optional[str] = None
    ):
        """
        Add a response time entry.
        
        Args:
            operation: Name of the operation
            duration: Duration in seconds
            timestamp: Timestamp of the operation
            exceeded_threshold: Whether duration exceeded threshold
            error: Optional error message if operation failed
        """
        entry = {
            'operation': operation,
            'duration': duration,
            'timestamp': timestamp,
            'exceeded_threshold': exceeded_threshold
        }
        
        if error:
            entry['error'] = error
        
        self.response_times.append(entry)
        
        # Deque with maxlen automatically handles max_entries enforcement
    
    def cleanup_expired(self) -> int:
        """
        Remove entries older than TTL.
        
        Returns:
            Number of entries removed
        """
        cutoff_time = datetime.now() - timedelta(hours=self.ttl_hours)
        
        # Filter out expired entries
        original_count = len(self.response_times)
        
        # Convert deque to list, filter, and create new deque
        valid_entries = [
            entry for entry in self.response_times
            if entry['timestamp'] > cutoff_time
        ]
        
        self.response_times = deque(valid_entries, maxlen=self.max_entries)
        
        removed_count = original_count - len(self.response_times)
        
        if removed_count > 0:
            logger.info(f"[METRICS] 🧹 Cleaned up {removed_count} expired performance entries")
        
        self.last_cleanup_time = datetime.now()
        
        return removed_count
    
    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary statistics of performance metrics.
        
        Returns:
            Dictionary with summary statistics
        """
        if not self.response_times:
            return {
                'total_operations': 0,
                'threshold_violations': 0,
                'violation_rate': 0.0,
                'avg_response_time': 0.0,
                'max_response_time': 0.0,
                'min_response_time': 0.0
            }
        
        durations = [entry['duration'] for entry in self.response_times]
        violations = sum(1 for entry in self.response_times if entry['exceeded_threshold'])
        
        return {
            'total_operations': len(self.response_times),
            'threshold_violations': violations,
            'violation_rate': violations / len(self.response_times),
            'avg_response_time': sum(durations) / len(durations),
            'max_response_time': max(durations),
            'min_response_time': min(durations)
        }
    
    def reset(self):
        """Reset all performance metrics."""
        self.response_times.clear()
        self.last_cleanup_time = None


# Global performance metrics instance
_global_performance_metrics = PerformanceMetrics(max_entries=1000, ttl_hours=24)


def get_performance_metrics() -> PerformanceMetrics:
    """Get the global performance metrics instance."""
    return _global_performance_metrics


def reset_performance_metrics():
    """Reset the global performance metrics."""
    global _global_performance_metrics
    _global_performance_metrics = PerformanceMetrics(max_entries=1000, ttl_hours=24)


def track_response_time(operation_name: str, threshold_seconds: float = 2.0) -> Callable:
    """
    Decorator to track response time of operations.
    Logs warning if response time exceeds threshold.
    Supports both synchronous and asynchronous functions.
    
    Args:
        operation_name: Name of the operation being tracked
        threshold_seconds: Threshold in seconds (default 2.0 per §2)
    
    Returns:
        Decorator function
    
    Example (sync):
        @track_response_time("conversation_turn")
        def process_conversation(state):
            # ... process conversation ...
            return result
    
    Example (async):
        @track_response_time("async_processing")
        async def process_message(message):
            # ... async process message ...
            return result
    """
    def decorator(func: Callable) -> Callable:
        # Detect if function is async (coroutine)
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                start_time = time.time()
                error_message = None
                
                try:
                    result = await func(*args, **kwargs)
                    return result
                except Exception as e:
                    error_message = f"{type(e).__name__}: {str(e)}"
                    raise
                finally:
                    elapsed = time.time() - start_time
                    exceeded_threshold = elapsed > threshold_seconds
                    
                    # Log performance
                    if exceeded_threshold:
                        logger.warning(
                            f"⚠️ [PERFORMANCE] Response time {elapsed:.2f}s exceeds {threshold_seconds}s "
                            f"threshold for operation: {operation_name}"
                        )
                    else:
                        logger.debug(
                            f"[PERFORMANCE] Operation {operation_name} completed in {elapsed:.2f}s"
                        )
                    
                    # Record metrics
                    _global_performance_metrics.add_response_time(
                        operation=operation_name,
                        duration=elapsed,
                        timestamp=datetime.now(),
                        exceeded_threshold=exceeded_threshold,
                        error=error_message
                    )
            
            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                start_time = time.time()
                error_message = None
                
                try:
                    result = func(*args, **kwargs)
                    return result
                except Exception as e:
                    error_message = f"{type(e).__name__}: {str(e)}"
                    raise
                finally:
                    elapsed = time.time() - start_time
                    exceeded_threshold = elapsed > threshold_seconds
                    
                    # Log performance
                    if exceeded_threshold:
                        logger.warning(
                            f"⚠️ [PERFORMANCE] Response time {elapsed:.2f}s exceeds {threshold_seconds}s "
                            f"threshold for operation: {operation_name}"
                        )
                    else:
                        logger.debug(
                            f"[PERFORMANCE] Operation {operation_name} completed in {elapsed:.2f}s"
                        )
                    
                    # Record metrics
                    _global_performance_metrics.add_response_time(
                        operation=operation_name,
                        duration=elapsed,
                        timestamp=datetime.now(),
                        exceeded_threshold=exceeded_threshold,
                        error=error_message
                    )
            
            return sync_wrapper
    return decorator


def get_performance_summary() -> Dict[str, Any]:
    """
    Get comprehensive performance summary including response times and violations.
    
    Returns:
        Dictionary with performance statistics
    """
    metrics = get_performance_metrics()
    summary = metrics.get_summary()
    
    # Add additional context
    summary.update({
        'metrics_count': len(metrics.response_times),
        'max_entries': metrics.max_entries,
        'ttl_hours': metrics.ttl_hours,
        'last_cleanup': metrics.last_cleanup_time.isoformat() if metrics.last_cleanup_time else None
    })
    
    return summary


def cleanup_expired_metrics() -> int:
    """
    Manually trigger cleanup of expired metrics.
    Can be called from scheduled tasks.
    
    Returns:
        Number of entries removed
    """
    metrics = get_performance_metrics()
    return metrics.cleanup_expired()


__all__ = [
    'PerformanceMetrics',
    'track_response_time',
    'get_performance_metrics',
    'reset_performance_metrics',
    'get_performance_summary',
    'cleanup_expired_metrics'
]


