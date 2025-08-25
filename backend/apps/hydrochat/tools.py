# HydroChat Tool Layer Implementation
# Provides REST endpoint abstraction with validation, error handling, and NRIC masking
# Implements patient and scan result management operations for conversational interface

import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Union, Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from .enums import DownloadStage, Intent
from .http_client import HttpClient
from .logging_formatter import metrics_logger
from .utils import mask_nric

logger = logging.getLogger(__name__)


# ===== VALIDATION MODELS =====

class PatientInput(BaseModel):
    """Pydantic model for patient creation/update validation."""
    first_name: str = Field(..., min_length=1, max_length=50)
    last_name: str = Field(..., min_length=1, max_length=50)
    nric: str = Field(..., min_length=1, max_length=9)
    date_of_birth: Optional[str] = Field(None, description="YYYY-MM-DD format")
    contact_no: Optional[str] = Field(None, description="Phone number with optional + prefix")
    details: Optional[str] = Field(None, max_length=500)

    @field_validator('nric', mode='before')
    @classmethod
    def validate_nric(cls, v: str) -> str:
        """Validate NRIC format and length."""
        if not isinstance(v, str):
            raise ValueError("NRIC must be a string")
        v = v.strip().upper()
        if not v:
            raise ValueError("NRIC cannot be empty")
        if len(v) > 9:
            raise ValueError("NRIC cannot be longer than 9 characters")
        return v

    @field_validator('date_of_birth')
    @classmethod
    def validate_date_of_birth(cls, v: Optional[str]) -> Optional[str]:
        """Validate date format if provided."""
        if v is None:
            return v
        try:
            datetime.strptime(v, '%Y-%m-%d')
            return v
        except ValueError:
            raise ValueError("Date of birth must be in YYYY-MM-DD format")

    @field_validator('contact_no')
    @classmethod
    def validate_contact_no(cls, v: Optional[str]) -> Optional[str]:
        """Validate contact number format if provided."""
        if v is None:
            return v
        v = v.strip()
        if not v:
            return None
        # Basic validation for phone number format
        if not v.replace('+', '').replace('-', '').replace(' ', '').isdigit():
            raise ValueError("Contact number must contain only digits, +, -, and spaces")
        return v


class ToolResponse(BaseModel):
    """Standard response format for all tool operations."""
    success: bool
    data: Optional[Union[Dict, List]] = None  # Allow both Dict and List
    error: Optional[str] = None
    nric_masked: bool = Field(default=False, description="Whether NRIC was masked in logs")
    # Phase 8: Enhanced error handling
    status_code: Optional[int] = Field(default=None, description="HTTP status code from backend")
    validation_errors: Optional[Dict[str, List[str]]] = Field(default=None, description="Field-specific validation errors from 400 responses")
    retryable: bool = Field(default=False, description="Whether operation can be safely retried")


# ===== TOOL FUNCTIONS =====

