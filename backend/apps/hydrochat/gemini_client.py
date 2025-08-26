"""
Phase 14 - Gemini API Integration & LLM Fallback
HydroChat.md §2, §15, §16, §17

This module provides Gemini API integration for intent classification and field extraction
when regex-based approaches return UNKNOWN or fail to extract required fields.
"""

from __future__ import annotations
import json
import logging
import time
import asyncio
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict

import httpx
from dataclasses import dataclass, asdict

from .enums import Intent

logger = logging.getLogger(__name__)


@dataclass
class GeminiUsageMetrics:
    """Track Gemini API usage for cost monitoring per §29"""
    successful_calls: int = 0
    failed_calls: int = 0
    total_tokens_used: int = 0
    total_cost_usd: float = 0.0
    last_call_timestamp: Optional[float] = None
    
    def add_call(self, success: bool, tokens: int = 0, cost: float = 0.0):
        """Add a call to metrics tracking"""
        if success:
            self.successful_calls += 1
        else:
            self.failed_calls += 1
        self.total_tokens_used += tokens
        self.total_cost_usd += cost
        self.last_call_timestamp = time.time()


# Global metrics instance
_gemini_metrics = GeminiUsageMetrics()


class GeminiAPIError(Exception):
    """Custom exception for Gemini API errors"""
    def __init__(self, message: str, status_code: Optional[int] = None, retry_after: Optional[float] = None):
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


