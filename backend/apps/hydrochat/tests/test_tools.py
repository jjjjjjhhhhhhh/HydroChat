# Test suite for HydroChat tool layer
# Tests all patient and scan tools with validation, error handling, and NRIC masking

import json
from unittest.mock import MagicMock, patch
from pydantic import ValidationError
import pytest

from apps.hydrochat.enums import Intent
from apps.hydrochat.http_client import HttpClient
from apps.hydrochat.tools import PatientTools, ScanTools, ToolManager, PatientInput, ToolResponse


class TestPatientInput:
    """Test Pydantic validation model for patient inputs."""
    
    def test_valid_patient_input(self):
        """Test valid patient input validation."""
        data = {
            'first_name': 'John',
            'last_name': 'Doe',
            'nric': 'S1234567A',
            'date_of_birth': '1990-01-01',
            'contact_no': '+6512345678',
            'details': 'Test patient'
        }
        patient = PatientInput(**data)
        assert patient.first_name == 'John'
        assert patient.last_name == 'Doe'
        assert patient.nric == 'S1234567A'
        assert patient.date_of_birth == '1990-01-01'
        assert patient.contact_no == '+6512345678'
        assert patient.details == 'Test patient'

    def test_required_fields_validation(self):
        """Test validation of required fields."""
        # Missing required fields should raise ValidationError
        with pytest.raises(ValidationError):
            PatientInput()
        
        with pytest.raises(ValidationError):
            PatientInput(first_name='John')
        
        with pytest.raises(ValidationError):
            PatientInput(first_name='John', last_name='Doe')

    def test_nric_validation(self):
        """Test NRIC field validation."""
        base_data = {'first_name': 'John', 'last_name': 'Doe'}
        
        # Valid NRIC
        patient = PatientInput(**base_data, nric='S1234567A')
        assert patient.nric == 'S1234567A'
        
        # Empty NRIC should raise ValidationError
        with pytest.raises(ValidationError):  # Just check that ValidationError is raised
            PatientInput(**base_data, nric='')
        
        # Long NRIC should raise ValidationError (using Pydantic's built-in validation)
        with pytest.raises(ValidationError):
            PatientInput(**base_data, nric='S1234567890')
        
        # NRIC should be uppercase and stripped
        patient = PatientInput(**base_data, nric=' s1234567a ')
        assert patient.nric == 'S1234567A'

    def test_date_of_birth_validation(self):
        """Test date of birth field validation."""
        base_data = {'first_name': 'John', 'last_name': 'Doe', 'nric': 'S1234567A'}
        
        # Valid date
        patient = PatientInput(**base_data, date_of_birth='1990-01-01')
        assert patient.date_of_birth == '1990-01-01'
        
        # None is valid
        patient = PatientInput(**base_data, date_of_birth=None)
        assert patient.date_of_birth is None
        
        # Invalid date format should raise ValidationError
        with pytest.raises(ValidationError, match="Date of birth must be in YYYY-MM-DD format"):
            PatientInput(**base_data, date_of_birth='01/01/1990')

    def test_contact_no_validation(self):
        """Test contact number field validation."""
        base_data = {'first_name': 'John', 'last_name': 'Doe', 'nric': 'S1234567A'}
        
        # Valid contact numbers
        valid_contacts = ['+6512345678', '12345678', '+65 1234 5678', '+65-1234-5678']
        for contact in valid_contacts:
            patient = PatientInput(**base_data, contact_no=contact)
            assert patient.contact_no == contact
        
        # None is valid
        patient = PatientInput(**base_data, contact_no=None)
        assert patient.contact_no is None
        
        # Empty string should become None
        patient = PatientInput(**base_data, contact_no='')
        assert patient.contact_no is None
        
        # Invalid contact with letters should raise ValidationError
        with pytest.raises(ValidationError, match="Contact number must contain only digits"):
            PatientInput(**base_data, contact_no='123abc456')


