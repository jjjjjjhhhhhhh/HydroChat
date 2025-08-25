# Test suite for HydroChat name resolution cache
# Tests cache refresh, name resolution, ambiguity handling, and invalidation

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
import pytest

from apps.hydrochat.name_cache import (
    NameResolutionCache, PatientCacheEntry, CacheMetadata,
    create_name_cache, resolve_patient_name
)
from apps.hydrochat.http_client import HttpClient


class TestPatientCacheEntry:
    """Test PatientCacheEntry dataclass."""
    
    def test_cache_entry_creation(self):
        """Test creating a cache entry with all fields."""
        entry = PatientCacheEntry(
            patient_id=1,
            full_name="John Doe",
            first_name="John",
            last_name="Doe",
            nric="S1234567A",
            contact_no="+6512345678",
            date_of_birth="1990-01-01"
        )
        
        assert entry.patient_id == 1
        assert entry.full_name == "John Doe"
        assert entry.first_name == "John"
        assert entry.last_name == "Doe"
        assert entry.nric == "S1234567A"
        assert entry.contact_no == "+6512345678"
        assert entry.date_of_birth == "1990-01-01"

    def test_cache_entry_optional_fields(self):
        """Test creating a cache entry with minimal fields."""
        entry = PatientCacheEntry(
            patient_id=1,
            full_name="John Doe",
            first_name="John",
            last_name="Doe",
            nric="S1234567A"
        )
        
        assert entry.patient_id == 1
        assert entry.full_name == "John Doe"
        assert entry.contact_no is None
        assert entry.date_of_birth is None


class TestCacheMetadata:
    """Test CacheMetadata dataclass."""
    
    def test_metadata_creation(self):
        """Test creating cache metadata."""
        now = datetime.now()
        metadata = CacheMetadata(
            last_refresh=now,
            entry_count=5,
            refresh_count=1,
            invalidation_count=0
        )
        
        assert metadata.last_refresh == now
        assert metadata.entry_count == 5
        assert metadata.refresh_count == 1
        assert metadata.invalidation_count == 0


