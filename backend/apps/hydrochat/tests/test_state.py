import json
from datetime import datetime
from apps.hydrochat.state import ConversationState
from apps.hydrochat.enums import Intent, PendingAction, ConfirmationType, DownloadStage


def test_state_completeness():
    """Test that all required state keys exist on initialization."""
    state = ConversationState()
    # Should not raise - completeness validated in constructor
    assert state.intent == Intent.UNKNOWN
    assert state.pending_action == PendingAction.NONE
    assert state.awaiting_confirmation_type == ConfirmationType.NONE
    assert state.download_stage == DownloadStage.NONE


def test_enum_serialization():
    """Test enums are serialized by name in snapshot."""
    state = ConversationState()
    state.intent = Intent.CREATE_PATIENT
    state.pending_action = PendingAction.CREATE_PATIENT
    state.awaiting_confirmation_type = ConfirmationType.DELETE
    state.download_stage = DownloadStage.PREVIEW_SHOWN
    
    snapshot = state.serialize_snapshot()
    assert snapshot['intent'] == 'CREATE_PATIENT'
    assert snapshot['pending_action'] == 'CREATE_PATIENT'
    assert snapshot['awaiting_confirmation_type'] == 'DELETE' 
    assert snapshot['download_stage'] == 'PREVIEW_SHOWN'
    
    # Should be JSON serializable
    json_str = json.dumps(snapshot)
    assert '"intent": "CREATE_PATIENT"' in json_str


def test_deque_serialization():
    """Test recent_messages deque is serialized as list."""
    state = ConversationState()
    state.add_message('user', 'hello')
    state.add_message('assistant', 'hi there')
    
    snapshot = state.serialize_snapshot()
    messages = snapshot['recent_messages']
    assert isinstance(messages, list)
    assert len(messages) == 2
    assert messages[0]['role'] == 'user'
    assert messages[1]['role'] == 'assistant'
    
    # Should be JSON serializable
    json.dumps(snapshot)


def test_cancellation_reset():
    """Test cancellation resets expected fields."""
    state = ConversationState()
    # Populate fields that should be reset
    state.pending_action = PendingAction.CREATE_PATIENT
    state.extracted_fields = {'name': 'John'}
    state.validated_fields = {'first_name': 'John'}
    state.pending_fields = {'last_name', 'nric'}
    state.disambiguation_options = [{'id': 1, 'name': 'test'}]
    state.selected_patient_id = 123
    state.clarification_loop_count = 2
    state.confirmation_required = True
    state.awaiting_confirmation_type = ConfirmationType.DELETE
    state.download_stage = DownloadStage.PREVIEW_SHOWN
    state.last_tool_error = {'status': 400}
    
    state.reset_for_cancellation()
    
    # Assert reset fields
    assert state.pending_action == PendingAction.NONE
    assert state.extracted_fields == {}
    assert state.validated_fields == {}
    assert state.pending_fields == set()
    assert state.disambiguation_options == []
    assert state.selected_patient_id is None
    assert state.clarification_loop_count == 0
    assert state.confirmation_required is False
    assert state.awaiting_confirmation_type == ConfirmationType.NONE
    assert state.download_stage == DownloadStage.NONE
    assert state.last_tool_error is None


def test_message_rolling_window():
    """Test recent_messages respects maxlen=5."""
    state = ConversationState()
    # Add 7 messages
    for i in range(7):
        state.add_message('user', f'message {i}')
    
    # Should only keep last 5
    assert len(state.recent_messages) == 5
    messages = list(state.recent_messages)
    assert messages[0]['content'] == 'message 2'  # oldest kept
    assert messages[-1]['content'] == 'message 6'  # newest
