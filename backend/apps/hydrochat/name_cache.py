# HydroChat Name Resolution Cache
# Provides efficient patient name-to-ID resolution with cache management and ambiguity handling
# Implements 5-minute cache refresh policy with automatic invalidation on CRUD operations

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from .http_client import HttpClient
from .tools import ToolResponse
from .utils import mask_nric

logger = logging.getLogger(__name__)


@dataclass
class PatientCacheEntry:
    """Cache entry for a single patient record."""
    patient_id: int
    full_name: str  # "First Last" format
    first_name: str
    last_name: str
    nric: str
    contact_no: Optional[str] = None
    date_of_birth: Optional[str] = None


@dataclass
class CacheMetadata:
    """Metadata for cache management."""
    last_refresh: datetime
    entry_count: int
    refresh_count: int
    invalidation_count: int


class NameResolutionCache:
    """
    Patient name resolution cache with automatic refresh and invalidation.
    
    Features:
    - 5-minute cache refresh policy
    - Case-insensitive exact full-name matching
    - Ambiguity detection for multiple matches
    - Automatic cache invalidation on CRUD operations
    - NRIC masking for privacy protection
    """
    
    def __init__(self, http_client: HttpClient, cache_ttl_minutes: int = 5):
        self.http_client = http_client
        self.cache_ttl = timedelta(minutes=cache_ttl_minutes)
        
        # Cache storage
        self._cache: Dict[int, PatientCacheEntry] = {}  # patient_id -> entry
        self._name_index: Dict[str, List[int]] = {}  # lowercase_full_name -> [patient_ids]
        
        # Cache metadata
        self._metadata = CacheMetadata(
            last_refresh=datetime.min,  # Force initial refresh
            entry_count=0,
            refresh_count=0,
            invalidation_count=0
        )
        
        logger.info("[NameCache] 🗃️ Name resolution cache initialized")

    def _is_cache_stale(self) -> bool:
        """Check if cache needs refresh based on TTL."""
        age = datetime.now() - self._metadata.last_refresh
        return age > self.cache_ttl

    def _refresh_cache(self) -> bool:
        """
        Refresh cache from backend API.
        
        Returns:
            bool: True if refresh successful, False otherwise
        """
        try:
            logger.info("[NameCache] 🔄 Refreshing patient cache")
            
            # Fetch all patients from API
            response = self.http_client.request('GET', '/api/patients/')
            
            if response.status_code != 200:
                logger.error(f"[NameCache] ❌ Failed to refresh cache: HTTP {response.status_code}")
                return False
            
            patients_data = response.json()
            
            # Clear existing cache
            self._cache.clear()
            self._name_index.clear()
            
            # Populate cache with new data
            for patient in patients_data:
                entry = PatientCacheEntry(
                    patient_id=patient['id'],
                    full_name=f"{patient['first_name']} {patient['last_name']}",
                    first_name=patient['first_name'],
                    last_name=patient['last_name'],
                    nric=patient['nric'],
                    contact_no=patient.get('contact_no'),
                    date_of_birth=patient.get('date_of_birth')
                )
                
                # Store in main cache
                self._cache[patient['id']] = entry
                
                # Build name index (case-insensitive)
                full_name_key = entry.full_name.lower().strip()
                if full_name_key not in self._name_index:
                    self._name_index[full_name_key] = []
                self._name_index[full_name_key].append(patient['id'])
                
                # Log with masked NRIC
                logger.debug(f"[NameCache] Cached: {entry.full_name} (ID: {patient['id']}, NRIC: {mask_nric(entry.nric)})")
            
            # Update metadata
            self._metadata.last_refresh = datetime.now()
            self._metadata.entry_count = len(self._cache)
            self._metadata.refresh_count += 1
            
            logger.info(f"[NameCache] ✅ Cache refreshed: {len(self._cache)} patients loaded")
            return True
            
        except Exception as e:
            logger.error(f"[NameCache] ❌ Cache refresh failed: {e}")
            return False

    def _ensure_cache_fresh(self) -> bool:
        """
        Ensure cache is fresh, refresh if needed.
        
        Returns:
            bool: True if cache is available and fresh, False otherwise
        """
        if self._is_cache_stale():
            return self._refresh_cache()
        return True

    def resolve_name_to_id(self, full_name: str) -> Tuple[Optional[int], List[PatientCacheEntry], bool]:
        """
        Resolve full name to patient ID with ambiguity handling.
        
        Args:
            full_name: Full name to resolve (case-insensitive)
            
        Returns:
            Tuple of:
            - patient_id: Single patient ID if unique match, None otherwise
            - matches: List of all matching PatientCacheEntry objects
            - cache_refreshed: Whether cache was refreshed during this call
        """
        cache_was_stale = self._is_cache_stale()
        
        # Ensure cache is fresh
        if not self._ensure_cache_fresh():
            logger.warning("[NameCache] ⚠️ Cache unavailable, cannot resolve name")
            return None, [], False
        
        # Cache was refreshed if it was stale and now we have data
        cache_refreshed = cache_was_stale and len(self._cache) > 0
        
        # Normalize input name
        search_name = full_name.lower().strip()
        
        if not search_name:
            logger.warning("[NameCache] ⚠️ Empty name provided for resolution")
            return None, [], cache_refreshed
        
        # Look up in name index
        matching_ids = self._name_index.get(search_name, [])
        
        if not matching_ids:
            logger.info(f"[NameCache] 🔍 No matches found for: '{full_name}'")
            return None, [], cache_refreshed
        
        # Get full patient entries for matches
        matches = [self._cache[patient_id] for patient_id in matching_ids if patient_id in self._cache]
        
        if len(matches) == 1:
            # Unique match found
            match = matches[0]
            logger.info(f"[NameCache] ✅ Unique match found: '{full_name}' -> ID {match.patient_id} (NRIC: {mask_nric(match.nric)})")
            return match.patient_id, matches, cache_refreshed
        else:
            # Multiple matches found
            masked_matches = [f"ID {m.patient_id} (NRIC: {mask_nric(m.nric)})" for m in matches]
            logger.info(f"[NameCache] ⚠️ Multiple matches found for '{full_name}': {masked_matches}")
            return None, matches, cache_refreshed

    def get_patient_by_id(self, patient_id: int) -> Optional[PatientCacheEntry]:
        """
        Get patient entry by ID from cache.
        
        Args:
            patient_id: Patient ID to look up
            
        Returns:
            PatientCacheEntry if found, None otherwise
        """
        # Ensure cache is fresh
        if not self._ensure_cache_fresh():
            logger.warning("[NameCache] ⚠️ Cache unavailable, cannot get patient")
            return None
        
        entry = self._cache.get(patient_id)
        if entry:
            logger.debug(f"[NameCache] Found patient ID {patient_id}: {entry.full_name} (NRIC: {mask_nric(entry.nric)})")
        else:
            logger.info(f"[NameCache] 🔍 Patient ID {patient_id} not found in cache")
        
        return entry

    def invalidate_cache(self, reason: str = "Manual invalidation") -> None:
        """
        Invalidate cache to force refresh on next access.
        
        Args:
            reason: Reason for invalidation (for logging)
        """
        logger.info(f"[NameCache] 🗑️ Cache invalidated: {reason}")
        self._metadata.last_refresh = datetime.min  # Force refresh
        self._metadata.invalidation_count += 1

    def invalidate_on_crud_success(self, operation: str, patient_id: Optional[int] = None) -> None:
        """
        Invalidate cache after successful CRUD operations.
        
        Args:
            operation: CRUD operation performed (create, update, delete)
            patient_id: Patient ID affected (for logging)
        """
        patient_info = f" (ID: {patient_id})" if patient_id else ""
        reason = f"Patient {operation} operation{patient_info}"
        self.invalidate_cache(reason)

    def get_cache_stats(self) -> Dict:
        """
        Get cache statistics and metadata.
        
        Returns:
            Dictionary with cache statistics
        """
        cache_age = datetime.now() - self._metadata.last_refresh if self._metadata.last_refresh != datetime.min else None
        
        stats = {
            'entry_count': self._metadata.entry_count,
            'refresh_count': self._metadata.refresh_count,
            'invalidation_count': self._metadata.invalidation_count,
            'last_refresh': self._metadata.last_refresh.isoformat() if self._metadata.last_refresh != datetime.min else None,
            'cache_age_seconds': cache_age.total_seconds() if cache_age else None,
            'is_stale': self._is_cache_stale(),
            'cache_ttl_seconds': self.cache_ttl.total_seconds(),
            'name_index_size': len(self._name_index)
        }
        
        logger.debug(f"[NameCache] 📊 Cache stats: {stats}")
        return stats

    def list_all_cached_patients(self) -> List[PatientCacheEntry]:
        """
        Get all cached patient entries.
        
        Returns:
            List of all PatientCacheEntry objects
        """
        # Ensure cache is fresh
        if not self._ensure_cache_fresh():
            logger.warning("[NameCache] ⚠️ Cache unavailable, returning empty list")
            return []
        
        entries = list(self._cache.values())
        logger.debug(f"[NameCache] 📋 Retrieved {len(entries)} cached patients")
        return entries

    def build_ambiguity_list(self, matches: List[PatientCacheEntry]) -> List[str]:
        """
        Build user-friendly ambiguity list with masked NRICs.
        
        Args:
            matches: List of matching PatientCacheEntry objects
            
        Returns:
            List of formatted strings for user presentation
        """
        if not matches:
            return []
        
        ambiguity_list = []
        for entry in matches:
            # Format: "ID 1: John Doe (NRIC: S****567A, DOB: 1990-01-01)"
            display_parts = [f"ID {entry.patient_id}: {entry.full_name}"]
            display_parts.append(f"NRIC: {mask_nric(entry.nric)}")
            
            if entry.date_of_birth:
                display_parts.append(f"DOB: {entry.date_of_birth}")
            
            if entry.contact_no:
                display_parts.append(f"Contact: {entry.contact_no}")
            
            formatted = f"{display_parts[0]} ({', '.join(display_parts[1:])})"
            ambiguity_list.append(formatted)
        
        logger.debug(f"[NameCache] 📝 Built ambiguity list with {len(ambiguity_list)} entries")
        return ambiguity_list


# Convenience functions for integration

def create_name_cache(http_client: HttpClient) -> NameResolutionCache:
    """Create a name resolution cache instance."""
    return NameResolutionCache(http_client)


def resolve_patient_name(cache: NameResolutionCache, full_name: str) -> Tuple[Optional[int], List[str], bool]:
    """
    Convenience function for name resolution with ambiguity handling.
    
    Args:
        cache: NameResolutionCache instance
        full_name: Full name to resolve
        
    Returns:
        Tuple of:
        - patient_id: Single patient ID if unique match, None otherwise
        - ambiguity_list: Formatted strings for ambiguous matches
        - cache_refreshed: Whether cache was refreshed
    """
    patient_id, matches, cache_refreshed = cache.resolve_name_to_id(full_name)
    
    if patient_id is None and matches:
        # Build ambiguity list for multiple matches
        ambiguity_list = cache.build_ambiguity_list(matches)
        return None, ambiguity_list, cache_refreshed
    else:
        # Single match or no matches
        return patient_id, [], cache_refreshed
