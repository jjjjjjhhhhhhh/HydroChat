# HydroChat Conversation Graph Implementation
# LangGraph-based conversation orchestrator for patient management workflows
# Phase 16: Implements centralized routing with validated state transitions

import logging
from typing import Any, Dict, List, Optional, Tuple, TypedDict, Literal, cast
from datetime import datetime

from langgraph.graph import StateGraph, MessagesState, END
from langgraph.prebuilt import ToolNode

from .enums import Intent, PendingAction, ConfirmationType, DownloadStage
from .state import ConversationState
from .intent_classifier import classify_intent, extract_fields, validate_required_patient_fields
# Phase 9 & 10: Import additional detection functions
from .intent_classifier import is_show_more_scans, is_depth_map_request, is_stats_request
from .tools import ToolManager, ToolResponse
from .name_cache import NameResolutionCache, resolve_patient_name
from .http_client import HttpClient
from .logging_formatter import metrics_logger
from .agent_stats import agent_stats
from .utils import mask_nric
# Phase 16: Import centralized routing
from .graph_routing import GraphRoutingIntegration

logger = logging.getLogger(__name__)


# ===== LOGGING TAXONOMY =====

class LogCategory:
    """Logging taxonomy categories for conversation flow."""
    INTENT = "INTENT"
    MISSING = "MISSING" 
    TOOL = "TOOL"
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"
    FLOW = "FLOW"


# ===== GRAPH STATE =====

class GraphState(TypedDict):
    """State definition for the conversation graph."""
    # Core conversation
    user_message: str
    agent_response: str
    conversation_state: ConversationState
    
    # Processing results
    classified_intent: Optional[Intent]
    extracted_fields: Dict[str, Any]
    tool_result: Optional[ToolResponse]
    
    # Flow control
    next_node: Optional[str]
    should_end: bool


# ===== GRAPH NODES =====

