"""
Phase 17: Gemini SDK Migration (V2)
Migration from manual httpx calls to official google-genai SDK for accurate token tracking.
"""

import logging
import time
import json
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict

from google import genai
from google.genai import types
from google.genai.errors import APIError

from .enums import Intent

logger = logging.getLogger(__name__)

# Configuration constants
DEFAULT_MAX_INPUT_LENGTH = 1000  # Maximum input length to prevent token abuse


@dataclass
class GeminiUsageMetricsV2:
    """Track Gemini API usage with accurate token counts from SDK"""
    successful_calls: int = 0
    failed_calls: int = 0
    total_tokens_used: int = 0
    prompt_tokens_used: int = 0
    completion_tokens_used: int = 0
    total_cost_usd: float = 0.0
    last_call_timestamp: Optional[float] = None
    
    def add_call(
        self,
        success: bool,
        total_tokens: int = 0,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cost: float = 0.0
    ):
        """Add a call to metrics tracking with accurate token counts"""
        if success:
            self.successful_calls += 1
        else:
            self.failed_calls += 1
        
        self.total_tokens_used += total_tokens
        self.prompt_tokens_used += prompt_tokens
        self.completion_tokens_used += completion_tokens
        self.total_cost_usd += cost
        self.last_call_timestamp = time.time()


# Global metrics instance
_gemini_metrics_v2 = GeminiUsageMetricsV2()


def calculate_cost(
    prompt_tokens: int,
    completion_tokens: int,
    model: str = "gemini-2.0-flash-exp"
) -> float:
    """
    Calculate cost based on actual token usage.
    
    Gemini 2.0 Flash pricing (as of 2025):
    - Input: $0.10 per 1M tokens
    - Output: $0.30 per 1M tokens
    
    Args:
        prompt_tokens: Number of input tokens
        completion_tokens: Number of output tokens
        model: Model name
    
    Returns:
        Cost in USD
    """
    # Rates per 1M tokens
    INPUT_RATE = 0.10
    OUTPUT_RATE = 0.30
    
    input_cost = (prompt_tokens * INPUT_RATE) / 1_000_000
    output_cost = (completion_tokens * OUTPUT_RATE) / 1_000_000
    
    return input_cost + output_cost


