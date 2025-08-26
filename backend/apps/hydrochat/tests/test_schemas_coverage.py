# Phase 13 Tests: Schema Coverage Tests
# Tests to improve coverage of schemas.py

import pytest
from datetime import date, datetime


class TestPatientSchemas:
    """Test Pydantic schemas for patient data"""
    
    def test_patient_create_input_basic(self):
        """Test: PatientCreateInput schema"""
        
        from apps.hydrochat.schemas import PatientCreateInput
        
        # Test required fields only
        patient_data = {
            "first_name": "John",
            "last_name": "Doe", 
            "nric": "S1234567A"
        }
        
        patient = PatientCreateInput(**patient_data)
        
        assert patient.first_name == "John"
        assert patient.last_name == "Doe"
        assert patient.nric == "S1234567A"
        assert patient.date_of_birth is None
        assert patient.contact_no is None
        assert patient.details is None
    
    def test_patient_create_input_full(self):
        """Test: PatientCreateInput with all fields"""
        
        from apps.hydrochat.schemas import PatientCreateInput
        
        # Test with all fields
        patient_data = {
            "first_name": "Jane",
            "last_name": "Smith",
            "nric": "T9876543B",
            "date_of_birth": date(1990, 5, 15),
            "contact_no": "+65 9123 4567",
            "details": "Patient has allergies to shellfish"
        }
        
        patient = PatientCreateInput(**patient_data)
        
        assert patient.first_name == "Jane"
        assert patient.last_name == "Smith"
        assert patient.nric == "T9876543B"
        assert patient.date_of_birth == date(1990, 5, 15)
        assert patient.contact_no == "+65 9123 4567"
        assert patient.details == "Patient has allergies to shellfish"


class TestPatientOutput:
    """Test PatientOutput schema"""
    
    def test_patient_output_basic(self):
        """Test: PatientOutput schema"""
        
        from apps.hydrochat.schemas import PatientOutput
        
        patient_data = {
            "id": 123,
            "first_name": "Alice",
            "last_name": "Johnson",
            "nric": "S5555555Z"
        }
        
        patient = PatientOutput(**patient_data)
        
        assert patient.id == 123
        assert patient.first_name == "Alice"
        assert patient.last_name == "Johnson"
        assert patient.nric == "S5555555Z"


class TestPatientUpdateInput:
    """Test PatientUpdateInput schema"""
    
    def test_patient_update_input(self):
        """Test: PatientUpdateInput schema"""
        
        from apps.hydrochat.schemas import PatientUpdateInput
        
        update_data = {
            "id": 456,
            "first_name": "Bob",
            "last_name": "Wilson",
            "nric": "T1111111C",
            "contact_no": "+65 8888 9999"
        }
        
        patient = PatientUpdateInput(**update_data)
        
        assert patient.id == 456
        assert patient.first_name == "Bob"
        assert patient.last_name == "Wilson"
        assert patient.nric == "T1111111C"
        assert patient.contact_no == "+65 8888 9999"


class TestScanResultListItem:
    """Test ScanResultListItem schema"""
    
    def test_scan_result_basic(self):
        """Test: ScanResultListItem schema"""
        
        from apps.hydrochat.schemas import ScanResultListItem
        
        now = datetime.now()
        
        scan_data = {
            "id": 789,
            "scan_id": 101,
            "created_at": now,
            "updated_at": now
        }
        
        scan = ScanResultListItem(**scan_data)
        
        assert scan.id == 789
        assert scan.scan_id == 101
        assert scan.created_at == now
        assert scan.updated_at == now
        assert scan.patient_name is None
        assert scan.volume_estimate is None
    
    def test_scan_result_full(self):
        """Test: ScanResultListItem with all fields"""
        
        from apps.hydrochat.schemas import ScanResultListItem
        
        now = datetime.now()
        scan_date = datetime.now()
        
        scan_data = {
            "id": 999,
            "scan_id": 202,
            "patient_name": "Test Patient",
            "patient_name_display": "Test P****t",
            "scan_date": scan_date,
            "stl_file": "http://example.com/file.stl",
            "depth_map_8bit": "http://example.com/depth_8.png",
            "depth_map_16bit": "http://example.com/depth_16.png",
            "preview_image": "http://example.com/preview.jpg",
            "volume_estimate": 125.5,
            "processing_metadata": {"steps": 5, "duration": "2.3s"},
            "file_sizes": {"stl": 1024, "depth": 512},
            "created_at": now,
            "updated_at": now
        }
        
        scan = ScanResultListItem(**scan_data)
        
        assert scan.id == 999
        assert scan.scan_id == 202
        assert scan.patient_name == "Test Patient"
        assert scan.patient_name_display == "Test P****t"
        assert scan.volume_estimate == 125.5
        assert scan.processing_metadata == {"steps": 5, "duration": "2.3s"}
        assert scan.file_sizes == {"stl": 1024, "depth": 512}


class TestSchemaImports:
    """Test schema module imports and __all__"""
    
    def test_schema_all_exports(self):
        """Test: Schema module __all__ list"""
        
        from apps.hydrochat.schemas import __all__
        
        expected_exports = [
            'PatientCreateInput', 
            'PatientOutput', 
            'PatientUpdateInput', 
            'ScanResultListItem'
        ]
        
        for export in expected_exports:
            assert export in __all__
    
    def test_pydantic_imports(self):
        """Test: Pydantic import handling"""
        
        # Test that schemas can be imported without errors
        from apps.hydrochat.schemas import (
            PatientCreateInput,
            PatientOutput,
            PatientUpdateInput,
            ScanResultListItem
        )
        
        # Basic validation that classes exist
        assert PatientCreateInput is not None
        assert PatientOutput is not None
        assert PatientUpdateInput is not None
        assert ScanResultListItem is not None