class ConversationGraphNodes:
    """Individual node implementations for the conversation graph."""
    
    def __init__(self, tool_manager: ToolManager, name_cache: NameResolutionCache):
        self.tool_manager = tool_manager
        self.name_cache = name_cache

    def classify_intent_node(self, state: GraphState) -> GraphState:
        """
        Node 1: Classify user intent and extract fields.
        
        Routes to appropriate workflow based on classified intent.
        """
        user_message = state["user_message"]
        conv_state = state["conversation_state"]
        
        logger.info(f"[{LogCategory.INTENT}] 🧠 Classifying intent for message: '{user_message[:50]}...'")
        
        # Phase 9: Check for pagination requests first if we have scan results
        from .intent_classifier import is_show_more_scans, is_depth_map_request
        
        if is_show_more_scans(user_message) and conv_state.scan_results_buffer:
            logger.info(f"[{LogCategory.INTENT}] 📄 Detected pagination request")
            conv_state.recent_messages.append(f"User: {user_message}")
            return {
                **state,
                "classified_intent": None,  # Special handling, not a normal intent
                "extracted_fields": {},
                "conversation_state": conv_state,
                "next_node": "show_more_scans"
            }
        
        # Phase 9: Check for depth map requests during scan results context  
        if is_depth_map_request(user_message) and conv_state.scan_results_buffer:
            logger.info(f"[{LogCategory.INTENT}] 🗺️ Detected depth map request")
            conv_state.recent_messages.append(f"User: {user_message}")
            return {
                **state,
                "classified_intent": None,  # Special handling
                "extracted_fields": {},
                "conversation_state": conv_state,
                "next_node": "provide_depth_maps"
            }
        
        # Phase 10: Check for stats requests
        if is_stats_request(user_message):
            logger.info(f"[{LogCategory.INTENT}] 📊 Detected stats request")
            conv_state.recent_messages.append(f"User: {user_message}")
            return {
                **state,
                "classified_intent": None,  # Special handling
                "extracted_fields": {},
                "conversation_state": conv_state,
                "next_node": "provide_agent_stats"
            }
        
        # Regular intent classification
        intent = classify_intent(user_message)
        extracted_fields = extract_fields(user_message)
        
        # Phase 14: LLM fallback when regex returns UNKNOWN per §15
        if intent == Intent.UNKNOWN:
            logger.info(f"[{LogCategory.INTENT}] 🤖 Regex classification returned UNKNOWN, trying LLM fallback")
            try:
                # Import async function
                from .intent_classifier import llm_classify_intent_fallback
                
                # Build context for LLM
                context = " | ".join(list(conv_state.recent_messages)[-3:]) if conv_state.recent_messages else ""
                conversation_summary = conv_state.history_summary if hasattr(conv_state, 'history_summary') else ""
                
                # Call async LLM fallback
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # If we're already in an async context, create a new task
                    intent = asyncio.create_task(llm_classify_intent_fallback(user_message, context, conversation_summary))
                    intent = intent.result() if hasattr(intent, 'result') else Intent.UNKNOWN
                else:
                    intent = loop.run_until_complete(llm_classify_intent_fallback(user_message, context, conversation_summary))
                
                logger.info(f"[{LogCategory.INTENT}] 🤖 LLM fallback classified: {intent.value}")
                
                # If LLM also found fields, try field extraction fallback
                if intent != Intent.UNKNOWN and not extracted_fields:
                    logger.info(f"[{LogCategory.INTENT}] 🔍 Attempting LLM field extraction fallback")
                    try:
                        from .intent_classifier import llm_extract_fields_fallback
                        # Determine what fields we might need based on intent
                        needed_fields = []
                        if intent in [Intent.CREATE_PATIENT, Intent.UPDATE_PATIENT]:
                            needed_fields = ['first_name', 'last_name', 'nric', 'contact_no', 'date_of_birth', 'details']
                        elif intent in [Intent.GET_PATIENT_DETAILS, Intent.DELETE_PATIENT]:
                            needed_fields = ['patient_id', 'nric', 'first_name', 'last_name']
                        
                        if needed_fields:
                            # Use same async pattern as intent classification
                            if loop.is_running():
                                # If we're already in an async context, create a new task
                                task = asyncio.create_task(llm_extract_fields_fallback(user_message, needed_fields))
                                try:
                                    # Use asyncio.run in thread pool to avoid blocking
                                    import concurrent.futures
                                    with concurrent.futures.ThreadPoolExecutor() as executor:
                                        future = executor.submit(asyncio.run, llm_extract_fields_fallback(user_message, needed_fields))
                                        llm_fields = future.result(timeout=10)
                                except Exception as e:
                                    logger.warning(f"[{LogCategory.INTENT}] LLM field extraction task failed: {e}")
                                    llm_fields = {}
                            else:
                                llm_fields = loop.run_until_complete(llm_extract_fields_fallback(user_message, needed_fields))
                            
                            if llm_fields:
                                extracted_fields.update(llm_fields)
                                logger.info(f"[{LogCategory.INTENT}] 🔍 LLM extracted additional fields: {list(llm_fields.keys())}")
                    
                    except Exception as e:
                        logger.warning(f"[{LogCategory.INTENT}] LLM field extraction failed: {e}")
                        
            except Exception as e:
                logger.warning(f"[{LogCategory.INTENT}] LLM fallback failed: {e}, using UNKNOWN")
                intent = Intent.UNKNOWN
        
        # Update conversation state
        conv_state.intent = intent
        
        # Add message to history
        conv_state.recent_messages.append(f"User: {user_message}")
        
        logger.info(f"[{LogCategory.INTENT}] ✅ Intent classified: {intent.value}")
        logger.debug(f"[{LogCategory.INTENT}] Extracted fields: {list(extracted_fields.keys())}")
        
        # Determine next node based on intent
        next_node = self._determine_next_node_from_intent(intent)
        
        return {
            **state,
            "classified_intent": intent,
            "extracted_fields": extracted_fields,
            "conversation_state": conv_state,
            "next_node": next_node
        }

    def create_patient_node(self, state: GraphState) -> GraphState:
        """
        Node 2: Handle patient creation workflow.
        
        Validates required fields and either creates patient or requests missing fields.
        """
        conv_state = state["conversation_state"]
        extracted_fields = state["extracted_fields"]
        
        logger.info(f"[{LogCategory.FLOW}] 👤 Processing create patient request")
        
        # Update conversation state for patient creation
        conv_state.pending_action = PendingAction.CREATE_PATIENT
        
        # Merge extracted fields with existing validated fields
        if extracted_fields:
            conv_state.validated_fields.update(extracted_fields)
            logger.debug(f"[{LogCategory.FLOW}] Updated validated fields: {list(conv_state.validated_fields.keys())}")
        
        # Validate required fields
        is_complete, missing_fields_set = validate_required_patient_fields(conv_state.validated_fields)
        
        if not is_complete:
            # Phase 8: Clarification loop count guard - prevent infinite loops
            if conv_state.clarification_loop_count >= 1:
                logger.warning(f"[{LogCategory.ERROR}] ⚠️ Clarification loop limit reached, offering cancellation")
                response = f"""❌ I've asked for missing information before but still need:
{', '.join(sorted(missing_fields_set))}

This seems to be taking too long. You can:
• Provide the missing information: {', '.join(sorted(missing_fields_set))}
• Say "cancel" to start over

How would you like to proceed?"""
                
                return {
                    **state,
                    "agent_response": response,
                    "conversation_state": conv_state,
                    "next_node": "end",
                    "should_end": False
                }
            
            # Missing fields - request them from user
            conv_state.pending_fields = missing_fields_set
            conv_state.clarification_loop_count += 1
            
            logger.info(f"[{LogCategory.MISSING}] ⚠️ Missing required fields: {list(missing_fields_set)}")
            
            # Generate response requesting missing fields
            field_requests = []
            for field in missing_fields_set:
                if field == 'nric':
                    field_requests.append("NRIC (e.g., S1234567A)")
                elif field == 'first_name':
                    field_requests.append("first name")
                elif field == 'last_name':
                    field_requests.append("last name")
                else:
                    field_requests.append(field.replace('_', ' '))
            
            if len(field_requests) == 1:
                response = f"I need the patient's {field_requests[0]} to create the patient record. Please provide it."
            else:
                response = f"I need the following information to create the patient record: {', '.join(field_requests)}. Please provide them."
            
            return {
                **state,
                "agent_response": response,
                "conversation_state": conv_state,
                "next_node": "end",
                "should_end": False
            }
        else:
            # All fields present - proceed to create patient
            logger.info(f"[{LogCategory.FLOW}] ✅ All required fields present, creating patient")
            
            return {
                **state,
                "conversation_state": conv_state,
                "next_node": "execute_create_patient"
            }

    def execute_create_patient_node(self, state: GraphState) -> GraphState:
        """
        Node 3: Execute patient creation via tool layer.
        """
        conv_state = state["conversation_state"]
        
        logger.info(f"[{LogCategory.TOOL}] 🔧 Executing patient creation")
        
        try:
            # Execute patient creation tool
            tool_result = self.tool_manager.execute_tool(
                Intent.CREATE_PATIENT,
                conv_state.metrics,
                **conv_state.validated_fields
            )
            
            if tool_result.success and tool_result.data:
                # Success - patient created
                patient_data = tool_result.data
                if isinstance(patient_data, dict):
                    patient_name = f"{patient_data.get('first_name', '')} {patient_data.get('last_name', '')}".strip()
                    patient_id = patient_data.get('id', 'Unknown')
                    
                    logger.info(f"[{LogCategory.SUCCESS}] ✅ Patient created successfully: {patient_name} (ID: {patient_id})")
                    
                    # Invalidate name cache
                    self.name_cache.invalidate_on_crud_success("create", patient_id)
                    
                    # Reset conversation state
                    conv_state.pending_action = PendingAction.NONE
                    conv_state.validated_fields.clear()
                    conv_state.pending_fields.clear()
                    
                    # Generate success response
                    response = f"✅ Successfully created patient: **{patient_name}** (ID: {patient_id})"
                    if patient_data.get('date_of_birth'):
                        response += f"\nDate of Birth: {patient_data['date_of_birth']}"
                    if patient_data.get('contact_no'):
                        response += f"\nContact: {patient_data['contact_no']}"
                else:
                    # Reset conversation state
                    conv_state.pending_action = PendingAction.NONE
                    conv_state.validated_fields.clear()
                    conv_state.pending_fields.clear()
                    
                    response = "✅ Successfully created patient"
                    logger.warning(f"[{LogCategory.SUCCESS}] Patient created but data format unexpected: {type(patient_data)}")
                
                return {
                    **state,
                    "agent_response": response,
                    "tool_result": tool_result,
                    "conversation_state": conv_state,
                    "next_node": "end",
                    "should_end": True
                }
            else:
                # Tool execution failed
                logger.error(f"[{LogCategory.ERROR}] ❌ Patient creation failed: {tool_result.error}")
                
                # Phase 8: Handle 400 validation errors specially
                if hasattr(tool_result, 'status_code') and tool_result.status_code == 400 and hasattr(tool_result, 'validation_errors'):
                    validation_errors = tool_result.validation_errors or {}
                    logger.info(f"[{LogCategory.ERROR}] 🔄 Repopulating pending fields from validation errors: {list(validation_errors.keys())}")
                    
                    # Repopulate pending_fields from validation errors
                    conv_state.pending_fields = set(validation_errors.keys())
                    
                    # Generate field-specific error message
                    field_messages = []
                    for field, errors in validation_errors.items():
                        if isinstance(errors, list):
                            field_messages.append(f"• {field}: {', '.join(errors)}")
                        else:
                            field_messages.append(f"• {field}: {errors}")
                    
                    response = f"""❌ Please correct the following issues:

{chr(10).join(field_messages)}

Please provide the corrected information."""
                    
                    # Route back to create_patient node for field collection
                    return {
                        **state,
                        "agent_response": response,
                        "tool_result": tool_result,
                        "conversation_state": conv_state,
                        "next_node": "create_patient",  # Route back for field correction
                        "should_end": False
                    }
                else:
                    # Generic error handling for non-validation failures
                    return {
                        **state,
                        "agent_response": f"❌ Failed to create patient: {tool_result.error}",
                        "tool_result": tool_result,
                        "conversation_state": conv_state,
                        "next_node": "end",
                        "should_end": False
                    }
                
        except Exception as e:
            logger.error(f"[{LogCategory.ERROR}] ❌ Unexpected error during patient creation: {e}")
            
            return {
                **state,
                "agent_response": f"❌ An unexpected error occurred while creating the patient: {e}",
                "conversation_state": conv_state,
                "next_node": "end",
                "should_end": False
            }

    def list_patients_node(self, state: GraphState) -> GraphState:
        """
        Node 4: Handle patient listing workflow.
        """
        conv_state = state["conversation_state"]
        
        logger.info(f"[{LogCategory.FLOW}] 📋 Processing list patients request")
        
        try:
            # Execute list patients tool
            tool_result = self.tool_manager.execute_tool(Intent.LIST_PATIENTS, conv_state.metrics)
            
            if tool_result.success:
                patients_data = tool_result.data
                
                # Ensure we have a list of patients
                if isinstance(patients_data, dict):
                    # If it's a dict, it might be paginated response - try to get results array
                    patients_list = patients_data.get('results', [])
                elif isinstance(patients_data, list):
                    patients_list = patients_data
                else:
                    patients_list = []
                
                patient_count = len(patients_list)
                
                logger.info(f"[{LogCategory.SUCCESS}] ✅ Listed {patient_count} patients")
                
                if patient_count == 0:
                    response = "📋 No patients found in the system."
                else:
                    response = f"📋 Found {patient_count} patient(s):\n\n"
                    
                    for patient in patients_list:
                        patient_line = f"**{patient['first_name']} {patient['last_name']}** (ID: {patient['id']})"
                        
                        # Add additional info if available
                        info_parts = []
                        if patient.get('date_of_birth'):
                            info_parts.append(f"DOB: {patient['date_of_birth']}")
                        if patient.get('contact_no'):
                            info_parts.append(f"Contact: {patient['contact_no']}")
                        
                        if info_parts:
                            patient_line += f" - {', '.join(info_parts)}"
                        
                        response += f"• {patient_line}\n"
                
                return {
                    **state,
                    "agent_response": response,
                    "tool_result": tool_result,
                    "conversation_state": conv_state,
                    "next_node": "end",
                    "should_end": True
                }
            else:
                # Tool execution failed
                logger.error(f"[{LogCategory.ERROR}] ❌ Failed to list patients: {tool_result.error}")
                
                return {
                    **state,
                    "agent_response": f"❌ Failed to list patients: {tool_result.error}",
                    "tool_result": tool_result,
                    "conversation_state": conv_state,
                    "next_node": "end",
                    "should_end": False
                }
                
        except Exception as e:
            logger.error(f"[{LogCategory.ERROR}] ❌ Unexpected error during patient listing: {e}")
            
            return {
                **state,
                "agent_response": f"❌ An unexpected error occurred while listing patients: {e}",
                "conversation_state": conv_state,
                "next_node": "end",
                "should_end": False
            }

    def get_patient_details_node(self, state: GraphState) -> GraphState:
        """
        Node 6: Handle get patient details workflow.
        """
        conv_state = state["conversation_state"]
        extracted_fields = state["extracted_fields"]
        
        logger.info(f"[{LogCategory.FLOW}] 👤 Processing get patient details request")
        
        # Check if patient_id was provided
        patient_id = extracted_fields.get('patient_id')
        if not patient_id:
            # Try to resolve from validated_fields (from previous context)
            patient_id = conv_state.validated_fields.get('patient_id')
        
        if not patient_id:
            # No patient ID provided - ask for it
            response = "Please specify which patient you'd like to see details for (e.g., 'patient 5' or 'show patient 12')."
            return {
                **state,
                "agent_response": response,
                "conversation_state": conv_state,
                "next_node": "end",
                "should_end": False
            }
        
        try:
            # Execute get patient tool
            tool_result = self.tool_manager.execute_tool(
                Intent.GET_PATIENT_DETAILS,
                conv_state.metrics,
                patient_id=patient_id
            )
            
            if tool_result.success and tool_result.data:
                patient_data = tool_result.data
                
                # Ensure patient_data is a dict (single patient)
                if isinstance(patient_data, list) and len(patient_data) > 0:
                    patient_data = patient_data[0]
                elif not isinstance(patient_data, dict):
                    raise ValueError(f"Unexpected patient data format: {type(patient_data)}")
                
                logger.info(f"[{LogCategory.SUCCESS}] ✅ Retrieved patient details for ID: {patient_id}")
                
                # Format patient details response
                response = f"👤 **Patient Details:**\n\n"
                response += f"• **ID:** {patient_data['id']}\n"
                response += f"• **Name:** {patient_data['first_name']} {patient_data['last_name']}\n"
                response += f"• **NRIC:** {mask_nric(patient_data['nric'])}\n"
                
                if patient_data.get('date_of_birth'):
                    response += f"• **Date of Birth:** {patient_data['date_of_birth']}\n"
                if patient_data.get('contact_no'):
                    response += f"• **Contact:** {patient_data['contact_no']}\n"
                if patient_data.get('details'):
                    response += f"• **Details:** {patient_data['details']}\n"
                
                return {
                    **state,
                    "agent_response": response,
                    "tool_result": tool_result,
                    "conversation_state": conv_state,
                    "next_node": "end",
                    "should_end": True
                }
            else:
                # Tool execution failed
                logger.error(f"[{LogCategory.ERROR}] ❌ Failed to get patient details: {tool_result.error}")
                
                # Phase 8: Enhanced 404 handling offering list option
                if (hasattr(tool_result, 'status_code') and tool_result.status_code == 404) or \
                   "404" in str(tool_result.error) or "not found" in str(tool_result.error).lower():
                    response = f"""❌ Patient not found: {tool_result.error}

💡 **Helpful options:**
• Say "list patients" to see all available patients
• Provide a different patient ID to look up
• Say "cancel" to start over

How would you like to proceed?"""
                else:
                    response = f"❌ Failed to get patient details: {tool_result.error}"
                
                return {
                    **state,
                    "agent_response": response,
                    "tool_result": tool_result,
                    "conversation_state": conv_state,
                    "next_node": "end",
                    "should_end": False
                }
                
        except Exception as e:
            logger.error(f"[{LogCategory.ERROR}] ❌ Unexpected error getting patient details: {e}")
            
            return {
                **state,
                "agent_response": f"❌ An unexpected error occurred while getting patient details: {e}",
                "conversation_state": conv_state,
                "next_node": "end",
                "should_end": False
            }

    def update_patient_node(self, state: GraphState) -> GraphState:
        """
        Node 7: Handle patient update workflow with merge logic.
        """
        conv_state = state["conversation_state"]
        extracted_fields = state["extracted_fields"]
        
        logger.info(f"[{LogCategory.FLOW}] ✏️ Processing update patient request")
        
        # Update conversation state for patient update
        conv_state.pending_action = PendingAction.UPDATE_PATIENT
        
        # Check if patient_id was provided
        patient_id = extracted_fields.get('patient_id')
        if not patient_id:
            patient_id = conv_state.validated_fields.get('patient_id')
        
        if not patient_id:
            # No patient ID provided - ask for it
            response = "Please specify which patient you'd like to update (e.g., 'update patient 5' or 'modify patient 12')."
            return {
                **state,
                "agent_response": response,
                "conversation_state": conv_state,
                "next_node": "end",
                "should_end": False
            }
        
        # Store patient_id in validated_fields
        conv_state.validated_fields['patient_id'] = patient_id
        
        # Merge new extracted fields (excluding patient_id)
        update_fields = {k: v for k, v in extracted_fields.items() if k != 'patient_id' and v is not None}
        if update_fields:
            conv_state.validated_fields.update(update_fields)
            logger.debug(f"[{LogCategory.FLOW}] Extracted update fields: {list(update_fields.keys())}")
        
        # Check if we have any fields to update
        updatable_fields = {k: v for k, v in conv_state.validated_fields.items() 
                           if k != 'patient_id' and v is not None}
        
        if not updatable_fields:
            # No update fields provided - ask what to update
            response = f"What would you like to update for patient {patient_id}? You can update:\n"
            response += "• First name or last name\n"
            response += "• Contact number\n"
            response += "• Date of birth (YYYY-MM-DD format)\n"
            response += "• Details/notes\n\n"
            response += "For example: 'update patient 5 contact 91234567'"
            
            return {
                **state,
                "agent_response": response,
                "conversation_state": conv_state,
                "next_node": "end",
                "should_end": False
            }
        
        # We have fields to update - proceed to execute
        return {
            **state,
            "conversation_state": conv_state,
            "next_node": "execute_update_patient"
        }

    def execute_update_patient_node(self, state: GraphState) -> GraphState:
        """
        Node 8: Execute patient update via tool layer with PUT merge logic.
        """
        conv_state = state["conversation_state"]
        patient_id = conv_state.validated_fields['patient_id']
        
        logger.info(f"[{LogCategory.TOOL}] 🔧 Executing patient update for ID: {patient_id}")
        
        try:
            # Execute patient update tool (includes GET + merge + PUT logic)
            update_fields = {k: v for k, v in conv_state.validated_fields.items() 
                           if k != 'patient_id' and v is not None}
            
            tool_result = self.tool_manager.execute_tool(
                Intent.UPDATE_PATIENT,
                conv_state.metrics,
                patient_id=patient_id,
                **update_fields
            )
            
            if tool_result.success and tool_result.data:
                # Success - patient updated
                patient_data = tool_result.data
                
                # Ensure patient_data is a dict (single patient)
                if isinstance(patient_data, list) and len(patient_data) > 0:
                    patient_data = patient_data[0]
                elif not isinstance(patient_data, dict):
                    raise ValueError(f"Unexpected patient data format: {type(patient_data)}")
                
                patient_name = f"{patient_data.get('first_name', '')} {patient_data.get('last_name', '')}".strip()
                
                logger.info(f"[{LogCategory.SUCCESS}] ✅ Patient updated successfully: {patient_name} (ID: {patient_id})")
                
                # Invalidate name cache
                self.name_cache.invalidate_on_crud_success("update", patient_id)
                
                # Reset conversation state
                conv_state.pending_action = PendingAction.NONE
                conv_state.validated_fields.clear()
                conv_state.pending_fields.clear()
                
                # Generate success response with updated fields
                response = f"✅ Successfully updated patient: **{patient_name}** (ID: {patient_id})\n\n"
                response += "**Updated fields:**\n"
                for field, value in update_fields.items():
                    field_display = field.replace('_', ' ').title()
                    if field == 'nric':
                        value = mask_nric(value)
                    response += f"• {field_display}: {value}\n"
                
                return {
                    **state,
                    "agent_response": response,
                    "tool_result": tool_result,
                    "conversation_state": conv_state,
                    "next_node": "end",
                    "should_end": True
                }
            else:
                # Tool execution failed
                logger.error(f"[{LogCategory.ERROR}] ❌ Patient update failed: {tool_result.error}")
                
                # Phase 8: Handle 400 validation errors specially  
                if hasattr(tool_result, 'status_code') and tool_result.status_code == 400 and hasattr(tool_result, 'validation_errors'):
                    validation_errors = tool_result.validation_errors or {}
                    logger.info(f"[{LogCategory.ERROR}] 🔄 Repopulating pending fields from validation errors: {list(validation_errors.keys())}")
                    
                    # Keep patient ID but repopulate pending_fields for corrections
                    conv_state.pending_fields = set(validation_errors.keys())
                    # Clear invalid fields from validated_fields but keep patient ID
                    for field in validation_errors.keys():
                        conv_state.validated_fields.pop(field, None)
                    
                    # Generate field-specific error message
                    field_messages = []
                    for field, errors in validation_errors.items():
                        if isinstance(errors, list):
                            field_messages.append(f"• {field}: {', '.join(errors)}")
                        else:
                            field_messages.append(f"• {field}: {errors}")
                    
                    response = f"""❌ Please correct the following issues for patient {patient_id}:

{chr(10).join(field_messages)}

Please provide the corrected information."""
                    
                    # Route back to update_patient node for field collection
                    return {
                        **state,
                        "agent_response": response,
                        "tool_result": tool_result,
                        "conversation_state": conv_state,
                        "next_node": "update_patient",  # Route back for field correction
                        "should_end": False
                    }
                else:
                    # Generic error handling for non-validation failures
                    # Reset conversation state on failure
                    conv_state.pending_action = PendingAction.NONE
                    conv_state.validated_fields.clear()
                    conv_state.pending_fields.clear()
                    
                    return {
                        **state,
                        "agent_response": f"❌ Failed to update patient: {tool_result.error}",
                        "tool_result": tool_result,
                        "conversation_state": conv_state,
                        "next_node": "end",
                        "should_end": False
                    }
                
        except Exception as e:
            logger.error(f"[{LogCategory.ERROR}] ❌ Unexpected error during patient update: {e}")
            
            # Reset conversation state on error
            conv_state.pending_action = PendingAction.NONE
            conv_state.validated_fields.clear()
            conv_state.pending_fields.clear()
            
            return {
                **state,
                "agent_response": f"❌ An unexpected error occurred while updating the patient: {e}",
                "conversation_state": conv_state,
                "next_node": "end",
                "should_end": False
            }

    def delete_patient_node(self, state: GraphState) -> GraphState:
        """
        Node 9: Handle patient deletion workflow with confirmation guard.
        """
        conv_state = state["conversation_state"]
        extracted_fields = state["extracted_fields"]
        
        logger.info(f"[{LogCategory.FLOW}] 🗑️ Processing delete patient request")
        
        # Update conversation state for patient deletion
        conv_state.pending_action = PendingAction.DELETE_PATIENT
        
        # Check if patient_id was provided
        patient_id = extracted_fields.get('patient_id')
        if not patient_id:
            patient_id = conv_state.validated_fields.get('patient_id')
        
        if not patient_id:
            # No patient ID provided - ask for it
            response = "Please specify which patient you'd like to delete (e.g., 'delete patient 5' or 'remove patient 12')."
            return {
                **state,
                "agent_response": response,
                "conversation_state": conv_state,
                "next_node": "end",
                "should_end": False
            }
        
        # Store patient_id and set up confirmation
        conv_state.validated_fields['patient_id'] = patient_id
        conv_state.confirmation_required = True
        conv_state.awaiting_confirmation_type = ConfirmationType.DELETE
        
        # Generate confirmation prompt
        response = f"⚠️ **Confirmation Required**\n\n"
        response += f"Are you sure you want to **permanently delete** patient ID {patient_id}?\n\n"
        response += "This action cannot be undone. Please respond with:\n"
        response += "• **yes** or **confirm** to proceed\n"
        response += "• **no** or **cancel** to abort"
        
        logger.info(f"[{LogCategory.FLOW}] 🔄 Requesting delete confirmation for patient ID: {patient_id}")
        
        return {
            **state,
            "agent_response": response,
            "conversation_state": conv_state,
            "next_node": "end",
            "should_end": False
        }

    def execute_delete_patient_node(self, state: GraphState) -> GraphState:
        """
        Node 10: Execute patient deletion after confirmation.
        """
        conv_state = state["conversation_state"]
        patient_id = conv_state.validated_fields['patient_id']
        
        logger.info(f"[{LogCategory.TOOL}] 🔧 Executing patient deletion for ID: {patient_id}")
        
        try:
            # Execute patient deletion tool
            tool_result = self.tool_manager.execute_tool(
                Intent.DELETE_PATIENT,
                conv_state.metrics,
                patient_id=patient_id
            )
            
            if tool_result.success:
                # Success - patient deleted
                logger.info(f"[{LogCategory.SUCCESS}] ✅ Patient deleted successfully: ID {patient_id}")
                
                # Invalidate name cache
                self.name_cache.invalidate_on_crud_success("delete", patient_id)
                
                # Reset conversation state
                conv_state.pending_action = PendingAction.NONE
                conv_state.validated_fields.clear()
                conv_state.confirmation_required = False
                conv_state.awaiting_confirmation_type = ConfirmationType.NONE
                
                response = f"✅ Successfully deleted patient ID {patient_id}"
                
                return {
                    **state,
                    "agent_response": response,
                    "tool_result": tool_result,
                    "conversation_state": conv_state,
                    "next_node": "end",
                    "should_end": True
                }
            else:
                # Tool execution failed
                logger.error(f"[{LogCategory.ERROR}] ❌ Patient deletion failed: {tool_result.error}")
                
                # Reset conversation state on failure
                conv_state.pending_action = PendingAction.NONE
                conv_state.validated_fields.clear()
                conv_state.confirmation_required = False
                conv_state.awaiting_confirmation_type = ConfirmationType.NONE
                
                return {
                    **state,
                    "agent_response": f"❌ Failed to delete patient: {tool_result.error}",
                    "tool_result": tool_result,
                    "conversation_state": conv_state,
                    "next_node": "end",
                    "should_end": False
                }
                
        except Exception as e:
            logger.error(f"[{LogCategory.ERROR}] ❌ Unexpected error during patient deletion: {e}")
            
            # Reset conversation state on error
            conv_state.pending_action = PendingAction.NONE
            conv_state.validated_fields.clear()
            conv_state.confirmation_required = False
            conv_state.awaiting_confirmation_type = ConfirmationType.NONE
            
            return {
                **state,
                "agent_response": f"❌ An unexpected error occurred while deleting the patient: {e}",
                "conversation_state": conv_state,
                "next_node": "end",
                "should_end": False
            }

    def get_scan_results_node(self, state: GraphState) -> GraphState:
        """
        Node 11: Handle scan results retrieval with two-stage flow (preview first, then STL).
        """
        conv_state = state["conversation_state"]
        extracted_fields = state["extracted_fields"]
        
        logger.info(f"[{LogCategory.FLOW}] 🔬 Processing get scan results request")
        
        # Update conversation state for scan results
        conv_state.pending_action = PendingAction.GET_SCAN_RESULTS
        
        # Check if patient_id was provided
        patient_id = extracted_fields.get('patient_id')
        if not patient_id:
            patient_id = conv_state.validated_fields.get('patient_id')
        
        if not patient_id:
            # No patient ID provided - ask for it
            response = "Please specify which patient's scan results you'd like to see (e.g., 'show scans for patient 5')."
            return {
                **state,
                "agent_response": response,
                "conversation_state": conv_state,
                "next_node": "end",
                "should_end": False
            }
        
        try:
            # Execute scan results tool
            tool_result = self.tool_manager.execute_tool(
                Intent.GET_SCAN_RESULTS,
                conv_state.metrics,
                patient_id=patient_id,
                limit=conv_state.scan_display_limit
            )
            
            if tool_result.success and tool_result.data is not None:
                scan_results_data = tool_result.data
                
                # Ensure we have a list of scan results
                if isinstance(scan_results_data, dict):
                    # If it's a dict, it might be paginated response - try to get results array
                    scan_results = scan_results_data.get('results', [])
                elif isinstance(scan_results_data, list):
                    scan_results = scan_results_data
                else:
                    scan_results = []
                
                total_results = len(scan_results)
                
                # Store results in conversation state buffer
                conv_state.scan_results_buffer = scan_results
                conv_state.selected_patient_id = patient_id
                
                logger.info(f"[{LogCategory.SUCCESS}] ✅ Retrieved {total_results} scan results for patient ID: {patient_id}")
                
                if total_results == 0:
                    # No scan results found
                    response = f"📊 No scan results found for patient ID {patient_id}."
                    
                    # Reset state
                    conv_state.pending_action = PendingAction.NONE
                    
                    return {
                        **state,
                        "agent_response": response,
                        "tool_result": tool_result,
                        "conversation_state": conv_state,
                        "next_node": "end",
                        "should_end": True
                    }
                
                # Stage 1: Preview Mode (no STL links yet)
                display_count = min(total_results, conv_state.scan_display_limit)
                
                response = f"📊 **Scan Results for Patient ID {patient_id}** ({total_results} result(s)):\n\n"
                
                for i, result in enumerate(scan_results[:display_count]):
                    scan_id = result.get('scan_id', 'Unknown')
                    scan_date = result.get('scan_date', result.get('created_at', 'Unknown'))[:10]  # Take date part
                    
                    response += f"**{i+1}. Scan {scan_id}** ({scan_date})\n"
                    
                    # Show preview image if available
                    if result.get('preview_image'):
                        response += f"   📸 [Preview Image]({result['preview_image']})\n"
                    
                    # Show volume estimate if available
                    if result.get('volume_estimate'):
                        response += f"   📏 Volume: {result['volume_estimate']} mm³\n"
                    
                    response += "\n"
                
                # Pagination info
                if total_results > display_count:
                    remaining = total_results - display_count
                    response += f"*(Showing {display_count} of {total_results}. Say 'show more scans' to display {min(remaining, conv_state.scan_display_limit)} more.)*\n\n"
                    conv_state.scan_pagination_offset = display_count
                
                # Set up for Stage 2 (STL confirmation)
                conv_state.download_stage = DownloadStage.PREVIEW_SHOWN
                conv_state.confirmation_required = True
                conv_state.awaiting_confirmation_type = ConfirmationType.DOWNLOAD_STL
                
                response += "Would you like to download STL files for these scans? (yes/no)"
                
                return {
                    **state,
                    "agent_response": response,
                    "tool_result": tool_result,
                    "conversation_state": conv_state,
                    "next_node": "end",
                    "should_end": False
                }
            else:
                # Tool execution failed
                logger.error(f"[{LogCategory.ERROR}] ❌ Failed to get scan results: {tool_result.error}")
                
                # Reset state
                conv_state.pending_action = PendingAction.NONE
                
                # Phase 8: Enhanced 404 handling offering list option
                if (hasattr(tool_result, 'status_code') and tool_result.status_code == 404) or \
                   "404" in str(tool_result.error) or "not found" in str(tool_result.error).lower():
                    response = f"""❌ Patient ID {patient_id} not found: {tool_result.error}

💡 **Helpful options:**
• Say "list patients" to see all available patients  
• Provide a different patient ID for scan results
• Say "cancel" to start over

How would you like to proceed?"""
                else:
                    response = f"❌ Failed to get scan results: {tool_result.error}"
                
                return {
                    **state,
                    "agent_response": response,
                    "tool_result": tool_result,
                    "conversation_state": conv_state,
                    "next_node": "end",
                    "should_end": False
                }
                
        except Exception as e:
            logger.error(f"[{LogCategory.ERROR}] ❌ Unexpected error getting scan results: {e}")
            
            # Reset state
            conv_state.pending_action = PendingAction.NONE
            
            return {
                **state,
                "agent_response": f"❌ An unexpected error occurred while getting scan results: {e}",
                "conversation_state": conv_state,
                "next_node": "end",
                "should_end": False
            }

    def provide_stl_links_node(self, state: GraphState) -> GraphState:
        """
        Node 12: Provide STL download links after confirmation (Stage 2 of scan results flow).
        """
        conv_state = state["conversation_state"]
        
        logger.info(f"[{LogCategory.FLOW}] 📥 Providing STL download links")
        
        # Get scan results from buffer
        scan_results = conv_state.scan_results_buffer
        patient_id = conv_state.selected_patient_id
        
        if not scan_results:
            # No scan results in buffer - shouldn't happen
            logger.error(f"[{LogCategory.ERROR}] ❌ No scan results in buffer for STL links")
            
            # Reset state
            conv_state.pending_action = PendingAction.NONE
            conv_state.download_stage = DownloadStage.NONE
            conv_state.confirmation_required = False
            conv_state.awaiting_confirmation_type = ConfirmationType.NONE
            
            response = "❌ No scan results available for download. Please search for scans again."
            
            return {
                **state,
                "agent_response": response,
                "conversation_state": conv_state,
                "next_node": "end",
                "should_end": False
            }
        
        # Stage 2: Provide STL links for displayed results
        display_count = min(len(scan_results), conv_state.scan_pagination_offset or conv_state.scan_display_limit)
        
        response = f"📥 **STL Download Links for Patient ID {patient_id}:**\n\n"
        
        stl_count = 0
        for i, result in enumerate(scan_results[:display_count]):
            scan_id = result.get('scan_id', 'Unknown')
            scan_date = result.get('scan_date', result.get('created_at', 'Unknown'))[:10]
            
            if result.get('stl_file'):
                response += f"**{i+1}. Scan {scan_id}** ({scan_date})\n"
                response += f"   📁 [Download STL File]({result['stl_file']})\n\n"
                stl_count += 1
            else:
                response += f"**{i+1}. Scan {scan_id}** ({scan_date})\n"
                response += f"   ⚠️ No STL file available\n\n"
        
        if stl_count == 0:
            response += "⚠️ No STL files are available for download from these scan results."
        else:
            response += f"✅ {stl_count} STL file(s) ready for download."
        
        # Update state to STL_LINKS_SENT
        conv_state.download_stage = DownloadStage.STL_LINKS_SENT
        conv_state.confirmation_required = False
        conv_state.awaiting_confirmation_type = ConfirmationType.NONE
        
        # Keep results in buffer in case user wants to see more
        # Don't reset pending_action yet in case of pagination
        
        logger.info(f"[{LogCategory.SUCCESS}] ✅ Provided {stl_count} STL download links")
        
        return {
            **state,
            "agent_response": response,
            "conversation_state": conv_state,
            "next_node": "end",
            "should_end": True
        }

    def show_more_scans_node(self, state: GraphState) -> GraphState:
        """
        Phase 9 Node: Handle pagination for scan results ("show more scans").
        """
        conv_state = state["conversation_state"]
        
        logger.info(f"[{LogCategory.FLOW}] 📄 Processing show more scans request")
        
        # Get scan results from buffer
        scan_results = conv_state.scan_results_buffer
        patient_id = conv_state.selected_patient_id
        
        if not scan_results:
            logger.error(f"[{LogCategory.ERROR}] ❌ No scan results in buffer for pagination")
            response = "❌ No scan results available to show more. Please search for scans first."
            
            return {
                **state,
                "agent_response": response,
                "conversation_state": conv_state,
                "next_node": "end",
                "should_end": False
            }
        
        # Calculate pagination
        current_offset = conv_state.scan_pagination_offset
        total_results = len(scan_results)
        display_limit = conv_state.scan_display_limit
        
        # Check if there are more results to show
        if current_offset >= total_results:
            response = f"📊 All {total_results} scan results have been displayed for patient ID {patient_id}."
            
            return {
                **state,
                "agent_response": response,
                "conversation_state": conv_state,
                "next_node": "end",
                "should_end": True
            }
        
        # Calculate what to show next
        end_index = min(current_offset + display_limit, total_results)
        next_batch = scan_results[current_offset:end_index]
        
        logger.info(f"[{LogCategory.FLOW}] 📄 Showing results {current_offset+1}-{end_index} of {total_results}")
        
        # Format additional results
        response = f"📊 **More Scan Results for Patient ID {patient_id}** (showing {current_offset+1}-{end_index} of {total_results}):\n\n"
        
        for i, result in enumerate(next_batch):
            scan_id = result.get('scan_id', 'Unknown')
            scan_date = result.get('scan_date', result.get('created_at', 'Unknown'))[:10]
            
            # Use absolute numbering (not relative to batch)
            result_num = current_offset + i + 1
            response += f"**{result_num}. Scan {scan_id}** ({scan_date})\n"
            
            # Show preview image if available 
            if result.get('preview_image'):
                response += f"   📸 [Preview Image]({result['preview_image']})\n"
            
            # Show volume estimate if available
            if result.get('volume_estimate'):
                response += f"   📏 Volume: {result['volume_estimate']} mm³\n"
            
            response += "\n"
        
        # Update pagination offset
        conv_state.scan_pagination_offset = end_index
        
        # Check if there are more results available
        remaining = total_results - end_index
        if remaining > 0:
            response += f"*(Say 'show more scans' to display {min(remaining, display_limit)} more results.)*\n\n"
        else:
            response += "*All scan results have been displayed.*\n\n"
        
        # Phase 9: Two-stage flow - ask for STL download confirmation for these additional results
        # But only if we haven't already sent STL links
        if conv_state.download_stage == DownloadStage.PREVIEW_SHOWN:
            response += "Would you like to download STL files for these additional scans? (yes/no)"
            conv_state.confirmation_required = True
            conv_state.awaiting_confirmation_type = ConfirmationType.DOWNLOAD_STL
        elif conv_state.download_stage == DownloadStage.STL_LINKS_SENT:
            response += "Would you like STL download links for these additional scans? (yes/no)"
            conv_state.confirmation_required = True
            conv_state.awaiting_confirmation_type = ConfirmationType.DOWNLOAD_STL
            # Reset download stage to allow new STL links
            conv_state.download_stage = DownloadStage.PREVIEW_SHOWN
        
        return {
            **state,
            "agent_response": response,
            "conversation_state": conv_state,
            "next_node": "end",
            "should_end": False
        }

    def provide_depth_maps_node(self, state: GraphState) -> GraphState:
        """
        Phase 9 Node: Provide depth map information for scan results.
        """
        conv_state = state["conversation_state"]
        
        logger.info(f"[{LogCategory.FLOW}] 🗺️ Processing depth map request")
        
        # Get scan results from buffer
        scan_results = conv_state.scan_results_buffer
        patient_id = conv_state.selected_patient_id
        
        if not scan_results:
            logger.error(f"[{LogCategory.ERROR}] ❌ No scan results in buffer for depth maps")
            response = "❌ No scan results available for depth map display. Please search for scans first."
            
            return {
                **state,
                "agent_response": response,
                "conversation_state": conv_state,
                "next_node": "end",
                "should_end": False
            }
        
        # Get currently displayed results based on pagination offset
        current_offset = conv_state.scan_pagination_offset or conv_state.scan_display_limit
        displayed_results = scan_results[:current_offset]
        
        logger.info(f"[{LogCategory.FLOW}] 🗺️ Providing depth maps for {len(displayed_results)} results")
        
        # Format depth map information
        response = f"🗺️ **Depth Map Information for Patient ID {patient_id}:**\n\n"
        
        depth_count = 0
        for i, result in enumerate(displayed_results):
            scan_id = result.get('scan_id', 'Unknown')
            scan_date = result.get('scan_date', result.get('created_at', 'Unknown'))[:10]
            
            response += f"**{i+1}. Scan {scan_id}** ({scan_date})\n"
            
            # Show depth map links if available
            if result.get('depth_map_8bit'):
                response += f"   🗺️ [8-bit Depth Map]({result['depth_map_8bit']})\n"
                depth_count += 1
                
            if result.get('depth_map_16bit'):
                response += f"   🗺️ [16-bit Depth Map]({result['depth_map_16bit']})\n"
                depth_count += 1
            
            if not result.get('depth_map_8bit') and not result.get('depth_map_16bit'):
                response += f"   ⚠️ No depth maps available\n"
            
            response += "\n"
        
        if depth_count == 0:
            response += "⚠️ No depth maps are available for these scan results."
        else:
            response += f"✅ {depth_count} depth map(s) available for download."
        
        logger.info(f"[{LogCategory.SUCCESS}] ✅ Provided {depth_count} depth map links")
        
        return {
            **state,
            "agent_response": response,
            "conversation_state": conv_state,
            "next_node": "end",
            "should_end": True
        }

    def provide_agent_stats_node(self, state: GraphState) -> GraphState:
        """
        Phase 10 Node: Provide comprehensive agent statistics and metrics.
        """
        conv_state = state["conversation_state"]
        
        logger.info(f"[{LogCategory.FLOW}] 📊 Processing agent stats request")
        
        try:
            # Generate comprehensive statistics using agent_stats
            stats_data = agent_stats.generate_stats_summary(conv_state)
            
            # Format for user display
            response = agent_stats.format_stats_for_user(stats_data)
            
            # Log metrics summary for debugging
            metrics_logger.log_metrics_summary(conv_state.metrics)
            
            logger.info(f"[{LogCategory.SUCCESS}] ✅ Agent statistics provided")
            
            return {
                **state,
                "agent_response": response,
                "conversation_state": conv_state,
                "next_node": "end",
                "should_end": True
            }
            
        except Exception as e:
            logger.error(f"[{LogCategory.ERROR}] ❌ Error generating agent stats: {e}")
            
            # Fallback response with basic metrics
            metrics = conv_state.metrics
            basic_response = f"""📊 **Basic Agent Statistics**
            
**Operations Summary:**
• Total Operations: {metrics.get('successful_ops', 0) + metrics.get('aborted_ops', 0)}
• Successful: {metrics.get('successful_ops', 0)}
• Failed: {metrics.get('aborted_ops', 0)}
• Retry Attempts: {metrics.get('retries', 0)}

⚠️ Detailed statistics temporarily unavailable. Basic metrics shown above."""

            return {
                **state,
                "agent_response": basic_response,
                "conversation_state": conv_state,
                "next_node": "end",
                "should_end": True
            }

    def handle_confirmation_node(self, state: GraphState) -> GraphState:
        """
        Node 13: Handle user confirmations for various workflows.
        """
        conv_state = state["conversation_state"]
        user_message = state["user_message"].lower().strip()
        
        logger.info(f"[{LogCategory.FLOW}] 🔄 Processing confirmation: '{user_message}'")
        
        if not conv_state.confirmation_required:
            # No confirmation pending - shouldn't reach this node
            logger.warning(f"[{LogCategory.FLOW}] ⚠️ Confirmation handler called but no confirmation required")
            return self.unknown_intent_node(state)
        
        # Check confirmation type and user response
        confirmation_type = conv_state.awaiting_confirmation_type
        
        # Parse user response - use word boundaries for more precise matching
        affirmative_patterns = [r'\byes\b', r'\by\b', r'\bconfirm\b', r'\bproceed\b', r'\bok\b', r'\bokay\b']
        negative_patterns = [r'\bno\b', r'\bn\b', r'\bcancel\b', r'\babort\b', r'\bstop\b']
        
        import re
        is_affirmative = any(re.search(pattern, user_message, re.IGNORECASE) for pattern in affirmative_patterns)
        is_negative = any(re.search(pattern, user_message, re.IGNORECASE) for pattern in negative_patterns)
        
        if confirmation_type == ConfirmationType.DELETE:
            if is_affirmative:
                logger.info(f"[{LogCategory.FLOW}] ✅ Delete confirmation received")
                # Proceed with deletion
                return {
                    **state,
                    "conversation_state": conv_state,
                    "next_node": "execute_delete_patient"
                }
            elif is_negative:
                logger.info(f"[{LogCategory.FLOW}] ❌ Delete confirmation denied")
                # Cancel deletion
                conv_state.pending_action = PendingAction.NONE
                conv_state.validated_fields.clear()
                conv_state.confirmation_required = False
                conv_state.awaiting_confirmation_type = ConfirmationType.NONE
                
                response = "❌ Patient deletion cancelled. No changes were made."
                
                return {
                    **state,
                    "agent_response": response,
                    "conversation_state": conv_state,
                    "next_node": "end",
                    "should_end": True
                }
        
        elif confirmation_type == ConfirmationType.DOWNLOAD_STL:
            if is_affirmative:
                logger.info(f"[{LogCategory.FLOW}] ✅ STL download confirmation received")
                # Proceed with STL links
                return {
                    **state,
                    "conversation_state": conv_state,
                    "next_node": "provide_stl_links"
                }
            elif is_negative:
                logger.info(f"[{LogCategory.FLOW}] ❌ STL download confirmation denied")
                # End scan results flow without STL links
                conv_state.pending_action = PendingAction.NONE
                conv_state.download_stage = DownloadStage.NONE
                conv_state.confirmation_required = False
                conv_state.awaiting_confirmation_type = ConfirmationType.NONE
                conv_state.scan_results_buffer.clear()
                
                response = "👍 Scan results displayed without download links. Is there anything else I can help you with?"
                
                return {
                    **state,
                    "agent_response": response,
                    "conversation_state": conv_state,
                    "next_node": "end",
                    "should_end": True
                }
        
        # Ambiguous or unrecognized response
        logger.warning(f"[{LogCategory.FLOW}] ⚠️ Ambiguous confirmation response: '{user_message}'")
        
        # Re-prompt for clear confirmation
        if confirmation_type == ConfirmationType.DELETE:
            patient_id = conv_state.validated_fields.get('patient_id')
            response = f"⚠️ Please respond clearly:\n\n"
            response += f"Delete patient ID {patient_id}?\n"
            response += "• Type **yes** to proceed\n"
            response += "• Type **no** to cancel"
        elif confirmation_type == ConfirmationType.DOWNLOAD_STL:
            response = f"⚠️ Please respond clearly:\n\n"
            response += f"Download STL files?\n"
            response += "• Type **yes** to get download links\n"
            response += "• Type **no** to skip downloads"
        else:
            response = "⚠️ Please respond with **yes** or **no**."
        
        return {
            **state,
            "agent_response": response,
            "conversation_state": conv_state,
            "next_node": "end",
            "should_end": False
        }

    def unknown_intent_node(self, state: GraphState) -> GraphState:
        """
        Node 14: Handle unknown or unsupported intents.
        """
        conv_state = state["conversation_state"]
        user_message = state["user_message"]
        
        logger.info(f"[{LogCategory.INTENT}] ❓ Handling unknown intent for: '{user_message[:50]}...'")
        
        # Generate helpful response with all available capabilities
        response = """❓ I'm not sure what you'd like me to do. I can help you with:

• **Create a patient** - "create patient John Doe with NRIC S1234567A"
• **List patients** - "show all patients" or "list patients"
• **Get patient details** - "show patient 5" or "get details for patient 12"
• **Update a patient** - "update patient 5 contact 91234567"
• **Delete a patient** - "delete patient 5" (requires confirmation)
• **View scan results** - "show scans for patient 5"

Please let me know how I can assist you with patient management."""
        
        return {
            **state,
            "agent_response": response,
            "conversation_state": conv_state,
            "next_node": "end",
            "should_end": False
        }

    def ingest_user_message_node(self, state: GraphState) -> GraphState:
        """
        Node 1: Ingest and preprocess user message (Phase 15).
        
        Message preprocessing, validation, sanitization before classification.
        Entry point for all conversation flows per §24.1.
        """
        user_message = state["user_message"]
        conv_state = state["conversation_state"]
        
        logger.info(f"[{LogCategory.FLOW}] 📝 Ingesting user message: '{user_message[:50]}...'")
        
        # Input validation and sanitization
        if not user_message or not user_message.strip():
            logger.warning(f"[{LogCategory.ERROR}] ⚠️ Empty or whitespace-only message")
            return {
                **state,
                "agent_response": "Please provide a message. How can I help you with patient management?",
                "conversation_state": conv_state,
                "next_node": "end",
                "should_end": False
            }
        
        # Length validation (prevent token abuse per §26)
        MAX_MESSAGE_LENGTH = 2000  # Reasonable limit for patient management tasks
        if len(user_message) > MAX_MESSAGE_LENGTH:
            logger.warning(f"[{LogCategory.ERROR}] ⚠️ Message too long: {len(user_message)} chars")
            return {
                **state,
                "agent_response": f"Message too long ({len(user_message)} characters). Please keep messages under {MAX_MESSAGE_LENGTH} characters.",
                "conversation_state": conv_state,
                "next_node": "end", 
                "should_end": False
            }
        
        # Basic sanitization for security (prevent obvious injection attempts)
        sanitized_message = user_message.strip()
        
        # Check for malicious patterns per security requirements
        suspicious_patterns = [
            r'<script.*?</script>',
            r'javascript:',
            r'data:text/html',
            r'eval\s*\(',
            r'exec\s*\('
        ]
        
        import re
        for pattern in suspicious_patterns:
            if re.search(pattern, sanitized_message, re.IGNORECASE):
                logger.warning(f"[{LogCategory.ERROR}] ⚠️ Suspicious pattern detected, sanitizing input")
                # Don't reject entirely, just sanitize - this is a medical application
                sanitized_message = re.sub(pattern, '[sanitized]', sanitized_message, flags=re.IGNORECASE)
        
        # Update state with sanitized message
        state["user_message"] = sanitized_message
        
        # Check for cancellation early (per §28)
        cancellation_patterns = [r'\bcancel\b', r'\babort\b', r'\bstop\b', r'\breset\b']
        is_cancellation = any(re.search(pattern, sanitized_message, re.IGNORECASE) for pattern in cancellation_patterns)
        
        if is_cancellation:
            logger.info(f"[{LogCategory.INTENT}] 🛑 Cancellation detected in message")
            return {
                **state,
                "conversation_state": conv_state,
                "next_node": "handle_cancellation"
            }
        
        # Successful ingestion - proceed to intent classification
        logger.info(f"[{LogCategory.FLOW}] ✅ Message ingested successfully")
        
        return {
            **state,
            "conversation_state": conv_state,
            "next_node": "classify_intent"
        }

    def summarize_history_node(self, state: GraphState) -> GraphState:
        """
        Node 15: Summarize conversation history when >5 turns (Phase 15).
        
        Uses Gemini API to create coherent conversation history per §27.
        Triggered when recent_messages reaches capacity (5 items).
        """
        conv_state = state["conversation_state"]
        
        logger.info(f"[{LogCategory.FLOW}] 📚 Processing history summarization")
        
        # Check if summarization is needed
        if len(conv_state.recent_messages) < 5:
            logger.debug(f"[{LogCategory.FLOW}] History too short ({len(conv_state.recent_messages)} messages), skipping summarization")
            return {
                **state,
                "conversation_state": conv_state,
                "next_node": "finalize_response"
            }
        
        try:
            # Import Gemini client for summarization
            import json
            from .gemini_client import GeminiClient
            
            # Initialize client
            gemini_client = GeminiClient()
            
            # Check if API key is available
            if not gemini_client.api_key:
                logger.warning(f"[{LogCategory.FLOW}] Gemini API key not available, skipping LLM summarization")
                self._create_fallback_summary(conv_state)
                return {
                    **state,
                    "conversation_state": conv_state,
                    "next_node": "finalize_response"
                }
            
            # Prepare conversation history for summarization
            conversation_text = "\n".join([
                f"Turn {i+1}: {msg}" for i, msg in enumerate(conv_state.recent_messages)
            ])
            
            # Build summarization prompt per §27 requirements
            summarization_prompt = f"""Summarize this patient management conversation history into structured JSON format:

Conversation:
{conversation_text}

Return JSON with these fields:
- salient_patients: array of patient IDs mentioned or worked with
- pending_action: current incomplete action (CREATE_PATIENT, UPDATE_PATIENT, etc. or NONE)
- unresolved_fields: any missing patient fields still needed
- last_result: brief description of the most recent successful operation or current state

Keep summary concise and factual. Focus on patient management context only."""
            
            # Generate summary using Gemini
            import asyncio
            loop = asyncio.get_event_loop()
            
            async def get_summary():
                try:
                    api_response = await gemini_client._call_gemini_api(summarization_prompt)
                    
                    # Extract text content from Gemini API response
                    if 'candidates' in api_response and api_response['candidates']:
                        candidate = api_response['candidates'][0]
                        if 'content' in candidate and 'parts' in candidate['content']:
                            parts = candidate['content']['parts']
                            if parts and 'text' in parts[0]:
                                return parts[0]['text']
                    
                    logger.warning(f"[{LogCategory.FLOW}] Unexpected API response format")
                    return None
                    
                except Exception as e:
                    logger.warning(f"[{LogCategory.FLOW}] Gemini summarization failed: {e}")
                    return None
            
            if loop.is_running():
                # Use thread pool executor for proper async handling
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    try:
                        future = executor.submit(asyncio.run, get_summary())
                        summary_response = future.result(timeout=10)
                    except Exception as e:
                        logger.warning(f"[{LogCategory.FLOW}] Async summary execution failed: {e}")
                        summary_response = None
            else:
                summary_response = loop.run_until_complete(get_summary())
            
            if summary_response:
                # Parse and validate summary
                try:
                    summary_data = json.loads(summary_response.strip())
                    
                    # Validate required fields
                    required_fields = ['salient_patients', 'pending_action', 'unresolved_fields', 'last_result']
                    if all(field in summary_data for field in required_fields):
                        # Update history_summary with structured data
                        conv_state.history_summary = json.dumps(summary_data)
                        
                        # Keep only the most recent message in the rolling window 
                        # to make room for new messages while preserving immediate context
                        if conv_state.recent_messages:
                            last_message = conv_state.recent_messages[-1]
                            conv_state.recent_messages.clear()
                            conv_state.recent_messages.append(last_message)
                        
                        logger.info(f"[{LogCategory.FLOW}] ✅ History summarized successfully")
                        logger.debug(f"[{LogCategory.FLOW}] Summary: salient_patients={summary_data.get('salient_patients', [])}, pending_action={summary_data.get('pending_action', 'NONE')}")
                    else:
                        logger.warning(f"[{LogCategory.FLOW}] Summary missing required fields, using fallback")
                        self._create_fallback_summary(conv_state)
                        
                except json.JSONDecodeError as e:
                    logger.warning(f"[{LogCategory.FLOW}] Failed to parse summary JSON: {e}, using fallback")
                    self._create_fallback_summary(conv_state)
                    
            else:
                # Fallback summarization without LLM
                logger.info(f"[{LogCategory.FLOW}] Using fallback summarization")
                self._create_fallback_summary(conv_state)
                
        except Exception as e:
            logger.error(f"[{LogCategory.ERROR}] ❌ History summarization failed: {e}")
            # Continue without summarization - not critical for functionality
        
        return {
            **state,
            "conversation_state": conv_state,
            "next_node": "finalize_response"
        }

    def _create_fallback_summary(self, conv_state: ConversationState) -> None:
        """Create simple fallback summary when Gemini is unavailable."""
        import json
        
        # Simple structured fallback
        fallback_summary = {
            "salient_patients": [conv_state.selected_patient_id] if conv_state.selected_patient_id else [],
            "pending_action": conv_state.pending_action.name if conv_state.pending_action != PendingAction.NONE else "NONE",
            "unresolved_fields": list(conv_state.pending_fields),
            "last_result": f"Last intent: {conv_state.intent.name}" if conv_state.intent != Intent.UNKNOWN else "No recent activity"
        }
        
        conv_state.history_summary = json.dumps(fallback_summary)
        
        # Keep last 2 messages for minimal context
        if len(conv_state.recent_messages) > 2:
            recent = list(conv_state.recent_messages)[-2:]
            conv_state.recent_messages.clear()
            for msg in recent:
                conv_state.recent_messages.append(msg)

    def finalize_response_node(self, state: GraphState) -> GraphState:
        """
        Node 16: Final response formatting and PII masking validation (Phase 15).
        
        Consistent response formatting per §25 and final PII masking validation.
        Exit point for all conversation flows per §24.1.
        """
        conv_state = state["conversation_state"]
        agent_response = state.get("agent_response", "")
        
        logger.info(f"[{LogCategory.FLOW}] 🎯 Finalizing response")
        
        if not agent_response:
            logger.warning(f"[{LogCategory.ERROR}] ⚠️ No agent response to finalize")
            agent_response = "I apologize, but I couldn't process your request. Please try again."
        
        # Apply response templates per §25 for consistent formatting
        finalized_response = self._apply_response_templates(agent_response, state)
        
        # Final PII masking validation - ensure no unmasked NRICs leak through
        finalized_response = self._enforce_pii_masking(finalized_response, conv_state)
        
        # Add conversation context if available
        finalized_response = self._add_contextual_footer(finalized_response, conv_state)
        
        # Log final response (with PII masked for logs)
        logged_response = self._mask_for_logging(finalized_response)
        logger.info(f"[{LogCategory.SUCCESS}] ✅ Response finalized: '{logged_response[:100]}...'")
        
        return {
            **state,
            "agent_response": finalized_response,
            "conversation_state": conv_state,
            "next_node": "end",
            "should_end": True
        }

    def _apply_response_templates(self, response: str, state: GraphState) -> str:
        """Apply consistent response templates per §25."""
        conv_state = state["conversation_state"]
        tool_result = state.get("tool_result")
        
        # Handle DELETE_PATIENT template separately (no data expected)
        if tool_result and tool_result.success and conv_state.intent == Intent.DELETE_PATIENT:
            patient_id = conv_state.validated_fields.get('patient_id', 'Unknown')
            return f"✅ Deleted patient #{patient_id}."
        
        # If we have a tool result and it was successful, apply template formatting
        if tool_result and tool_result.success and tool_result.data:
            intent = conv_state.intent
            
            if intent == Intent.CREATE_PATIENT and isinstance(tool_result.data, dict):
                # Patient Creation Success template per §25
                patient_data = tool_result.data
                patient_id = patient_data.get('id', 'Unknown')
                first_name = patient_data.get('first_name', '')
                last_name = patient_data.get('last_name', '')
                nric = patient_data.get('nric', '')
                
                template_response = f"✅ Created patient #{patient_id}: {first_name} {last_name} (NRIC {mask_nric(nric)})."
                
                # Add optional fields if provided
                optional_parts = []
                if patient_data.get('date_of_birth'):
                    optional_parts.append(f"DOB: {patient_data['date_of_birth']}")
                if patient_data.get('contact_no'):
                    optional_parts.append(f"Contact: {patient_data['contact_no']}")
                if patient_data.get('details'):
                    optional_parts.append(f"Details: {patient_data['details']}")
                
                if optional_parts:
                    template_response += f"\n{', '.join(optional_parts)}"
                
                return template_response
                
            elif intent == Intent.UPDATE_PATIENT and isinstance(tool_result.data, dict):
                # Patient Update Success template per §25  
                patient_data = tool_result.data
                patient_id = patient_data.get('id', conv_state.validated_fields.get('patient_id', 'Unknown'))
                
                # Determine what fields were updated
                updated_fields = [k for k in conv_state.validated_fields.keys() 
                                if k != 'patient_id' and conv_state.validated_fields[k] is not None]
                
                field_list = ', '.join([field.replace('_', ' ').title() for field in updated_fields])
                
                return f"✅ Updated patient #{patient_id}: changed {field_list}."
        
        # Return original response if no template applies
        return response

    def _enforce_pii_masking(self, response: str, conv_state: ConversationState) -> str:
        """Enforce PII masking rules - ensure no unmasked NRICs appear."""
        import re
        
        # Pattern for Singapore NRIC
        nric_pattern = r'\b[STFG]\d{7}[A-Z]\b'
        
        # Find all potential NRICs in the response
        found_nrics = re.findall(nric_pattern, response)
        
        if found_nrics:
            logger.warning(f"[{LogCategory.ERROR}] ⚠️ Found {len(found_nrics)} unmasked NRICs in response")
            
            # Replace with masked versions
            for nric in found_nrics:
                masked = mask_nric(nric)
                response = response.replace(nric, masked)
                logger.info(f"[{LogCategory.FLOW}] Masked NRIC {nric[:1]}***{nric[-1:]} -> {masked}")
        
        return response

    def _add_contextual_footer(self, response: str, conv_state: ConversationState) -> str:
        """Add helpful contextual information to response when appropriate."""
        # Add guidance for pending workflows
        if conv_state.pending_action != PendingAction.NONE and not conv_state.confirmation_required:
            footer = "\n\nℹ️ *You can say 'cancel' at any time to reset.*"
            if footer not in response:
                response += footer
        
        return response

    def _mask_for_logging(self, text: str) -> str:
        """Mask any PII in text before logging."""
        import re
        
        # Mask any NRICs that might appear
        nric_pattern = r'\b[STFG]\d{7}[A-Z]\b'
        masked_text = re.sub(nric_pattern, lambda m: mask_nric(m.group()), text)
        
        return masked_text

    def handle_cancellation_node(self, state: GraphState) -> GraphState:
        """
        Node: Handle user cancellation/reset commands.
        Phase 8: Cancellation command handling.
        """
        conv_state = state["conversation_state"]
        user_message = state["user_message"]
        
        logger.info(f"[{LogCategory.INTENT}] 🛑 Handling cancellation request")
        
        # Check if there was an active workflow to cancel
        had_active_workflow = (
            conv_state.pending_action != PendingAction.NONE or
            conv_state.confirmation_required or
            len(conv_state.pending_fields) > 0 or
            conv_state.clarification_loop_count > 0
        )
        
        # Reset conversation state
        conv_state.reset_for_cancellation()
        
        # Generate appropriate response
        if had_active_workflow:
            response = "✅ Current operation cancelled. Your conversation has been reset. How can I help you with patient management?"
            logger.info(f"[{LogCategory.SUCCESS}] ✅ Active workflow cancelled and state reset")
        else:
            response = "ℹ️ No active operation to cancel. How can I help you with patient management?"
            logger.info(f"[{LogCategory.INTENT}] ℹ️ No active workflow found to cancel")
        
        # Increment metrics for cancelled operations
        if had_active_workflow:
            conv_state.metrics['aborted_ops'] += 1
        
        return {
            **state,
            "agent_response": response,
            "conversation_state": conv_state,
            "should_end": False,  # Conversation continues after cancellation
            "next_node": "finalize_response"  # Route to finalization
        }

    def _determine_next_node_from_intent(self, intent: Intent) -> str:
        """Determine the next node based on classified intent."""
        intent_routing = {
            Intent.CREATE_PATIENT: "create_patient",
            Intent.UPDATE_PATIENT: "update_patient", 
            Intent.DELETE_PATIENT: "delete_patient",
            Intent.LIST_PATIENTS: "list_patients",
            Intent.GET_PATIENT_DETAILS: "get_patient_details",
            Intent.GET_SCAN_RESULTS: "get_scan_results",
            Intent.CANCEL: "handle_cancellation",  # Phase 8: Cancellation handling
            Intent.UNKNOWN: "unknown_intent"
        }
        
        next_node = intent_routing.get(intent, "unknown_intent")
        logger.debug(f"[{LogCategory.FLOW}] Intent {intent.value} -> Node {next_node}")
        
        return next_node