class GeminiClientV2:
    """
    Official google-genai SDK client for accurate token tracking.
    Replaces manual httpx implementation with SDK methods.
    """
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.0-flash-exp"):
        """
        Initialize Gemini client with official SDK.
        
        Args:
            api_key: Gemini API key (if None, loads from settings)
            model: Model name to use
        """
        self._load_config(api_key, model)
        self._initialize_client()
    
    def _load_config(self, api_key: Optional[str], model: str):
        """Load configuration from settings or parameters"""
        if api_key:
            self.api_key = api_key
            self.model = model
            self.max_input_length = DEFAULT_MAX_INPUT_LENGTH
        else:
            # Load from Django settings
            try:
                from django.conf import settings
                self.api_key = getattr(settings, 'GEMINI_API_KEY', None)
                self.model = getattr(settings, 'GEMINI_MODEL', 'gemini-2.0-flash-exp')
                self.timeout = getattr(settings, 'LLM_REQUEST_TIMEOUT', 30.0)
                self.max_retries = getattr(settings, 'LLM_MAX_RETRIES', 3)
                self.max_input_length = getattr(settings, 'GEMINI_MAX_INPUT_LENGTH', DEFAULT_MAX_INPUT_LENGTH)
            except:
                self.api_key = None
                self.model = model
                self.timeout = 30.0
                self.max_retries = 3
                self.max_input_length = DEFAULT_MAX_INPUT_LENGTH
    
    def _initialize_client(self):
        """Initialize the official genai client"""
        if self.api_key:
            self.genai_client = genai.Client(api_key=self.api_key)
            logger.info(f"[GEMINI-SDK] ✅ Initialized client with model: {self.model}")
        else:
            self.genai_client = None
            logger.warning("[GEMINI-SDK] ⚠️ No API key configured")
    
    async def count_tokens(self, text: str) -> int:
        """
        Count tokens using official SDK method.
        
        Args:
            text: Text to count tokens for
        
        Returns:
            Number of tokens (0 on error)
        """
        if not self.genai_client:
            return 0
        
        try:
            response = await self.genai_client.aio.models.count_tokens(
                model=self.model,
                contents=text
            )
            
            token_count = response.total_tokens
            logger.debug(f"[GEMINI-SDK] Token count for text: {token_count}")
            return token_count
            
        except Exception as e:
            logger.error(f"[GEMINI-SDK] ❌ Token counting error: {e}")
            return 0
    
    async def generate_content_with_tokens(
        self,
        prompt: str,
        temperature: float = 0.1,
        max_output_tokens: int = 200
    ) -> Tuple[Any, int]:
        """
        Generate content and return response with token count.
        
        Args:
            prompt: Prompt text
            temperature: Generation temperature
            max_output_tokens: Maximum tokens to generate
        
        Returns:
            Tuple of (response, total_tokens)
        """
        if not self.genai_client:
            raise APIError("Gemini client not initialized")
        
        try:
            config = types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                top_p=0.8,
                top_k=10
            )
            
            response = await self.genai_client.aio.models.generate_content(
                model=self.model,
                contents=prompt,
                config=config
            )
            
            # Extract token count from usage metadata
            total_tokens = 0
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                total_tokens = getattr(response.usage_metadata, 'total_token_count', 0)
            
            return response, total_tokens
            
        except Exception as e:
            logger.error(f"[GEMINI-SDK] ❌ Content generation error: {e}")
            raise
    
    def _sanitize_input(self, text: str) -> str:
        """Sanitize user input to prevent prompt injection"""
        if not text:
            return ""
        
        # Remove potential injection patterns
        sanitized = text.replace("\\n", " ").replace("\\t", " ")
        
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
                logger.warning(f"[GEMINI-SDK] ⚠️ Potential prompt injection detected: {pattern}")
                sanitized = sanitized.replace(pattern, "[FILTERED]")
        
        # Limit length to prevent token abuse
        if len(sanitized) > self.max_input_length:
            sanitized = sanitized[:self.max_input_length] + "..."
            logger.info(f"[GEMINI-SDK] Input truncated to {self.max_input_length} chars to prevent token abuse")
        
        return sanitized.strip()
    
    def _build_intent_classification_prompt(
        self,
        message: str,
        context: str = "",
        conversation_summary: str = ""
    ) -> str:
        """Build structured prompt for intent classification"""
        clean_message = self._sanitize_input(message)
        clean_context = self._sanitize_input(context)
        clean_summary = self._sanitize_input(conversation_summary)
        
        context_section = ""
        if clean_context:
            context_section = f"\\nRecent context: {clean_context}"
        if clean_summary:
            context_section += f"\\nConversation summary: {clean_summary}"
        
        # Build intents list
        intent_descriptions = {
            Intent.CREATE_PATIENT: "Creating new patient records",
            Intent.UPDATE_PATIENT: "Modifying existing patient information",
            Intent.DELETE_PATIENT: "Removing patient records",
            Intent.LIST_PATIENTS: "Showing all patients",
            Intent.GET_PATIENT_DETAILS: "Getting specific patient information",
            Intent.GET_SCAN_RESULTS: "Retrieving scan/wound analysis results",
            Intent.SHOW_MORE_SCANS: "Show additional scan results",
            Intent.PROVIDE_DEPTH_MAPS: "Provide depth map data",
            Intent.PROVIDE_AGENT_STATS: "Show agent statistics",
            Intent.CANCEL: "Canceling current operation",
            Intent.UNKNOWN: "Cannot determine intent or ambiguous"
        }
        
        intents_section = "\n".join([
            f"{i}. {intent.name} - {intent_descriptions.get(intent, 'Medical assistant intent')}"
            for i, intent in enumerate(Intent, 1)
        ])
        
        prompt = f"""You are a medical assistant for wound care management. Classify the user's intent from this message.

User message: "{clean_message}"{context_section}

Classify into exactly one of these intents:
{intents_section}

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
    
    async def classify_intent_fallback(
        self,
        message: str,
        context: str = "",
        conversation_summary: str = ""
    ) -> Intent:
        """
        Classify intent using official SDK with accurate token tracking.
        
        Args:
            message: User message
            context: Recent context
            conversation_summary: Conversation summary
        
        Returns:
            Classified Intent enum value
        """
        if not self.genai_client:
            logger.info("[GEMINI-SDK] Client not configured, returning UNKNOWN")
            return Intent.UNKNOWN
        
        try:
            prompt = self._build_intent_classification_prompt(message, context, conversation_summary)
            response, total_tokens = await self.generate_content_with_tokens(prompt)
            
            # Extract token breakdown from usage_metadata
            prompt_tokens = 0
            completion_tokens = 0
            
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                prompt_tokens = getattr(response.usage_metadata, 'prompt_token_count', 0)
                completion_tokens = getattr(response.usage_metadata, 'candidates_token_count', 0)
            
            # Calculate cost
            cost = calculate_cost(prompt_tokens, completion_tokens, self.model)
            
            # Parse response
            text = response.text.strip()
            
            # Handle markdown formatting
            if '```json' in text:
                json_start = text.find('```json') + 7
                json_end = text.find('```', json_start)
                if json_end > json_start:
                    text = text[json_start:json_end].strip()
            elif '```' in text:
                text = text.replace('```', '').strip()
            
            parsed = json.loads(text)
            intent_str = parsed.get('intent', '').upper()
            confidence = parsed.get('confidence', 0.0)
            reason = parsed.get('reason', '')
            
            # Validate intent enum
            try:
                intent = Intent[intent_str]
                logger.info(
                    f"[GEMINI-SDK] ✅ Classified: {intent.name} "
                    f"(confidence: {confidence}, tokens: {total_tokens}, cost: ${cost:.6f})"
                )
                
                # Track metrics with ACTUAL tokens
                _gemini_metrics_v2.add_call(
                    success=True,
                    total_tokens=total_tokens,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    cost=cost
                )
                
                return intent
                
            except KeyError:
                logger.warning(f"[GEMINI-SDK] ⚠️ Invalid intent: {intent_str}")
                _gemini_metrics_v2.add_call(success=False)
                return Intent.UNKNOWN
                
        except Exception as e:
            logger.error(f"[GEMINI-SDK] ❌ Intent classification error: {e}")
            _gemini_metrics_v2.add_call(success=False)
            return Intent.UNKNOWN
    
    async def extract_fields_fallback(
        self,
        message: str,
        missing_fields: list[str]
    ) -> Dict[str, Any]:
        """
        Extract fields using SDK with accurate token tracking.
        
        Args:
            message: User message
            missing_fields: Fields to extract
        
        Returns:
            Dictionary of extracted fields
        """
        if not self.genai_client or not missing_fields:
            return {}
        
        try:
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

Respond with ONLY a JSON object containing the extracted fields. Use null for missing fields."""

            response, total_tokens = await self.generate_content_with_tokens(prompt)
            
            # Track metrics
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                prompt_tokens = getattr(response.usage_metadata, 'prompt_token_count', 0)
                completion_tokens = getattr(response.usage_metadata, 'candidates_token_count', 0)
                cost = calculate_cost(prompt_tokens, completion_tokens)
                
                _gemini_metrics_v2.add_call(
                    success=True,
                    total_tokens=total_tokens,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    cost=cost
                )
            
            # Parse response
            text = response.text.strip()
            if '```json' in text:
                json_start = text.find('```json') + 7
                json_end = text.find('```', json_start)
                if json_end > json_start:
                    text = text[json_start:json_end].strip()
            
            parsed = json.loads(text)
            
            # Filter to requested fields
            extracted = {}
            for field in missing_fields:
                value = parsed.get(field)
                if value is not None and str(value).strip():
                    extracted[field] = value
            
            logger.info(f"[GEMINI-SDK] ✅ Extracted fields: {extracted}")
            return extracted
            
        except Exception as e:
            logger.error(f"[GEMINI-SDK] ❌ Field extraction error: {e}")
            return {}


