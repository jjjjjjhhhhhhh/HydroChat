from __future__ import annotations
from datetime import date, datetime
from typing import Optional, Dict, Any

try:
    from pydantic import BaseModel, HttpUrl
except ImportError:  # pydantic not yet installed
    class BaseModel:  # type: ignore
        pass
    HttpUrl = str  # type: ignore

class PatientCreateInput(BaseModel):
    first_name: str
    last_name: str
    nric: str
    date_of_birth: Optional[date] = None
    contact_no: Optional[str] = None
    details: Optional[str] = None

class PatientOutput(BaseModel):
    id: int
    first_name: str
    last_name: str
    nric: str
    date_of_birth: Optional[date] = None
    contact_no: Optional[str] = None
    details: Optional[str] = None

class PatientUpdateInput(PatientCreateInput):
    id: int

class ScanResultListItem(BaseModel):
    id: int
    scan_id: int
    patient_name: Optional[str] = None
    patient_name_display: Optional[str] = None
    scan_date: Optional[datetime] = None
    stl_file: Optional[HttpUrl] = None
    depth_map_8bit: Optional[HttpUrl] = None
    depth_map_16bit: Optional[HttpUrl] = None
    preview_image: Optional[HttpUrl] = None
    volume_estimate: Optional[float] = None
    processing_metadata: Optional[Dict[str, Any]] = None
    file_sizes: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

__all__ = [
    'PatientCreateInput', 'PatientOutput', 'PatientUpdateInput', 'ScanResultListItem'
]