class PatientTools:
    """Patient management tools with validation and error handling."""
    
    def __init__(self, http_client: HttpClient):
        self.http_client = http_client

    def _parse_400_validation_error(self, response) -> Dict[str, Any]:
        """
        Parse 400 validation error response from Django REST Framework.
        
        Args:
            response: HTTP response object with 400 status code
            
        Returns:
            Dict with 'summary' (user-friendly message) and 'field_errors' (field-specific issues)
        """
        try:
            error_data = response.json()
            field_errors = {}
            error_messages = []
            
            if isinstance(error_data, dict):
                for field_name, field_issues in error_data.items():
                    if isinstance(field_issues, list):
                        field_errors[field_name] = field_issues
                        error_messages.append(f"{field_name}: {', '.join(field_issues)}")
                    else:
                        field_errors[field_name] = [str(field_issues)]
                        error_messages.append(f"{field_name}: {field_issues}")
            else:
                # Fallback for non-dict error responses
                error_messages.append(str(error_data))
                
            summary = '; '.join(error_messages) if error_messages else "Validation error"
            
            return {
                'summary': summary,
                'field_errors': field_errors
            }
            
        except Exception as e:
            logger.warning(f"[Tools] Failed to parse 400 error response: {e}")
            return {
                'summary': "Validation error (unable to parse details)",
                'field_errors': {}
            }

    def tool_create_patient(self, **kwargs) -> ToolResponse:
        """
        Create a new patient with validation and NRIC masking.
        
        Args:
            **kwargs: Patient data (first_name, last_name, nric, date_of_birth, contact_no, details)
            
        Returns:
            ToolResponse with patient data or error
        """
        try:
            # Validate input using Pydantic model
            patient_input = PatientInput(**kwargs)
            
            # Log creation attempt with masked NRIC
            logger.info(f"[Tools] 🏥 Creating patient: {patient_input.first_name} {patient_input.last_name}, NRIC: {mask_nric(patient_input.nric)}")
            
            # Prepare payload for API
            payload = patient_input.model_dump(exclude_none=True)
            
            # Call REST API
            response = self.http_client.request('POST', '/api/patients/', json=payload)
            
            if response.status_code == 201:
                patient_data = response.json()
                logger.info(f"[Tools] ✅ Patient created successfully - ID: {patient_data.get('id')}")
                return ToolResponse(success=True, data=patient_data, nric_masked=True)
            elif response.status_code == 400:
                # Parse validation errors and extract field-specific issues
                error_detail = self._parse_400_validation_error(response)
                logger.error(f"[Tools] ❌ Validation error creating patient: {error_detail['summary']}")
                return ToolResponse(
                    success=False, 
                    error=error_detail['summary'],
                    validation_errors=error_detail['field_errors'],
                    status_code=400
                )
            else:
                error_msg = f"Failed to create patient: {response.status_code}"
                logger.error(f"[Tools] ❌ {error_msg}")
                return ToolResponse(success=False, error=error_msg, status_code=response.status_code)
                
        except ValidationError as e:
            error_msg = f"Validation error: {e}"
            logger.error(f"[Tools] ❌ {error_msg}")
            return ToolResponse(success=False, error=error_msg)
        except Exception as e:
            error_msg = f"Unexpected error creating patient: {e}"
            logger.error(f"[Tools] ❌ {error_msg}")
            return ToolResponse(success=False, error=error_msg)

    def tool_list_patients(self, limit: Optional[int] = None) -> ToolResponse:
        """
        List all patients with optional limit and NRIC masking in logs.
        
        Args:
            limit: Optional limit on number of patients returned
            
        Returns:
            ToolResponse with patient list or error
        """
        try:
            logger.info("[Tools] 📋 Listing patients")
            
            # Call REST API
            params = {'limit': limit} if limit else {}
            response = self.http_client.request('GET', '/api/patients/', params=params)
            
            if response.status_code == 200:
                patients_data = response.json()
                patient_count = len(patients_data)
                
                # Log with masked NRICs
                for patient in patients_data:
                    if 'nric' in patient:
                        logger.info(f"[Tools] Patient {patient.get('id')}: {patient.get('first_name')} {patient.get('last_name')}, NRIC: {mask_nric(patient['nric'])}")
                
                logger.info(f"[Tools] ✅ Listed {patient_count} patients")
                return ToolResponse(success=True, data=patients_data, nric_masked=True)
            else:
                error_msg = f"Failed to list patients: {response.status_code}"
                logger.error(f"[Tools] ❌ {error_msg}")
                return ToolResponse(success=False, error=error_msg)
                
        except Exception as e:
            error_msg = f"Unexpected error listing patients: {e}"
            logger.error(f"[Tools] ❌ {error_msg}")
            return ToolResponse(success=False, error=error_msg)

    def tool_get_patient(self, patient_id: int) -> ToolResponse:
        """
        Get a specific patient by ID with NRIC masking in logs.
        
        Args:
            patient_id: Patient ID to retrieve
            
        Returns:
            ToolResponse with patient data or error
        """
        try:
            logger.info(f"[Tools] 🔍 Getting patient ID: {patient_id}")
            
            # Call REST API
            response = self.http_client.request('GET', f'/api/patients/{patient_id}/')
            
            if response.status_code == 200:
                patient_data = response.json()
                
                # Log with masked NRIC
                if 'nric' in patient_data:
                    logger.info(f"[Tools] Found patient: {patient_data.get('first_name')} {patient_data.get('last_name')}, NRIC: {mask_nric(patient_data['nric'])}")
                
                logger.info(f"[Tools] ✅ Retrieved patient ID: {patient_id}")
                return ToolResponse(success=True, data=patient_data, nric_masked=True)
            elif response.status_code == 404:
                error_msg = f"Patient with ID {patient_id} not found"
                logger.warning(f"[Tools] ⚠️ {error_msg}")
                return ToolResponse(success=False, error=error_msg)
            else:
                error_msg = f"Failed to get patient: {response.status_code}"
                logger.error(f"[Tools] ❌ {error_msg}")
                return ToolResponse(success=False, error=error_msg)
                
        except Exception as e:
            error_msg = f"Unexpected error getting patient: {e}"
            logger.error(f"[Tools] ❌ {error_msg}")
            return ToolResponse(success=False, error=error_msg)

    def tool_update_patient(self, patient_id: int, **kwargs) -> ToolResponse:
        """
        Update a patient using PUT semantics with validation and NRIC masking.
        
        Args:
            patient_id: Patient ID to update
            **kwargs: Patient data fields to update
            
        Returns:
            ToolResponse with updated patient data or error
        """
        try:
            # First, get current patient data
            logger.info(f"[Tools] 📝 Updating patient ID: {patient_id}")
            
            current_response = self.tool_get_patient(patient_id)
            if not current_response.success:
                return current_response
                
            current_data = current_response.data or {}
            
            # Merge current data with updates
            update_data = {**current_data, **kwargs}
            
            # Remove read-only fields
            update_data.pop('id', None)
            update_data.pop('user', None)
            
            # Validate merged data
            patient_input = PatientInput(**update_data)
            
            # Log update with masked NRIC
            logger.info(f"[Tools] Updating patient: {patient_input.first_name} {patient_input.last_name}, NRIC: {mask_nric(patient_input.nric)}")
            
            # Prepare payload for API
            payload = patient_input.model_dump(exclude_none=True)
            
            # Call REST API with PUT
            response = self.http_client.request('PUT', f'/api/patients/{patient_id}/', json=payload)
            
            if response.status_code == 200:
                patient_data = response.json()
                logger.info(f"[Tools] ✅ Patient updated successfully - ID: {patient_id}")
                return ToolResponse(success=True, data=patient_data, nric_masked=True)
            elif response.status_code == 400:
                # Parse validation errors and extract field-specific issues
                error_detail = self._parse_400_validation_error(response)
                logger.error(f"[Tools] ❌ Validation error updating patient: {error_detail['summary']}")
                return ToolResponse(
                    success=False, 
                    error=error_detail['summary'],
                    validation_errors=error_detail['field_errors'],
                    status_code=400
                )
            elif response.status_code == 404:
                error_msg = f"Patient with ID {patient_id} not found"
                logger.warning(f"[Tools] ⚠️ {error_msg}")
                return ToolResponse(success=False, error=error_msg, status_code=404)
            else:
                error_msg = f"Failed to update patient: {response.status_code}"
                logger.error(f"[Tools] ❌ {error_msg}")
                return ToolResponse(success=False, error=error_msg, status_code=response.status_code)
                
        except ValidationError as e:
            error_msg = f"Validation error: {e}"
            logger.error(f"[Tools] ❌ {error_msg}")
            return ToolResponse(success=False, error=error_msg)
        except Exception as e:
            error_msg = f"Unexpected error updating patient: {e}"
            logger.error(f"[Tools] ❌ {error_msg}")
            return ToolResponse(success=False, error=error_msg)

    def tool_delete_patient(self, patient_id: int) -> ToolResponse:
        """
        Delete a patient by ID with confirmation logging.
        
        Args:
            patient_id: Patient ID to delete
            
        Returns:
            ToolResponse with success status or error
        """
        try:
            # First get patient info for logging
            logger.info(f"[Tools] 🗑️ Deleting patient ID: {patient_id}")
            
            patient_response = self.tool_get_patient(patient_id)
            if not patient_response.success:
                return patient_response
                
            patient_data = patient_response.data or {}
            # Handle both dict and potential list responses safely
            if isinstance(patient_data, dict):
                patient_name = f"{patient_data.get('first_name', 'Unknown')} {patient_data.get('last_name', 'Unknown')}"
                masked_nric = mask_nric(patient_data.get('nric', ''))
            else:
                # Fallback for unexpected data format
                patient_name = f"Patient ID {patient_id}"
                masked_nric = "***UNKNOWN***"
            
            # Call REST API
            response = self.http_client.request('DELETE', f'/api/patients/{patient_id}/')
            
            if response.status_code == 204:
                logger.info(f"[Tools] ✅ Patient deleted successfully - {patient_name}, NRIC: {masked_nric}")
                return ToolResponse(success=True, data={'message': f'Patient {patient_name} deleted successfully'}, nric_masked=True)
            elif response.status_code == 404:
                error_msg = f"Patient with ID {patient_id} not found"
                logger.warning(f"[Tools] ⚠️ {error_msg}")
                return ToolResponse(success=False, error=error_msg)
            else:
                error_msg = f"Failed to delete patient: {response.status_code}"
                logger.error(f"[Tools] ❌ {error_msg}")
                return ToolResponse(success=False, error=error_msg)
                
        except Exception as e:
            error_msg = f"Unexpected error deleting patient: {e}"
            logger.error(f"[Tools] ❌ {error_msg}")
            return ToolResponse(success=False, error=error_msg)