class TestPatientTools:
    """Test patient management tools."""
    
    @pytest.fixture
    def mock_http_client(self):
        """Mock HTTP client for testing."""
        return MagicMock(spec=HttpClient)
    
    @pytest.fixture
    def patient_tools(self, mock_http_client):
        """Patient tools instance with mocked HTTP client."""
        return PatientTools(mock_http_client)

    def test_tool_create_patient_success(self, patient_tools, mock_http_client):
        """Test successful patient creation."""
        # Mock successful API response
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {'id': 1, 'first_name': 'John', 'last_name': 'Doe', 'nric': 'S1234567A'}
        mock_http_client.request.return_value = mock_response
        
        # Call tool
        result = patient_tools.tool_create_patient(
            first_name='John',
            last_name='Doe',
            nric='S1234567A',
            date_of_birth='1990-01-01'
        )
        
        # Verify result
        assert result.success is True
        assert result.data['id'] == 1
        assert result.nric_masked is True
        
        # Verify HTTP call
        mock_http_client.request.assert_called_once_with(
            'POST',
            '/api/patients/',
            json={
                'first_name': 'John',
                'last_name': 'Doe',
                'nric': 'S1234567A',
                'date_of_birth': '1990-01-01'
            }
        )

    def test_tool_create_patient_validation_error(self, patient_tools, mock_http_client):
        """Test patient creation with validation error."""
        # Call tool with invalid data (missing required field)
        result = patient_tools.tool_create_patient(first_name='John')
        
        # Verify result
        assert result.success is False
        assert 'Validation error' in result.error
        
        # HTTP client should not be called
        mock_http_client.request.assert_not_called()

    def test_tool_create_patient_api_error(self, patient_tools, mock_http_client):
        """Test patient creation with API error."""
        # Mock API error response
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"nric": ["Invalid NRIC format"]}  # Proper validation error format
        mock_http_client.request.return_value = mock_response
        
        # Call tool
        result = patient_tools.tool_create_patient(
            first_name='John',
            last_name='Doe',
            nric='S1234567A'
        )
        
        # Verify result
        assert result.success is False
        assert 'nric: Invalid NRIC format' in result.error  # Phase 8: Enhanced validation error parsing

    def test_tool_list_patients_success(self, patient_tools, mock_http_client):
        """Test successful patient listing."""
        # Mock successful API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {'id': 1, 'first_name': 'John', 'last_name': 'Doe', 'nric': 'S1234567A'},
            {'id': 2, 'first_name': 'Jane', 'last_name': 'Smith', 'nric': 'S2345678B'}
        ]
        mock_http_client.request.return_value = mock_response
        
        # Call tool
        result = patient_tools.tool_list_patients()
        
        # Verify result
        assert result.success is True
        assert len(result.data) == 2
        assert result.nric_masked is True
        
        # Verify HTTP call
        mock_http_client.request.assert_called_once_with('GET', '/api/patients/', params={})

    def test_tool_list_patients_with_limit(self, patient_tools, mock_http_client):
        """Test patient listing with limit parameter."""
        # Mock successful API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{'id': 1, 'first_name': 'John', 'last_name': 'Doe', 'nric': 'S1234567A'}]
        mock_http_client.request.return_value = mock_response
        
        # Call tool with limit
        result = patient_tools.tool_list_patients(limit=10)
        
        # Verify result
        assert result.success is True
        assert len(result.data) == 1
        
        # Verify HTTP call with params
        mock_http_client.request.assert_called_once_with('GET', '/api/patients/', params={'limit': 10})

    def test_tool_get_patient_success(self, patient_tools, mock_http_client):
        """Test successful patient retrieval."""
        # Mock successful API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'id': 1, 'first_name': 'John', 'last_name': 'Doe', 'nric': 'S1234567A'}
        mock_http_client.request.return_value = mock_response
        
        # Call tool
        result = patient_tools.tool_get_patient(patient_id=1)
        
        # Verify result
        assert result.success is True
        assert result.data['id'] == 1
        assert result.nric_masked is True
        
        # Verify HTTP call
        mock_http_client.request.assert_called_once_with('GET', '/api/patients/1/')

    def test_tool_get_patient_not_found(self, patient_tools, mock_http_client):
        """Test patient retrieval when patient not found."""
        # Mock 404 response
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_http_client.request.return_value = mock_response
        
        # Call tool
        result = patient_tools.tool_get_patient(patient_id=999)
        
        # Verify result
        assert result.success is False
        assert 'Patient with ID 999 not found' in result.error

    def test_tool_update_patient_success(self, patient_tools, mock_http_client):
        """Test successful patient update."""
        # Mock get patient response (for current data)
        get_response = MagicMock()
        get_response.status_code = 200
        get_response.json.return_value = {
            'id': 1,
            'first_name': 'John',
            'last_name': 'Doe',
            'nric': 'S1234567A',
            'date_of_birth': '1990-01-01'
        }
        
        # Mock update response
        update_response = MagicMock()
        update_response.status_code = 200
        update_response.json.return_value = {
            'id': 1,
            'first_name': 'John',
            'last_name': 'Smith',  # Updated
            'nric': 'S1234567A',
            'date_of_birth': '1990-01-01'
        }
        
        # Mock HTTP client to return different responses for GET and PUT
        mock_http_client.request.side_effect = [get_response, update_response]
        
        # Call tool
        result = patient_tools.tool_update_patient(patient_id=1, last_name='Smith')
        
        # Verify result
        assert result.success is True
        assert result.data['last_name'] == 'Smith'
        assert result.nric_masked is True
        
        # Verify HTTP calls
        assert mock_http_client.request.call_count == 2
        mock_http_client.request.assert_any_call('GET', '/api/patients/1/')
        mock_http_client.request.assert_any_call(
            'PUT',
            '/api/patients/1/',
            json={
                'first_name': 'John',
                'last_name': 'Smith',
                'nric': 'S1234567A',
                'date_of_birth': '1990-01-01'
            }
        )

    def test_tool_delete_patient_success(self, patient_tools, mock_http_client):
        """Test successful patient deletion."""
        # Mock get patient response (for logging)
        get_response = MagicMock()
        get_response.status_code = 200
        get_response.json.return_value = {
            'id': 1,
            'first_name': 'John',
            'last_name': 'Doe',
            'nric': 'S1234567A'
        }
        
        # Mock delete response
        delete_response = MagicMock()
        delete_response.status_code = 204
        
        # Mock HTTP client responses
        mock_http_client.request.side_effect = [get_response, delete_response]
        
        # Call tool
        result = patient_tools.tool_delete_patient(patient_id=1)
        
        # Verify result
        assert result.success is True
        assert 'John Doe deleted successfully' in result.data['message']
        assert result.nric_masked is True
        
        # Verify HTTP calls
        assert mock_http_client.request.call_count == 2
        mock_http_client.request.assert_any_call('GET', '/api/patients/1/')
        mock_http_client.request.assert_any_call('DELETE', '/api/patients/1/')