# ===== MAIN CONVERSATION GRAPH =====

class ConversationGraph:
    """
    Main conversation graph orchestrator using LangGraph.
    
    Implements a subset of nodes (1-12) to support:
    - Create patient workflow with missing field prompts
    - List patients workflow
    """
    
    def __init__(self, http_client: HttpClient):
        self.http_client = http_client
        self.tool_manager = ToolManager(http_client)
        self.name_cache = NameResolutionCache(http_client)
        self.nodes = ConversationGraphNodes(self.tool_manager, self.name_cache)
        
        # Build the graph
        self.graph = self._build_graph()
        
        logger.info("[GRAPH] 🕸️ Conversation graph initialized")

    def _build_graph(self):
        """Build and configure the conversation graph with all 16 nodes per Phase 15."""
        
        # Create state graph
        workflow = StateGraph(GraphState)
        
        # Add all nodes (Phase 15: Complete 16-node implementation)
        workflow.add_node("ingest_user_message", self.nodes.ingest_user_message_node)      # Node 1
        workflow.add_node("classify_intent", self.nodes.classify_intent_node)               # Node 2
        workflow.add_node("create_patient", self.nodes.create_patient_node)
        workflow.add_node("execute_create_patient", self.nodes.execute_create_patient_node)
        workflow.add_node("update_patient", self.nodes.update_patient_node)
        workflow.add_node("execute_update_patient", self.nodes.execute_update_patient_node)
        workflow.add_node("delete_patient", self.nodes.delete_patient_node)
        workflow.add_node("execute_delete_patient", self.nodes.execute_delete_patient_node)
        workflow.add_node("list_patients", self.nodes.list_patients_node)
        workflow.add_node("get_patient_details", self.nodes.get_patient_details_node)
        workflow.add_node("get_scan_results", self.nodes.get_scan_results_node)
        workflow.add_node("provide_stl_links", self.nodes.provide_stl_links_node)
        workflow.add_node("show_more_scans", self.nodes.show_more_scans_node)               # Phase 9: Pagination
        workflow.add_node("provide_depth_maps", self.nodes.provide_depth_maps_node)        # Phase 9: Depth maps
        workflow.add_node("provide_agent_stats", self.nodes.provide_agent_stats_node)      # Phase 10: Agent statistics
        workflow.add_node("handle_confirmation", self.nodes.handle_confirmation_node)
        workflow.add_node("unknown_intent", self.nodes.unknown_intent_node)
        workflow.add_node("handle_cancellation", self.nodes.handle_cancellation_node)
        workflow.add_node("summarize_history", self.nodes.summarize_history_node)          # Node 15: Phase 15
        workflow.add_node("finalize_response", self.nodes.finalize_response_node)          # Node 16: Phase 15
        
        # Set entry point - all conversations start with message ingestion (Phase 15)
        workflow.set_entry_point("ingest_user_message")
        
        # Phase 15: New routing from ingest_user_message
        workflow.add_conditional_edges(
            "ingest_user_message",
            self._route_from_ingest_message,
            {
                "classify_intent": "classify_intent",
                "handle_cancellation": "handle_cancellation",
                "end": END
            }
        )
        
        # Add conditional routing from classify_intent
        workflow.add_conditional_edges(
            "classify_intent",
            self._route_from_classify_intent,
            {
                "create_patient": "create_patient",
                "update_patient": "update_patient",
                "delete_patient": "delete_patient", 
                "list_patients": "list_patients",
                "get_patient_details": "get_patient_details",
                "get_scan_results": "get_scan_results",
                "show_more_scans": "show_more_scans",  # Phase 9: Pagination routing
                "provide_depth_maps": "provide_depth_maps",  # Phase 9: Depth map routing
                "provide_agent_stats": "provide_agent_stats",  # Phase 10: Agent stats routing
                "handle_confirmation": "handle_confirmation",
                "handle_cancellation": "handle_cancellation",
                "unknown_intent": "unknown_intent"
            }
        )
        
        # Add conditional routing from create_patient
        workflow.add_conditional_edges(
            "create_patient",
            self._route_from_create_patient,
            {
                "execute_create_patient": "execute_create_patient",
                "finalize_response": "finalize_response"  # Phase 15: Route to finalization
            }
        )
        
        # Add conditional routing from update_patient  
        workflow.add_conditional_edges(
            "update_patient",
            self._route_from_update_patient,
            {
                "execute_update_patient": "execute_update_patient",
                "finalize_response": "finalize_response"  # Phase 15: Route to finalization
            }
        )
        
        # Add conditional routing from delete_patient (goes to confirmation or finalization)
        workflow.add_conditional_edges(
            "delete_patient", 
            self._route_from_delete_patient,
            {
                "finalize_response": "finalize_response"  # Phase 15: Route to finalization
            }
        )
        
        # Add conditional routing from handle_confirmation
        workflow.add_conditional_edges(
            "handle_confirmation",
            self._route_from_confirmation,
            {
                "execute_delete_patient": "execute_delete_patient",
                "provide_stl_links": "provide_stl_links",
                "finalize_response": "finalize_response"  # Phase 15: Route to finalization
            }
        )
        
        # Phase 15: All execution and terminal nodes check for summarization need then finalize
        workflow.add_conditional_edges(
            "execute_create_patient",
            self._route_to_summarization_check,
            {
                "summarize_history": "summarize_history",
                "finalize_response": "finalize_response"
            }
        )
        
        workflow.add_conditional_edges(
            "execute_update_patient", 
            self._route_to_summarization_check,
            {
                "summarize_history": "summarize_history",
                "finalize_response": "finalize_response"
            }
        )
        
        workflow.add_conditional_edges(
            "execute_delete_patient",
            self._route_to_summarization_check,
            {
                "summarize_history": "summarize_history", 
                "finalize_response": "finalize_response"
            }
        )
        
        workflow.add_conditional_edges(
            "list_patients",
            self._route_to_summarization_check,
            {
                "summarize_history": "summarize_history",
                "finalize_response": "finalize_response"
            }
        )
        
        workflow.add_conditional_edges(
            "get_patient_details",
            self._route_to_summarization_check,
            {
                "summarize_history": "summarize_history",
                "finalize_response": "finalize_response"
            }
        )
        
        workflow.add_conditional_edges(
            "get_scan_results",
            self._route_to_summarization_check,
            {
                "summarize_history": "summarize_history",
                "finalize_response": "finalize_response"
            }
        )
        
        workflow.add_conditional_edges(
            "provide_stl_links",
            self._route_to_summarization_check,
            {
                "summarize_history": "summarize_history",
                "finalize_response": "finalize_response"
            }
        )
        
        workflow.add_conditional_edges(
            "show_more_scans",
            self._route_to_summarization_check,
            {
                "summarize_history": "summarize_history", 
                "finalize_response": "finalize_response"
            }
        )
        
        workflow.add_conditional_edges(
            "provide_depth_maps",
            self._route_to_summarization_check,
            {
                "summarize_history": "summarize_history",
                "finalize_response": "finalize_response"
            }
        )
        
        workflow.add_conditional_edges(
            "provide_agent_stats",
            self._route_to_summarization_check,
            {
                "summarize_history": "summarize_history",
                "finalize_response": "finalize_response"
            }
        )
        
        workflow.add_conditional_edges(
            "unknown_intent",
            self._route_to_summarization_check,
            {
                "summarize_history": "summarize_history",
                "finalize_response": "finalize_response"
            }
        )
        
        workflow.add_conditional_edges(
            "handle_cancellation", 
            self._route_to_summarization_check,
            {
                "summarize_history": "summarize_history",
                "finalize_response": "finalize_response"
            }
        )
        
        # Phase 15: Summarization always leads to finalization
        workflow.add_edge("summarize_history", "finalize_response")
        
        # Phase 15: Finalization is the final exit point
        workflow.add_edge("finalize_response", END)
        
        return workflow.compile()

    def _route_from_ingest_message(self, state: GraphState) -> str:
        """Route from ingest_user_message node using centralized routing."""
        return GraphRoutingIntegration.route_from_ingest_message(cast(Dict[str, Any], state))

    def _route_from_classify_intent(self, state: GraphState) -> str:
        """Route from classify_intent node using centralized routing."""
        return GraphRoutingIntegration.route_from_classify_intent(cast(Dict[str, Any], state))

    def _route_from_create_patient(self, state: GraphState) -> str:
        """Route from create_patient node using centralized routing."""
        return GraphRoutingIntegration.route_from_create_patient(cast(Dict[str, Any], state))

    def _route_from_update_patient(self, state: GraphState) -> str:
        """Route from update_patient node using centralized routing."""
        return GraphRoutingIntegration.route_from_update_patient(cast(Dict[str, Any], state))

    def _route_from_delete_patient(self, state: GraphState) -> str:
        """Route from delete_patient node using centralized routing."""
        return GraphRoutingIntegration.route_from_delete_patient(cast(Dict[str, Any], state))

    def _route_from_confirmation(self, state: GraphState) -> str:
        """Route from handle_confirmation node using centralized routing."""
        return GraphRoutingIntegration.route_from_confirmation(cast(Dict[str, Any], state))

    def _route_to_summarization_check(self, state: GraphState) -> str:
        """
        Generic routing for nodes that need summarization check using centralized routing.
        """
        return GraphRoutingIntegration.route_to_summarization_check(cast(Dict[str, Any], state))

    async def process_message(self, user_message: str, conversation_state: ConversationState) -> Tuple[str, ConversationState]:
        """
        Process a user message through the conversation graph.
        
        Args:
            user_message: The user's input message
            conversation_state: Current conversation state
            
        Returns:
            Tuple of (agent_response, updated_conversation_state)
        """
        logger.info(f"[GRAPH] 🚀 Processing message: '{user_message[:50]}...'")
        
        # Create initial graph state (Phase 15: starts with ingest_user_message)
        initial_state: GraphState = {
            "user_message": user_message,
            "agent_response": "",
            "conversation_state": conversation_state,
            "classified_intent": None,
            "extracted_fields": {},
            "tool_result": None,
            "next_node": None,
            "should_end": False
        }
        
        try:
            # Run the graph (entry point is now ingest_user_message per Phase 15)
            final_state = await self.graph.ainvoke(initial_state)
            
            # Extract results
            agent_response = final_state["agent_response"]
            updated_conv_state = final_state["conversation_state"]
            
            # Add agent response to message history
            updated_conv_state.recent_messages.append(f"Assistant: {agent_response}")
            
            logger.info(f"[GRAPH] ✅ Message processed successfully")
            
            return agent_response, updated_conv_state
            
        except Exception as e:
            logger.error(f"[GRAPH] ❌ Error processing message: {e}")
            
            # Return error response with finalization
            error_response = f"❌ I encountered an error processing your request: {e}"
            
            # Apply basic finalization to error response
            finalized_error = self._apply_basic_finalization(error_response, conversation_state)
            
            # Store error in last_tool_error
            conversation_state.last_tool_error = {"error": str(e), "timestamp": datetime.now().isoformat()}
            
            return finalized_error, conversation_state

    def _apply_basic_finalization(self, response: str, conv_state: ConversationState) -> str:
        """Apply basic finalization when graph execution fails."""
        # Ensure PII masking even for error responses
        import re
        nric_pattern = r'\b[STFG]\d{7}[A-Z]\b'
        masked_response = re.sub(nric_pattern, lambda m: mask_nric(m.group()), response)
        
        return masked_response

    def process_message_sync(self, user_message: str, conversation_state: ConversationState) -> Tuple[str, ConversationState]:
        """
        Synchronous wrapper for process_message.
        
        Args:
            user_message: The user's input message
            conversation_state: Current conversation state
            
        Returns:
            Tuple of (agent_response, updated_conversation_state)
        """
        import asyncio
        
        # Create event loop if none exists
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Run the async method
        return loop.run_until_complete(
            self.process_message(user_message, conversation_state)
        )


# ===== CONVENIENCE FUNCTIONS =====

def create_conversation_graph(http_client: HttpClient) -> ConversationGraph:
    """Create a conversation graph instance."""
    return ConversationGraph(http_client)


def process_conversation_turn(
    graph: ConversationGraph, 
    user_message: str, 
    conversation_state: ConversationState
) -> Tuple[str, ConversationState]:
    """
    Process a single conversation turn.
    
    Args:
        graph: ConversationGraph instance
        user_message: User's input message
        conversation_state: Current conversation state
        
    Returns:
        Tuple of (agent_response, updated_conversation_state)
    """
    return graph.process_message_sync(user_message, conversation_state)
