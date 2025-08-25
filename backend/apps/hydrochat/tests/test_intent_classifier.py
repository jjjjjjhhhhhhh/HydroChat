import pytest
from apps.hydrochat.intent_classifier import (
    classify_intent, extract_fields, validate_required_patient_fields
)
from apps.hydrochat.enums import Intent


def test_intent_classification_create():
    """Test CREATE_PATIENT intent patterns."""
    assert classify_intent("create patient John Doe") == Intent.CREATE_PATIENT
    assert classify_intent("add new patient") == Intent.CREATE_PATIENT
    assert classify_intent("Add Patient Mary Smith") == Intent.CREATE_PATIENT  # case insensitive


def test_intent_classification_update():
    """Test UPDATE_PATIENT intent patterns."""
    assert classify_intent("update patient contact") == Intent.UPDATE_PATIENT
    assert classify_intent("change patient name") == Intent.UPDATE_PATIENT
    assert classify_intent("modify patient details") == Intent.UPDATE_PATIENT
    assert classify_intent("edit nric") == Intent.UPDATE_PATIENT


def test_intent_classification_delete():
    """Test DELETE_PATIENT intent patterns."""
    assert classify_intent("delete patient 5") == Intent.DELETE_PATIENT
    assert classify_intent("remove patient") == Intent.DELETE_PATIENT


def test_intent_classification_list():
    """Test LIST_PATIENTS intent patterns."""
    assert classify_intent("list patients") == Intent.LIST_PATIENTS
    assert classify_intent("show all patients") == Intent.LIST_PATIENTS


def test_intent_classification_scan_results():
    """Test GET_SCAN_RESULTS intent patterns."""
    assert classify_intent("show scans for patient 5") == Intent.GET_SCAN_RESULTS
    assert classify_intent("get scan results") == Intent.GET_SCAN_RESULTS
    assert classify_intent("list scans") == Intent.GET_SCAN_RESULTS


def test_intent_disambiguation_patient_vs_scans():
    """Test disambiguation between GET_PATIENT_DETAILS and GET_SCAN_RESULTS."""
    # Should prefer scan results when both patterns match
    assert classify_intent("show patient scan results") == Intent.GET_SCAN_RESULTS
    # Pure patient details
    assert classify_intent("get patient details") == Intent.GET_PATIENT_DETAILS


def test_intent_unknown():
    """Test UNKNOWN intent for unmatched text."""
    assert classify_intent("hello there") == Intent.UNKNOWN
    assert classify_intent("what's the weather?") == Intent.UNKNOWN
    assert classify_intent("") == Intent.UNKNOWN


def test_field_extraction_nric():
    """Test NRIC field extraction."""
    fields = extract_fields("create patient S1234567A")
    assert fields['nric'] == 'S1234567A'
    
    fields = extract_fields("patient with NRIC T7654321B")
    assert fields['nric'] == 'T7654321B'


def test_field_extraction_name():
    """Test name extraction (two capitalized tokens)."""
    fields = extract_fields("create patient John Doe")
    assert fields['first_name'] == 'John'
    assert fields['last_name'] == 'Doe'
    
    fields = extract_fields("add Mary Jane Watson")
    assert fields['first_name'] == 'Mary'
    assert fields['last_name'] == 'Jane Watson'  # Multi-word last name


def test_field_extraction_contact():
    """Test contact number extraction."""
    fields = extract_fields("patient contact 91234567")
    assert fields['contact_no'] == '91234567'
    
    fields = extract_fields("phone +6591234567")
    assert fields['contact_no'] == '+6591234567'


def test_field_extraction_dob():
    """Test date of birth extraction (YYYY-MM-DD only)."""
    fields = extract_fields("born 1990-05-15")
    assert fields['date_of_birth'] == '1990-05-15'
    
    # Invalid date format should be ignored
    fields = extract_fields("born 15/05/1990")
    assert 'date_of_birth' not in fields
    
    # Invalid date should be ignored
    fields = extract_fields("born 1990-13-45")
    assert 'date_of_birth' not in fields


def test_field_extraction_patient_id():
    """Test patient ID extraction."""
    fields = extract_fields("update patient 123")
    assert fields['patient_id'] == 123
    
    fields = extract_fields("show patient 456 details")
    assert fields['patient_id'] == 456


def test_field_extraction_combined():
    """Test extraction of multiple fields from single text."""
    text = "create patient John Smith NRIC S1234567A contact 91234567 born 1985-03-20"
    fields = extract_fields(text)
    
    assert fields['first_name'] == 'John'
    assert fields['last_name'] == 'Smith'
    assert fields['nric'] == 'S1234567A'
    assert fields['contact_no'] == '91234567'
    assert fields['date_of_birth'] == '1985-03-20'


def test_validate_required_fields():
    """Test required field validation."""
    # Complete fields
    complete_fields = {
        'first_name': 'John',
        'last_name': 'Doe', 
        'nric': 'S1234567A'
    }
    is_complete, missing = validate_required_patient_fields(complete_fields)
    assert is_complete is True
    assert len(missing) == 0
    
    # Missing fields
    incomplete_fields = {
        'first_name': 'John',
        'contact_no': '91234567'
    }
    is_complete, missing = validate_required_patient_fields(incomplete_fields)
    assert is_complete is False
    assert missing == {'last_name', 'nric'}
    
    # Empty/None values treated as missing
    empty_fields = {
        'first_name': 'John',
        'last_name': '',
        'nric': None
    }
    is_complete, missing = validate_required_patient_fields(empty_fields)
    assert is_complete is False
    assert 'last_name' in missing
    assert 'nric' in missing


def test_negative_patterns():
    """Test patterns that should NOT match."""
    # Should not match single word names
    fields = extract_fields("create patient John")
    assert 'first_name' not in fields
    
    # Should not match non-NRIC patterns
    fields = extract_fields("ID 1234567A")
    assert 'nric' not in fields
    
    # Should not match short numbers as contact
    fields = extract_fields("room 123")
    assert 'contact_no' not in fields