class TestScanTools:
    """Test scan result management tools."""
    
    @pytest.fixture
    def mock_http_client(self):
        """Mock HTTP client for testing."""
        return MagicMock(spec=HttpClient)
    
    @pytest.fixture
    def scan_tools(self, mock_http_client):
        """Scan tools instance with mocked HTTP client."""
        return ScanTools(mock_http_client)

    def test_tool_list_scan_results_success(self, scan_tools, mock_http_client):
        """Test successful scan results listing."""
        # Mock successful API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {'id': 1, 'patient': 1, 'scan_type': 'wound'},
            {'id': 2, 'patient': 1, 'scan_type': 'wound'}
        ]
        mock_http_client.request.return_value = mock_response
        
        # Call tool
        result = scan_tools.tool_list_scan_results()
        
        # Verify result
        assert result.success is True
        assert len(result.data) == 2
        
        # Verify HTTP call
        mock_http_client.request.assert_called_once_with('GET', '/api/scan-results/', params={})

    def test_tool_list_scan_results_with_patient_filter(self, scan_tools, mock_http_client):
        """Test scan results listing with patient filter."""
        # Mock successful API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{'id': 1, 'patient': 1, 'scan_type': 'wound'}]
        mock_http_client.request.return_value = mock_response
        
        # Call tool with patient filter
        result = scan_tools.tool_list_scan_results(patient_id=1)
        
        # Verify result
        assert result.success is True
        assert len(result.data) == 1
        
        # Verify HTTP call with params
        mock_http_client.request.assert_called_once_with('GET', '/api/scan-results/', params={'patient': 1})

    def test_tool_list_scan_results_with_limit(self, scan_tools, mock_http_client):
        """Test scan results listing with limit parameter."""
        # Mock successful API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{'id': 1, 'patient': 1, 'scan_type': 'wound'}]
        mock_http_client.request.return_value = mock_response
        
        # Call tool with limit
        result = scan_tools.tool_list_scan_results(patient_id=1, limit=5)
        
        # Verify result
        assert result.success is True
        
        # Verify HTTP call with params
        mock_http_client.request.assert_called_once_with(
            'GET', 
            '/api/scan-results/', 
            params={'patient': 1, 'limit': 5}
        )