class TestNameResolutionCache:
    """Test name resolution cache functionality."""
    
    @pytest.fixture
    def mock_http_client(self):
        """Mock HTTP client for testing."""
        return MagicMock(spec=HttpClient)
    
    @pytest.fixture
    def cache(self, mock_http_client):
        """Name resolution cache instance with mocked HTTP client."""
        return NameResolutionCache(mock_http_client, cache_ttl_minutes=5)

    @pytest.fixture
    def sample_patients_data(self):
        """Sample patient data for testing."""
        return [
            {
                'id': 1,
                'first_name': 'John',
                'last_name': 'Doe',
                'nric': 'S1234567A',
                'contact_no': '+6512345678',
                'date_of_birth': '1990-01-01'
            },
            {
                'id': 2,
                'first_name': 'Jane',
                'last_name': 'Smith',
                'nric': 'S2345678B',
                'contact_no': '+6587654321',
                'date_of_birth': '1985-05-15'
            },
            {
                'id': 3,
                'first_name': 'John',
                'last_name': 'Smith',  # Same first name as patient 1, different last name
                'nric': 'S3456789C',
                'contact_no': None,
                'date_of_birth': None
            }
        ]

    def test_cache_initialization(self, cache, mock_http_client):
        """Test cache initialization with proper defaults."""
        assert cache.http_client == mock_http_client
        assert cache.cache_ttl == timedelta(minutes=5)
        assert len(cache._cache) == 0
        assert len(cache._name_index) == 0
        assert cache._metadata.refresh_count == 0
        assert cache._metadata.invalidation_count == 0
        assert cache._metadata.entry_count == 0

    def test_cache_is_stale_initially(self, cache):
        """Test that cache is stale on initialization."""
        assert cache._is_cache_stale() is True

    def test_cache_refresh_success(self, cache, mock_http_client, sample_patients_data):
        """Test successful cache refresh from API."""
        # Mock successful API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_patients_data
        mock_http_client.request.return_value = mock_response
        
        # Refresh cache
        result = cache._refresh_cache()
        
        # Verify refresh was successful
        assert result is True
        assert len(cache._cache) == 3
        assert len(cache._name_index) == 3
        assert cache._metadata.entry_count == 3
        assert cache._metadata.refresh_count == 1
        
        # Verify cache contents
        assert 1 in cache._cache
        assert 2 in cache._cache
        assert 3 in cache._cache
        
        # Verify name index (case-insensitive)
        assert 'john doe' in cache._name_index
        assert 'jane smith' in cache._name_index
        assert 'john smith' in cache._name_index
        
        # Verify API was called correctly
        mock_http_client.request.assert_called_once_with('GET', '/api/patients/')

    def test_cache_refresh_api_error(self, cache, mock_http_client):
        """Test cache refresh with API error."""
        # Mock API error response
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_http_client.request.return_value = mock_response
        
        # Refresh cache
        result = cache._refresh_cache()
        
        # Verify refresh failed
        assert result is False
        assert len(cache._cache) == 0
        assert cache._metadata.refresh_count == 0

    def test_cache_refresh_network_error(self, cache, mock_http_client):
        """Test cache refresh with network error."""
        # Mock network error
        mock_http_client.request.side_effect = Exception("Network error")
        
        # Refresh cache
        result = cache._refresh_cache()
        
        # Verify refresh failed
        assert result is False
        assert len(cache._cache) == 0
        assert cache._metadata.refresh_count == 0

    def test_resolve_name_unique_match(self, cache, mock_http_client, sample_patients_data):
        """Test name resolution with unique match."""
        # Setup cache with data
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_patients_data
        mock_http_client.request.return_value = mock_response
        
        # Resolve unique name
        patient_id, matches, cache_refreshed = cache.resolve_name_to_id("Jane Smith")
        
        # Verify unique match
        assert patient_id == 2
        assert len(matches) == 1
        assert matches[0].patient_id == 2
        assert matches[0].full_name == "Jane Smith"
        assert cache_refreshed is True  # First refresh

    def test_resolve_name_case_insensitive(self, cache, mock_http_client, sample_patients_data):
        """Test case-insensitive name resolution."""
        # Setup cache with data
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_patients_data
        mock_http_client.request.return_value = mock_response
        
        # Resolve with different cases
        test_cases = ["jane smith", "JANE SMITH", "Jane Smith", " jane smith "]
        
        for test_name in test_cases:
            patient_id, matches, _ = cache.resolve_name_to_id(test_name)
            assert patient_id == 2
            assert len(matches) == 1
            assert matches[0].patient_id == 2

    def test_resolve_name_no_match(self, cache, mock_http_client, sample_patients_data):
        """Test name resolution with no matches."""
        # Setup cache with data
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_patients_data
        mock_http_client.request.return_value = mock_response
        
        # Resolve non-existent name
        patient_id, matches, cache_refreshed = cache.resolve_name_to_id("Bob Wilson")
        
        # Verify no match
        assert patient_id is None
        assert len(matches) == 0
        assert cache_refreshed is True  # Cache was refreshed with data

    def test_resolve_name_multiple_matches(self, cache, mock_http_client):
        """Test name resolution with multiple matches (duplicate names)."""
        # Sample data with duplicate names
        duplicate_name_data = [
            {
                'id': 1,
                'first_name': 'John',
                'last_name': 'Doe',
                'nric': 'S1234567A',
                'contact_no': '+6512345678',
                'date_of_birth': '1990-01-01'
            },
            {
                'id': 2,
                'first_name': 'John',
                'last_name': 'Doe',  # Same name as patient 1
                'nric': 'S2345678B',
                'contact_no': '+6587654321',
                'date_of_birth': '1985-05-15'
            }
        ]
        
        # Setup cache with duplicate name data
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = duplicate_name_data
        mock_http_client.request.return_value = mock_response
        
        # Resolve duplicate name
        patient_id, matches, cache_refreshed = cache.resolve_name_to_id("John Doe")
        
        # Verify multiple matches
        assert patient_id is None  # No unique match
        assert len(matches) == 2
        assert matches[0].patient_id in [1, 2]
        assert matches[1].patient_id in [1, 2]
        assert matches[0].patient_id != matches[1].patient_id
        assert cache_refreshed is True

    def test_resolve_name_empty_input(self, cache, mock_http_client, sample_patients_data):
        """Test name resolution with empty input."""
        # Setup cache with data
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_patients_data
        mock_http_client.request.return_value = mock_response
        
        # Test empty inputs
        empty_inputs = ["", "  ", "\t", "\n"]
        
        for empty_input in empty_inputs:
            patient_id, matches, _ = cache.resolve_name_to_id(empty_input)
            assert patient_id is None
            assert len(matches) == 0

    def test_get_patient_by_id_success(self, cache, mock_http_client, sample_patients_data):
        """Test getting patient by ID from cache."""
        # Setup cache with data
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_patients_data
        mock_http_client.request.return_value = mock_response
        
        # Get patient by ID
        entry = cache.get_patient_by_id(2)
        
        # Verify entry
        assert entry is not None
        assert entry.patient_id == 2
        assert entry.full_name == "Jane Smith"
        assert entry.nric == "S2345678B"

    def test_get_patient_by_id_not_found(self, cache, mock_http_client, sample_patients_data):
        """Test getting non-existent patient by ID."""
        # Setup cache with data
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_patients_data
        mock_http_client.request.return_value = mock_response
        
        # Get non-existent patient
        entry = cache.get_patient_by_id(999)
        
        # Verify not found
        assert entry is None

    def test_cache_invalidation(self, cache, mock_http_client, sample_patients_data):
        """Test manual cache invalidation."""
        # Setup cache with data
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_patients_data
        mock_http_client.request.return_value = mock_response
        
        # Load cache initially
        cache._refresh_cache()
        assert cache._metadata.invalidation_count == 0
        assert not cache._is_cache_stale()
        
        # Invalidate cache
        cache.invalidate_cache("Test invalidation")
        
        # Verify invalidation
        assert cache._metadata.invalidation_count == 1
        assert cache._is_cache_stale() is True

    def test_invalidate_on_crud_success(self, cache):
        """Test cache invalidation after CRUD operations."""
        initial_count = cache._metadata.invalidation_count
        
        # Test different CRUD operations
        cache.invalidate_on_crud_success("create", 1)
        assert cache._metadata.invalidation_count == initial_count + 1
        
        cache.invalidate_on_crud_success("update", 2)
        assert cache._metadata.invalidation_count == initial_count + 2
        
        cache.invalidate_on_crud_success("delete", 3)
        assert cache._metadata.invalidation_count == initial_count + 3
        
        # Test without patient ID
        cache.invalidate_on_crud_success("create")
        assert cache._metadata.invalidation_count == initial_count + 4

    def test_cache_ttl_behavior(self, mock_http_client):
        """Test cache TTL behavior with different timeouts."""
        # Create cache with short TTL
        cache = NameResolutionCache(mock_http_client, cache_ttl_minutes=1)
        
        # Initially stale
        assert cache._is_cache_stale() is True
        
        # Mock successful refresh
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_http_client.request.return_value = mock_response
        
        # Refresh cache
        cache._refresh_cache()
        assert cache._is_cache_stale() is False
        
        # Manually set cache to be older than TTL
        old_time = datetime.now() - timedelta(minutes=2)
        cache._metadata.last_refresh = old_time
        
        # Should be stale now
        assert cache._is_cache_stale() is True

    def test_get_cache_stats(self, cache, mock_http_client, sample_patients_data):
        """Test cache statistics reporting."""
        # Get initial stats
        initial_stats = cache.get_cache_stats()
        assert initial_stats['entry_count'] == 0
        assert initial_stats['refresh_count'] == 0
        assert initial_stats['invalidation_count'] == 0
        assert initial_stats['last_refresh'] is None
        assert initial_stats['is_stale'] is True
        
        # Setup and refresh cache
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_patients_data
        mock_http_client.request.return_value = mock_response
        
        cache._refresh_cache()
        
        # Get updated stats
        updated_stats = cache.get_cache_stats()
        assert updated_stats['entry_count'] == 3
        assert updated_stats['refresh_count'] == 1
        assert updated_stats['last_refresh'] is not None
        assert updated_stats['is_stale'] is False
        assert updated_stats['name_index_size'] == 3

    def test_list_all_cached_patients(self, cache, mock_http_client, sample_patients_data):
        """Test listing all cached patients."""
        # Setup cache with data
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_patients_data
        mock_http_client.request.return_value = mock_response
        
        # Get all patients
        patients = cache.list_all_cached_patients()
        
        # Verify all patients returned
        assert len(patients) == 3
        patient_ids = {p.patient_id for p in patients}
        assert patient_ids == {1, 2, 3}

    def test_build_ambiguity_list(self, cache):
        """Test building ambiguity list for multiple matches."""
        # Create sample matching entries
        matches = [
            PatientCacheEntry(
                patient_id=1,
                full_name="John Doe",
                first_name="John",
                last_name="Doe",
                nric="S1234567A",
                contact_no="+6512345678",
                date_of_birth="1990-01-01"
            ),
            PatientCacheEntry(
                patient_id=2,
                full_name="John Doe",
                first_name="John",
                last_name="Doe",
                nric="S2345678B",
                contact_no=None,
                date_of_birth=None
            )
        ]
        
        # Build ambiguity list
        ambiguity_list = cache.build_ambiguity_list(matches)
        
        # Verify formatting
        assert len(ambiguity_list) == 2
        
        # Check first entry (with all fields)
        assert "ID 1: John Doe" in ambiguity_list[0]
        assert "NRIC: S******7A" in ambiguity_list[0]  # Corrected masking format
        assert "DOB: 1990-01-01" in ambiguity_list[0]
        assert "Contact: +6512345678" in ambiguity_list[0]
        
        # Check second entry (minimal fields)
        assert "ID 2: John Doe" in ambiguity_list[1]
        assert "NRIC: S******8B" in ambiguity_list[1]  # Corrected masking format
        assert "DOB:" not in ambiguity_list[1]
        assert "Contact:" not in ambiguity_list[1]

    def test_build_ambiguity_list_empty(self, cache):
        """Test building ambiguity list with empty matches."""
        ambiguity_list = cache.build_ambiguity_list([])
        assert ambiguity_list == []


