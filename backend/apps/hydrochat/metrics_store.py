"""
Phase 17: Metrics Storage and Retention Policy
Manages metrics storage with configurable retention policies and cleanup mechanisms.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from collections import deque

logger = logging.getLogger(__name__)


class MetricsStore:
    """
    Central metrics storage with retention policy enforcement.
    Manages max entries cap and TTL-based expiration.
    """
    
    def __init__(
        self,
        max_entries: int = 1000,
        ttl_hours: int = 24,
        auto_cleanup: bool = False,
        cleanup_interval_minutes: int = 60
    ):
        """
        Initialize metrics store.
        
        Args:
            max_entries: Maximum number of entries to retain (default 1000)
            ttl_hours: Time-to-live for entries in hours (default 24)
            auto_cleanup: Whether to automatically cleanup on add (default False)
            cleanup_interval_minutes: Minimum minutes between cleanup runs
        """
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        if ttl_hours <= 0:
            raise ValueError("ttl_hours must be positive")
        
        self.max_entries = max_entries
        self.ttl_hours = ttl_hours
        self.auto_cleanup = auto_cleanup
        self.cleanup_interval_minutes = cleanup_interval_minutes
        
        # Use deque for automatic size limiting
        self.entries: deque = deque(maxlen=max_entries)
        self.last_cleanup_time: Optional[datetime] = None
        
        logger.info(
            f"[METRICS] 📊 Initialized MetricsStore (max_entries={max_entries}, "
            f"ttl_hours={ttl_hours})"
        )
    
    def add_entry(self, entry: Dict[str, Any]):
        """
        Add a metric entry to the store.
        
        Args:
            entry: Dictionary containing metric data (must have 'timestamp' field)
        """
        if 'timestamp' not in entry:
            entry['timestamp'] = datetime.now()
        
        self.entries.append(entry)
        
        # Auto-cleanup if enabled and interval passed
        if self.auto_cleanup:
            self._maybe_auto_cleanup()
    
    def get_entries_since(self, cutoff: datetime) -> List[Dict[str, Any]]:
        """
        Get all entries since a specific timestamp.
        
        Args:
            cutoff: Cutoff timestamp
            
        Returns:
            List of entries after cutoff
        """
        return [
            entry for entry in self.entries
            if entry['timestamp'] >= cutoff
        ]
    
    def get_expired_entries(self) -> List[Dict[str, Any]]:
        """
        Get all expired entries based on TTL.
        
        Returns:
            List of expired entries
        """
        cutoff_time = datetime.now() - timedelta(hours=self.ttl_hours)
        
        return [
            entry for entry in self.entries
            if entry['timestamp'] <= cutoff_time
        ]
    
    def cleanup_expired(self) -> int:
        """
        Remove all expired entries based on TTL.
        
        Returns:
            Number of entries removed
        """
        cutoff_time = datetime.now() - timedelta(hours=self.ttl_hours)
        
        original_count = len(self.entries)
        
        # Filter out expired entries
        valid_entries = [
            entry for entry in self.entries
            if entry['timestamp'] > cutoff_time
        ]
        
        # Replace deque with cleaned entries
        self.entries = deque(valid_entries, maxlen=self.max_entries)
        
        removed_count = original_count - len(self.entries)
        
        if removed_count > 0:
            logger.info(
                f"[METRICS] 🧹 Cleaned up {removed_count} expired metrics entries "
                f"(TTL: {self.ttl_hours}h)"
            )
        
        self.last_cleanup_time = datetime.now()
        
        return removed_count
    
    def _maybe_auto_cleanup(self):
        """Conditionally run cleanup if interval has passed."""
        if self.last_cleanup_time is None:
            self.cleanup_expired()
            return
        
        elapsed = datetime.now() - self.last_cleanup_time
        elapsed_minutes = elapsed.total_seconds() / 60
        
        if elapsed_minutes >= self.cleanup_interval_minutes:
            self.cleanup_expired()
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about the metrics store.
        
        Returns:
            Dictionary with store statistics
        """
        if not self.entries:
            return {
                'total_entries': 0,
                'max_entries': self.max_entries,
                'ttl_hours': self.ttl_hours,
                'expired_count': 0,
                'oldest_entry_age_hours': 0,
                'storage_utilization_percent': 0.0,
                'last_cleanup': None
            }
        
        now = datetime.now()
        expired = self.get_expired_entries()
        oldest_entry = min(self.entries, key=lambda e: e['timestamp'])
        oldest_age = (now - oldest_entry['timestamp']).total_seconds() / 3600  # hours
        
        utilization = (len(self.entries) / self.max_entries) * 100
        
        stats = {
            'total_entries': len(self.entries),
            'max_entries': self.max_entries,
            'ttl_hours': self.ttl_hours,
            'expired_count': len(expired),
            'oldest_entry_age_hours': oldest_age,
            'storage_utilization_percent': utilization,
            'last_cleanup': self.last_cleanup_time.isoformat() if self.last_cleanup_time else None
        }
        
        # Add warning if storage highly utilized
        if utilization >= 80:
            stats['warning'] = f"Storage utilization at {utilization:.1f}% - consider cleanup or increasing max_entries"
        
        return stats
    
    def export_to_json(self) -> Dict[str, Any]:
        """
        Export metrics and statistics to JSON-serializable format.
        
        Returns:
            Dictionary ready for JSON export
        """
        # Convert datetime objects to ISO format strings
        serialized_entries = []
        for entry in self.entries:
            serialized_entry = entry.copy()
            if isinstance(serialized_entry.get('timestamp'), datetime):
                serialized_entry['timestamp'] = serialized_entry['timestamp'].isoformat()
            serialized_entries.append(serialized_entry)
        
        return {
            'entries': serialized_entries,
            'statistics': self.get_statistics()
        }
    
    def reset(self):
        """Reset the metrics store."""
        self.entries.clear()
        self.last_cleanup_time = None
        logger.info("[METRICS] 🔄 Metrics store reset")


# Global metrics store instance
_global_metrics_store: Optional[MetricsStore] = None


def get_global_metrics_store() -> MetricsStore:
    """
    Get or create the global metrics store singleton.
    
    Returns:
        Global MetricsStore instance
    """
    global _global_metrics_store
    
    if _global_metrics_store is None:
        # Try to get settings from Django config
        try:
            from django.conf import settings
            max_entries = getattr(settings, 'METRICS_MAX_ENTRIES', 1000)
            ttl_hours = getattr(settings, 'METRICS_TTL_HOURS', 24)
        except:
            max_entries = 1000
            ttl_hours = 24
        
        _global_metrics_store = MetricsStore(
            max_entries=max_entries,
            ttl_hours=ttl_hours
        )
    
    return _global_metrics_store


def reset_global_metrics_store():
    """Reset the global metrics store singleton."""
    global _global_metrics_store
    _global_metrics_store = None


__all__ = [
    'MetricsStore',
    'get_global_metrics_store',
    'reset_global_metrics_store'
]