class TestToolManager:
    """Test main tool manager."""
    
    @pytest.fixture
    def mock_http_client(self):
        """Mock HTTP client for testing."""
        return MagicMock(spec=HttpClient)
    
    @pytest.fixture
    def tool_manager(self, mock_http_client):
        """Tool manager instance with mocked HTTP client."""
        return ToolManager(mock_http_client)

    def test_execute_tool_create_patient(self, tool_manager, mock_http_client):
        """Test executing create patient tool."""
        # Mock successful API response
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {'id': 1, 'first_name': 'John', 'last_name': 'Doe', 'nric': 'S1234567A'}
        mock_http_client.request.return_value = mock_response
        
        # Execute tool
        result = tool_manager.execute_tool(
            Intent.CREATE_PATIENT,
            first_name='John',
            last_name='Doe',
            nric='S1234567A'
        )
        
        # Verify result
        assert result.success is True
        assert result.data['id'] == 1

    def test_execute_tool_list_patients(self, tool_manager, mock_http_client):
        """Test executing list patients tool."""
        # Mock successful API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{'id': 1, 'first_name': 'John', 'last_name': 'Doe', 'nric': 'S1234567A'}]
        mock_http_client.request.return_value = mock_response
        
        # Execute tool
        result = tool_manager.execute_tool(Intent.LIST_PATIENTS)
        
        # Verify result
        assert result.success is True
        assert len(result.data) == 1

    def test_execute_tool_get_patient_details(self, tool_manager, mock_http_client):
        """Test executing get patient details tool."""
        # Mock successful API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'id': 1, 'first_name': 'John', 'last_name': 'Doe', 'nric': 'S1234567A'}
        mock_http_client.request.return_value = mock_response
        
        # Execute tool
        result = tool_manager.execute_tool(Intent.GET_PATIENT_DETAILS, patient_id=1)
        
        # Verify result
        assert result.success is True
        assert result.data['id'] == 1

    def test_execute_tool_update_patient(self, tool_manager, mock_http_client):
        """Test executing update patient tool."""
        # Mock get response (for current data)
        get_response = MagicMock()
        get_response.status_code = 200
        get_response.json.return_value = {
            'id': 1,
            'first_name': 'John',
            'last_name': 'Doe',
            'nric': 'S1234567A'
        }
        
        # Mock update response
        update_response = MagicMock()
        update_response.status_code = 200
        update_response.json.return_value = {
            'id': 1,
            'first_name': 'John',
            'last_name': 'Smith',
            'nric': 'S1234567A'
        }
        
        mock_http_client.request.side_effect = [get_response, update_response]
        
        # Execute tool
        result = tool_manager.execute_tool(
            Intent.UPDATE_PATIENT,
            patient_id=1,
            last_name='Smith'
        )
        
        # Verify result
        assert result.success is True
        assert result.data['last_name'] == 'Smith'

    def test_execute_tool_delete_patient(self, tool_manager, mock_http_client):
        """Test executing delete patient tool."""
        # Mock get response (for logging)
        get_response = MagicMock()
        get_response.status_code = 200
        get_response.json.return_value = {
            'id': 1,
            'first_name': 'John',
            'last_name': 'Doe',
            'nric': 'S1234567A'
        }
        
        # Mock delete response
        delete_response = MagicMock()
        delete_response.status_code = 204
        
        mock_http_client.request.side_effect = [get_response, delete_response]
        
        # Execute tool
        result = tool_manager.execute_tool(Intent.DELETE_PATIENT, patient_id=1)
        
        # Verify result
        assert result.success is True
        assert 'deleted successfully' in result.data['message']

    def test_execute_tool_get_scan_results(self, tool_manager, mock_http_client):
        """Test executing get scan results tool."""
        # Mock successful API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{'id': 1, 'patient': 1, 'scan_type': 'wound'}]
        mock_http_client.request.return_value = mock_response
        
        # Execute tool
        result = tool_manager.execute_tool(Intent.GET_SCAN_RESULTS, patient_id=1)
        
        # Verify result
        assert result.success is True
        assert len(result.data) == 1

    def test_execute_tool_unknown_intent(self, tool_manager, mock_http_client):
        """Test executing tool with unknown intent."""
        # Execute tool with unknown intent
        result = tool_manager.execute_tool(Intent.UNKNOWN)
        
        # Verify result
        assert result.success is False
        assert 'No tool available for intent' in result.error


class TestToolResponse:
    """Test ToolResponse model."""
    
    def test_tool_response_success(self):
        """Test successful ToolResponse."""
        response = ToolResponse(success=True, data={'id': 1}, nric_masked=True)
        assert response.success is True
        assert response.data == {'id': 1}
        assert response.error is None
        assert response.nric_masked is True

    def test_tool_response_error(self):
        """Test error ToolResponse."""
        response = ToolResponse(success=False, error='Something went wrong')
        assert response.success is False
        assert response.data is None
        assert response.error == 'Something went wrong'
        assert response.nric_masked is False