class TestConvenienceFunctions:
    """Test convenience functions for integration."""
    
    @pytest.fixture
    def mock_http_client(self):
        """Mock HTTP client for testing."""
        return MagicMock(spec=HttpClient)

    def test_create_name_cache(self, mock_http_client):
        """Test creating name cache via convenience function."""
        cache = create_name_cache(mock_http_client)
        
        assert isinstance(cache, NameResolutionCache)
        assert cache.http_client == mock_http_client
        assert cache.cache_ttl == timedelta(minutes=5)

    def test_resolve_patient_name_unique_match(self, mock_http_client):
        """Test convenience function for unique name resolution."""
        cache = create_name_cache(mock_http_client)
        
        # Mock successful cache refresh and resolution
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                'id': 1,
                'first_name': 'John',
                'last_name': 'Doe',
                'nric': 'S1234567A',
                'contact_no': '+6512345678',
                'date_of_birth': '1990-01-01'
            }
        ]
        mock_http_client.request.return_value = mock_response
        
        # Resolve name
        patient_id, ambiguity_list, cache_refreshed = resolve_patient_name(cache, "John Doe")
        
        # Verify unique resolution
        assert patient_id == 1
        assert ambiguity_list == []
        assert cache_refreshed is True

    def test_resolve_patient_name_multiple_matches(self, mock_http_client):
        """Test convenience function for ambiguous name resolution."""
        cache = create_name_cache(mock_http_client)
        
        # Mock cache with duplicate names
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                'id': 1,
                'first_name': 'John',
                'last_name': 'Doe',
                'nric': 'S1234567A',
                'contact_no': '+6512345678',
                'date_of_birth': '1990-01-01'
            },
            {
                'id': 2,
                'first_name': 'John',
                'last_name': 'Doe',
                'nric': 'S2345678B',
                'contact_no': None,
                'date_of_birth': None
            }
        ]
        mock_http_client.request.return_value = mock_response
        
        # Resolve ambiguous name
        patient_id, ambiguity_list, cache_refreshed = resolve_patient_name(cache, "John Doe")
        
        # Verify ambiguous resolution
        assert patient_id is None
        assert len(ambiguity_list) == 2
        assert "ID 1: John Doe" in ambiguity_list[0]
        assert "ID 2: John Doe" in ambiguity_list[1]
        assert cache_refreshed is True

    def test_resolve_patient_name_no_match(self, mock_http_client):
        """Test convenience function for no matches."""
        cache = create_name_cache(mock_http_client)
        
        # Mock empty cache
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_http_client.request.return_value = mock_response
        
        # Resolve non-existent name
        patient_id, ambiguity_list, cache_refreshed = resolve_patient_name(cache, "Non Existent")
        
        # Verify no match
        assert patient_id is None
        assert ambiguity_list == []
        assert cache_refreshed is False  # No cache refresh when empty data returned