class ScanTools:
    """Scan result management tools."""
    
    def __init__(self, http_client: HttpClient):
        self.http_client = http_client

    def tool_list_scan_results(self, patient_id: Optional[int] = None, limit: Optional[int] = None) -> ToolResponse:
        """
        List scan results with optional patient filter and limit.
        
        Args:
            patient_id: Optional patient ID to filter results
            limit: Optional limit on number of results
            
        Returns:
            ToolResponse with scan results or error
        """
        try:
            if patient_id:
                logger.info(f"[Tools] 🔬 Listing scan results for patient ID: {patient_id}")
            else:
                logger.info("[Tools] 🔬 Listing all scan results")
            
            # Build query parameters
            params = {}
            if patient_id:
                params['patient'] = patient_id
            if limit:
                params['limit'] = limit
            
            # Call REST API
            response = self.http_client.request('GET', '/api/scan-results/', params=params)
            
            if response.status_code == 200:
                results_data = response.json()
                result_count = len(results_data)
                
                logger.info(f"[Tools] ✅ Listed {result_count} scan results")
                return ToolResponse(success=True, data=results_data)
            else:
                error_msg = f"Failed to list scan results: {response.status_code}"
                logger.error(f"[Tools] ❌ {error_msg}")
                return ToolResponse(success=False, error=error_msg)
                
        except Exception as e:
            error_msg = f"Unexpected error listing scan results: {e}"
            logger.error(f"[Tools] ❌ {error_msg}")
            return ToolResponse(success=False, error=error_msg)