# Global client instance
_gemini_client_v2 = GeminiClientV2()


# Public API functions
async def classify_intent_fallback_v2(
    message: str,
    context: str = "",
    conversation_summary: str = ""
) -> Intent:
    """Public API for intent classification with SDK"""
    return await _gemini_client_v2.classify_intent_fallback(message, context, conversation_summary)


async def extract_fields_fallback_v2(
    message: str,
    missing_fields: list[str]
) -> Dict[str, Any]:
    """Public API for field extraction with SDK"""
    return await _gemini_client_v2.extract_fields_fallback(message, missing_fields)


def get_gemini_metrics_v2() -> Dict[str, Any]:
    """Get metrics with accurate token counts"""
    return asdict(_gemini_metrics_v2)


def reset_gemini_metrics_v2():
    """Reset metrics (for testing)"""
    global _gemini_metrics_v2
    _gemini_metrics_v2 = GeminiUsageMetricsV2()


def reset_gemini_client_v2():
    """Reset Gemini client state (for testing)"""
    global _gemini_client_v2
    _gemini_client_v2 = GeminiClientV2()
    reset_gemini_metrics_v2()


__all__ = [
    'GeminiClientV2',
    'classify_intent_fallback_v2',
    'extract_fields_fallback_v2',
    'get_gemini_metrics_v2',
    'reset_gemini_metrics_v2',
    'reset_gemini_client_v2',
    'calculate_cost'
]