class GeminiClient:
    """
    Client for Gemini API integration with exponential backoff and cost tracking.
    Uses gemini-2.5-flash model as specified in §2 for speed optimization.
    """
    
    def __init__(self):
        self._api_key = None
        self._model = None
        self._timeout = None
        self._max_retries = None
        self._retry_delay = None
        self._initialized = False
        
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
    
    def _ensure_initialized(self):
        """Lazy initialization of settings to avoid import-time Django configuration issues"""
        if self._initialized:
            return
            
        try:
            from django.conf import settings
            self._api_key = getattr(settings, 'GEMINI_API_KEY', None)
            self._model = getattr(settings, 'GEMINI_MODEL', 'gemini-2.5-flash')
            self._timeout = getattr(settings, 'LLM_REQUEST_TIMEOUT', 30.0)
            self._max_retries = getattr(settings, 'LLM_MAX_RETRIES', 3)
            self._retry_delay = getattr(settings, 'LLM_RETRY_DELAY', 1.0)
            
            if not self._api_key:
                logger.warning("Gemini API key not configured. LLM fallback disabled.")
            
            self._initialized = True
        except Exception as e:
            logger.warning(f"Could not initialize Gemini client: {e}")
            self._api_key = None
            self._initialized = True
    
    @property
    def api_key(self):
        self._ensure_initialized()
        return self._api_key
    
    @api_key.setter
    def api_key(self, value):
        self._api_key = value
    
    @property 
    def model(self):
        self._ensure_initialized()
        return self._model or 'gemini-2.5-flash'
    
    @model.setter
    def model(self, value):
        self._model = value
    
    @property
    def timeout(self):
        self._ensure_initialized()
        return self._timeout or 30.0
    
    @timeout.setter  
    def timeout(self, value):
        self._timeout = value
    
    @property
    def max_retries(self):
        self._ensure_initialized()
        return self._max_retries or 3
    
    @max_retries.setter
    def max_retries(self, value):
        self._max_retries = value
    
    @property
    def retry_delay(self):
        self._ensure_initialized()
        return self._retry_delay or 1.0
    
    @retry_delay.setter
    def retry_delay(self, value):
        self._retry_delay = value
    
    def _sanitize_input(self, text: str) -> str:
        """
        Sanitize user input to prevent prompt injection per §17.
        Remove potentially malicious patterns while preserving medical context.
        """
        if not text:
            return ""
        
        # Remove potential system prompt injection patterns
        sanitized = text.replace("\\n", " ").replace("\\t", " ")
        
        # Remove common injection patterns
        injection_patterns = [
            "ignore previous instructions",
            "system:",
            "assistant:",
            "user:",
            "```",
            "<|",
            "|>",
        ]
        
        text_lower = sanitized.lower()
        for pattern in injection_patterns:
            if pattern in text_lower:
                logger.warning(f"Potential prompt injection detected: {pattern}")
                # Replace with safe equivalent
                sanitized = sanitized.replace(pattern, "[FILTERED]")
        
        # Limit length to prevent token abuse
        if len(sanitized) > 1000:
            sanitized = sanitized[:1000] + "..."
            logger.info("Input truncated to prevent token abuse")
        
        return sanitized.strip()
    
    def _build_intent_classification_prompt(self, message: str, context: str = "", conversation_summary: str = "") -> str:
        """
        Build structured prompt for intent classification with examples per §15.
        """
        # Sanitize inputs
        clean_message = self._sanitize_input(message)
        clean_context = self._sanitize_input(context)
        clean_summary = self._sanitize_input(conversation_summary)
        
        # Build context section
        context_section = ""
        if clean_context:
            context_section = f"\\nRecent context: {clean_context}"
        if clean_summary:
            context_section += f"\\nConversation summary: {clean_summary}"
        
        prompt = f"""You are a medical assistant for wound care management. Classify the user's intent from this message.

User message: "{clean_message}"{context_section}

Classify into exactly one of these intents:
1. CREATE_PATIENT - Creating new patient records
2. UPDATE_PATIENT - Modifying existing patient information
3. DELETE_PATIENT - Removing patient records
4. LIST_PATIENTS - Showing all patients
5. GET_SCAN_RESULTS - Retrieving scan/wound analysis results
6. GET_PATIENT_DETAILS - Getting specific patient information
7. CANCEL - Canceling current operation
8. UNKNOWN - Cannot determine intent or ambiguous

Examples:
- "add new patient John Doe" → CREATE_PATIENT
- "update patient contact details" → UPDATE_PATIENT
- "show me scan results" → GET_SCAN_RESULTS
- "list all patients" → LIST_PATIENTS
- "cancel this operation" → CANCEL
- "hello how are you" → UNKNOWN

Respond with ONLY a JSON object in this exact format:
{{"intent": "INTENT_NAME", "confidence": 0.95, "reason": "Brief explanation"}}"""

        return prompt
    
    def _build_field_extraction_prompt(self, message: str, missing_fields: list[str]) -> str:
        """
        Build structured prompt for field extraction when regex patterns fail.
        """
        clean_message = self._sanitize_input(message)
        fields_list = ", ".join(missing_fields)
        
        prompt = f"""Extract medical patient information from this message.

User message: "{clean_message}"

Extract these specific fields if present: {fields_list}

Field formats:
- first_name: Given name (e.g., "John")
- last_name: Family name (e.g., "Doe") 
- nric: Singapore NRIC (format: S1234567A)
- contact_no: Phone number (8-15 digits, may include +)
- date_of_birth: Date as YYYY-MM-DD
- patient_id: Numeric ID when referencing existing patient
- details: Additional medical details

Examples:
- "patient John Smith S1234567A contact 91234567" 
  → {{"first_name": "John", "last_name": "Smith", "nric": "S1234567A", "contact_no": "91234567"}}
- "update patient 123 with new contact number eight one two three four five six seven"
  → {{"patient_id": 123, "contact_no": "81234567"}}

Respond with ONLY a JSON object containing the extracted fields. Use null for missing fields.
{{"first_name": null, "last_name": null, "nric": null, "contact_no": null, "date_of_birth": null, "patient_id": null, "details": null}}"""

        return prompt
    
    async def _call_gemini_api(self, prompt: str) -> Dict[str, Any]:
        """
        Make API call to Gemini with exponential backoff retry logic per §17.
        """
        if not self.api_key:
            raise GeminiAPIError("Gemini API key not configured")
        
        url = f"{self.base_url}/models/{self.model}:generateContent"
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key
        }
        
        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "temperature": 0.1,  # Low temperature for consistent classification
                "maxOutputTokens": 200,  # Limit output for cost control
                "topP": 0.8,
                "topK": 10
            }
        }
        
        last_error = None
        retry_delay = self.retry_delay
        
        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(url, json=payload, headers=headers)
                    
                    if response.status_code == 200:
                        result = response.json()
                        return result
                    
                    elif response.status_code == 429:  # Rate limit
                        retry_after = float(response.headers.get('retry-after', retry_delay))
                        logger.warning(f"Rate limited, waiting {retry_after}s before retry {attempt + 1}")
                        if attempt < self.max_retries:
                            await self._async_sleep(retry_after)
                            continue
                        else:
                            raise GeminiAPIError(
                                f"Rate limited after {self.max_retries} retries",
                                status_code=429,
                                retry_after=retry_after
                            )
                    
                    else:
                        error_text = response.text
                        logger.error(f"Gemini API error {response.status_code}: {error_text}")
                        raise GeminiAPIError(
                            f"API error {response.status_code}: {error_text}",
                            status_code=response.status_code
                        )
                        
            except GeminiAPIError:
                # Re-raise GeminiAPIError without wrapping
                raise
                        
            except httpx.TimeoutException as e:
                last_error = GeminiAPIError(f"Request timeout: {e}")
                logger.warning(f"Timeout on attempt {attempt + 1}: {e}")
                
            except httpx.RequestError as e:
                last_error = GeminiAPIError(f"Request error: {e}")
                logger.warning(f"Request error on attempt {attempt + 1}: {e}")
                
            except asyncio.TimeoutError as e:
                last_error = GeminiAPIError(f"Async timeout: {e}")
                logger.warning(f"Async timeout on attempt {attempt + 1}: {e}")
            
            except Exception as e:
                last_error = GeminiAPIError(f"Unexpected error: {e}")
                logger.error(f"Unexpected error on attempt {attempt + 1}: {e}")
            
            # Exponential backoff for retries
            if attempt < self.max_retries:
                await self._async_sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
        
        # All retries exhausted
        _gemini_metrics.add_call(success=False)
        raise last_error or GeminiAPIError("All retry attempts failed")
    
    async def _async_sleep(self, seconds: float):
        """Async sleep helper"""
        import asyncio
        await asyncio.sleep(seconds)
    
    def _extract_json_response(self, api_response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract and parse JSON from Gemini API response with validation.
        """
        try:
            candidates = api_response.get('candidates', [])
            if not candidates:
                raise ValueError("No candidates in API response")
            
            content = candidates[0].get('content', {})
            parts = content.get('parts', [])
            if not parts:
                raise ValueError("No content parts in API response")
            
            text = parts[0].get('text', '').strip()
            if not text:
                raise ValueError("Empty response text")
            
            # Extract JSON from response (handle potential markdown formatting)
            if '```json' in text:
                json_start = text.find('```json') + 7
                json_end = text.find('```', json_start)
                if json_end > json_start:
                    text = text[json_start:json_end].strip()
            elif '```' in text:
                # Remove any code block markers
                text = text.replace('```', '').strip()
            
            # Handle escaped newlines and common LLM response patterns
            text = text.replace('\\n', '\n').replace('\\t', '\t').strip()
            if text.startswith('json'):
                text = text[4:].strip()
            
            # Parse JSON
            parsed = json.loads(text)
            return parsed
            
        except (KeyError, IndexError, json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse Gemini response: {e}. Response: {api_response}")
            raise GeminiAPIError(f"Invalid response format: {e}")
    
    async def classify_intent_fallback(self, message: str, context: str = "", conversation_summary: str = "") -> Intent:
        """
        Fallback intent classification using Gemini API per §15.
        Returns UNKNOWN if API fails or response is invalid.
        """
        if not self.api_key:
            logger.info("Gemini API key not configured, returning UNKNOWN")
            return Intent.UNKNOWN

        try:
            prompt = self._build_intent_classification_prompt(message, context, conversation_summary)
            api_response = await self._call_gemini_api(prompt)
            parsed = self._extract_json_response(api_response)
            
            # Validate response schema
            intent_str = parsed.get('intent', '').upper()
            confidence = parsed.get('confidence', 0.0)
            reason = parsed.get('reason', '')
            
            # Validate intent is in enum
            try:
                intent = Intent[intent_str]
                logger.info(f"Gemini classified intent: {intent} (confidence: {confidence}, reason: {reason})")
                _gemini_metrics.add_call(success=True, tokens=100, cost=0.001)  # Estimate moved here
                return intent
                
            except KeyError:
                logger.warning(f"Gemini returned invalid intent: {intent_str}")
                _gemini_metrics.add_call(success=False)
                return Intent.UNKNOWN
                
        except GeminiAPIError as e:
            logger.error(f"Gemini API error during intent classification: {e}")
            _gemini_metrics.add_call(success=False)
            return Intent.UNKNOWN
        
        except Exception as e:
            logger.error(f"Unexpected error in Gemini intent classification: {e}")
            _gemini_metrics.add_call(success=False)
            return Intent.UNKNOWN
    
    async def extract_fields_fallback(self, message: str, missing_fields: list[str]) -> Dict[str, Any]:
        """
        Fallback field extraction using Gemini API when regex patterns fail.
        Returns empty dict if API fails.
        """
        if not self.api_key or not missing_fields:
            return {}

        try:
            prompt = self._build_field_extraction_prompt(message, missing_fields)
            api_response = await self._call_gemini_api(prompt)
            # Track successful metrics
            _gemini_metrics.add_call(True, len(prompt), 0.0)
            parsed = self._extract_json_response(api_response)
            
            # Filter to only requested fields and remove null values
            extracted = {}
            for field in missing_fields:
                value = parsed.get(field)
                if value is not None and str(value).strip():
                    extracted[field] = value
            
            logger.info(f"Gemini extracted fields: {extracted}")
            return extracted
            
        except GeminiAPIError as e:
            logger.error(f"Gemini API error during field extraction: {e}")
            return {}
        
        except Exception as e:
            logger.error(f"Unexpected error in Gemini field extraction: {e}")
            return {}
    
    def get_usage_metrics(self) -> Dict[str, Any]:
        """Get current usage metrics for monitoring per §29"""
        return asdict(_gemini_metrics)
    
    def reset_metrics(self):
        """Reset usage metrics (for testing)"""
        global _gemini_metrics
        _gemini_metrics = GeminiUsageMetrics()
    
    def reset_for_testing(self):
        """Reset client state for testing"""
        self._initialized = False
        self._api_key = None
        self._model = None
        self._temperature = None


# Global client instance
_gemini_client = GeminiClient()


# Public API functions matching intent_classifier.py interface
async def classify_intent_fallback(message: str, context: str = "", conversation_summary: str = "") -> Intent:
    """
    Public API for Gemini-based intent classification fallback per §15.
    Used when regex-based classification returns UNKNOWN.
    """
    return await _gemini_client.classify_intent_fallback(message, context, conversation_summary)


async def extract_fields_fallback(message: str, missing_fields: list[str]) -> Dict[str, Any]:
    """
    Public API for Gemini-based field extraction fallback.
    Used when regex patterns fail to extract required fields.
    """
    return await _gemini_client.extract_fields_fallback(message, missing_fields)


def get_gemini_metrics() -> Dict[str, Any]:
    """Get Gemini API usage metrics for cost monitoring per §29"""
    return _gemini_client.get_usage_metrics()


def reset_gemini_metrics():
    """Reset Gemini metrics (for testing)"""
    _gemini_client.reset_metrics()


def reset_gemini_client():
    """Reset Gemini client state (for testing)"""
    _gemini_client.reset_for_testing()


__all__ = [
    'classify_intent_fallback',
    'extract_fields_fallback', 
    'get_gemini_metrics',
    'reset_gemini_metrics',
    'reset_gemini_client',
    'GeminiAPIError',
    'GeminiUsageMetrics'
]