# ===== MAIN TOOL MANAGER =====

class ToolManager:
    """Main tool manager that coordinates all tool operations with metrics tracking."""
    
    def __init__(self, http_client: HttpClient):
        self.http_client = http_client
        self.patient_tools = PatientTools(http_client)
        self.scan_tools = ScanTools(http_client)
        
    def execute_tool(self, intent: Intent, state_metrics: Dict[str, int], **kwargs) -> ToolResponse:
        """
        Execute appropriate tool based on intent and parameters with metrics tracking.
        
        Args:
            intent: The classified intent
            state_metrics: Reference to conversation state metrics for updating
            **kwargs: Parameters for the tool
            
        Returns:
            ToolResponse with result or error
        """
        tool_name = f"tool_{intent.name.lower()}"
        
        # Log tool execution start
        metrics_logger.log_tool_call_start(tool_name, state_metrics)
        
        try:
            # Execute the appropriate tool based on intent
            result = None
            if intent == Intent.CREATE_PATIENT:
                result = self.patient_tools.tool_create_patient(**kwargs)
            elif intent == Intent.LIST_PATIENTS:
                result = self.patient_tools.tool_list_patients(**kwargs)
            elif intent == Intent.GET_PATIENT_DETAILS:
                result = self.patient_tools.tool_get_patient(**kwargs)
            elif intent == Intent.UPDATE_PATIENT:
                result = self.patient_tools.tool_update_patient(**kwargs)
            elif intent == Intent.DELETE_PATIENT:
                result = self.patient_tools.tool_delete_patient(**kwargs)
            elif intent == Intent.GET_SCAN_RESULTS:
                result = self.scan_tools.tool_list_scan_results(**kwargs)
            else:
                error_msg = f"No tool available for intent: {intent.name}"
                logger.error(f"[Tools] ❌ {error_msg}")
                result = ToolResponse(success=False, error=error_msg)
            
            # Track metrics based on result
            if result and result.success:
                response_size = len(str(result.data)) if result.data else 0
                metrics_logger.log_tool_call_success(tool_name, state_metrics, response_size)
            else:
                error = Exception(result.error if result else "Unknown tool error")
                metrics_logger.log_tool_call_error(tool_name, error, state_metrics)
                
            return result
                
        except Exception as e:
            # Log error and update metrics
            error_msg = f"Unexpected error executing tool: {e}"
            logger.error(f"[Tools] ❌ {error_msg}")
            metrics_logger.log_tool_call_error(tool_name, e, state_metrics)
            return ToolResponse(success=False, error=error_msg)
