# HydroChat Conversation Graph Implementation
# LangGraph-based conversation orchestrator for patient management workflows
# Implements nodes 1-12 subset for create patient and list patients flows

import logging
from typing import Any, Dict, List, Optional, Tuple, TypedDict, Literal
from datetime import datetime

from langgraph.graph import StateGraph, MessagesState, END
from langgraph.prebuilt import ToolNode

from .enums import Intent, PendingAction, ConfirmationType, DownloadStage
from .state import ConversationState
from .intent_classifier import classify_intent, extract_fields, validate_required_patient_fields
from .tools import ToolManager, ToolResponse
from .name_cache import NameResolutionCache, resolve_patient_name
from .http_client import HttpClient
from .utils import mask_nric

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
        
        # Classify intent
        intent = classify_intent(user_message)
        extracted_fields = extract_fields(user_message)
        
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
            tool_result = self.tool_manager.execute_tool(Intent.LIST_PATIENTS)
            
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
                
                response = f"❌ Failed to get patient details: {tool_result.error}"
                if "404" in str(tool_result.error) or "not found" in str(tool_result.error).lower():
                    response += "\n\nWould you like to see a list of all patients?"
                
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
                
                response = f"❌ Failed to get scan results: {tool_result.error}"
                if "404" in str(tool_result.error) or "not found" in str(tool_result.error).lower():
                    response += f"\n\nPatient ID {patient_id} may not exist. Would you like to see a list of all patients?"
                
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

    def _determine_next_node_from_intent(self, intent: Intent) -> str:
        """Determine the next node based on classified intent."""
        intent_routing = {
            Intent.CREATE_PATIENT: "create_patient",
            Intent.UPDATE_PATIENT: "update_patient", 
            Intent.DELETE_PATIENT: "delete_patient",
            Intent.LIST_PATIENTS: "list_patients",
            Intent.GET_PATIENT_DETAILS: "get_patient_details",
            Intent.GET_SCAN_RESULTS: "get_scan_results",
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
        """Build and configure the conversation graph."""
        
        # Create state graph
        workflow = StateGraph(GraphState)
        
        # Add all nodes
        workflow.add_node("classify_intent", self.nodes.classify_intent_node)
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
        workflow.add_node("handle_confirmation", self.nodes.handle_confirmation_node)
        workflow.add_node("unknown_intent", self.nodes.unknown_intent_node)
        
        # Set entry point - check for pending confirmations first
        workflow.set_entry_point("classify_intent")
        
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
                "handle_confirmation": "handle_confirmation",
                "unknown_intent": "unknown_intent"
            }
        )
        
        # Add conditional routing from create_patient
        workflow.add_conditional_edges(
            "create_patient",
            self._route_from_create_patient,
            {
                "execute_create_patient": "execute_create_patient",
                "end": END
            }
        )
        
        # Add conditional routing from update_patient  
        workflow.add_conditional_edges(
            "update_patient",
            self._route_from_update_patient,
            {
                "execute_update_patient": "execute_update_patient",
                "end": END
            }
        )
        
        # Add conditional routing from delete_patient (goes to confirmation or execution)
        workflow.add_conditional_edges(
            "delete_patient", 
            self._route_from_delete_patient,
            {
                "end": END
            }
        )
        
        # Add conditional routing from handle_confirmation
        workflow.add_conditional_edges(
            "handle_confirmation",
            self._route_from_confirmation,
            {
                "execute_delete_patient": "execute_delete_patient",
                "provide_stl_links": "provide_stl_links",
                "end": END
            }
        )
        
        # All execution and terminal nodes end the conversation
        workflow.add_edge("execute_create_patient", END)
        workflow.add_edge("execute_update_patient", END)
        workflow.add_edge("execute_delete_patient", END)
        workflow.add_edge("list_patients", END)
        workflow.add_edge("get_patient_details", END)
        workflow.add_edge("get_scan_results", END)
        workflow.add_edge("provide_stl_links", END)
        workflow.add_edge("unknown_intent", END)
        
        return workflow.compile()

    def _route_from_classify_intent(self, state: GraphState) -> str:
        """Route from classify_intent node based on next_node or confirmation state."""
        conv_state = state["conversation_state"]
        
        # Check if we're waiting for a confirmation
        if conv_state.confirmation_required:
            return "handle_confirmation"
        
        return state.get("next_node") or "unknown_intent"

    def _route_from_create_patient(self, state: GraphState) -> str:
        """Route from create_patient node based on next_node."""
        return state.get("next_node") or "end"

    def _route_from_update_patient(self, state: GraphState) -> str:
        """Route from update_patient node based on next_node."""
        return state.get("next_node") or "end"

    def _route_from_delete_patient(self, state: GraphState) -> str:
        """Route from delete_patient node (always ends to wait for confirmation)."""
        return "end"

    def _route_from_confirmation(self, state: GraphState) -> str:
        """Route from handle_confirmation node based on next_node."""
        return state.get("next_node") or "end"

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
        
        # Create initial graph state
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
            # Run the graph
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
            
            # Return error response
            error_response = f"❌ I encountered an error processing your request: {e}"
            # Store error in last_tool_error instead of non-existent fields
            conversation_state.last_tool_error = {"error": str(e), "timestamp": datetime.now().isoformat()}
            
            return error_response, conversation_state

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
