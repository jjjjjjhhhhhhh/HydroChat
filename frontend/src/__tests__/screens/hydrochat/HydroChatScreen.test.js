import React from 'react';
import { render, fireEvent, waitFor, screen } from '@testing-library/react-native';
import { Alert } from 'react-native';
import { resetMockServiceState } from '../../__setup__/mockServices';
import HydroChatScreen from '../../../screens/hydrochat/HydroChatScreen';

// Mock the hydro chat service - inline required by Jest
jest.mock('../../../services/hydroChatService', () => ({
  hydroChatService: {
    sendMessage: jest.fn(),
    canRetryMessage: jest.fn(),
    clearRetryData: jest.fn(),
  },
}));

// Mock React Navigation
jest.mock('@react-navigation/native', () => ({
  useFocusEffect: jest.fn(),
}));

// Mock Alert
jest.spyOn(Alert, 'alert');

const mockNavigation = {
  navigate: jest.fn(),
  goBack: jest.fn(),
  setParams: jest.fn(),
};

const mockRoute = {
  params: {},
};

// Import mocked service
const { hydroChatService } = require('../../../services/hydroChatService');

describe('HydroChatScreen', () => {
  beforeEach(() => {
    // Reset mock state using shared utility
    resetMockServiceState(hydroChatService);
    
    // Setup default mock: no retry capability (tests can override)
    hydroChatService.canRetryMessage.mockReturnValue({
      canRetry: false,
      attemptsRemaining: 0,
      totalAttempts: 0,
      maxAttempts: 3
    });
  });

  describe('Title Rendering', () => {
    it('should render title with correct colors', () => {
      render(<HydroChatScreen navigation={mockNavigation} route={mockRoute} />);
      
      expect(screen.getByText('Hydro')).toBeTruthy();
      expect(screen.getByText('Chat')).toBeTruthy();
    });
  });

  describe('Send Button Behavior', () => {
    it('should be disabled when input is empty', () => {
      render(<HydroChatScreen navigation={mockNavigation} route={mockRoute} />);
      
      const sendButton = screen.getByLabelText('Send message');
      expect(sendButton.props.accessibilityState.disabled).toBe(true);
    });

    it('should be enabled when input has text', () => {
      render(<HydroChatScreen navigation={mockNavigation} route={mockRoute} />);
      
      const textInput = screen.getByPlaceholderText('Type your message here');
      const sendButton = screen.getByLabelText('Send message');
      
      fireEvent.changeText(textInput, 'test message');
      
      expect(sendButton.props.accessibilityState.disabled).toBe(false);
    });

    it('should be disabled while sending', async () => {
      hydroChatService.sendMessage.mockImplementation(() => 
        new Promise(resolve => setTimeout(resolve, 100))
      );

      render(<HydroChatScreen navigation={mockNavigation} route={mockRoute} />);
      
      const textInput = screen.getByPlaceholderText('Type your message here');
      const sendButton = screen.getByLabelText('Send message');
      
      fireEvent.changeText(textInput, 'test message');
      fireEvent.press(sendButton);
      
      // Should be disabled while sending
      expect(sendButton.props.accessibilityState.disabled).toBe(true);
    });
  });

  describe('Typing Indicator', () => {
    it('should show typing indicator when sending message', async () => {
      hydroChatService.sendMessage.mockImplementation(() => 
        new Promise(resolve => setTimeout(() => resolve({
          conversation_id: 'test-id',
          messages: [{ role: 'assistant', content: 'Test response' }],
          agent_op: 'NONE',
          agent_state: {}
        }), 100))
      );

      render(<HydroChatScreen navigation={mockNavigation} route={mockRoute} />);
      
      const textInput = screen.getByPlaceholderText('Type your message here');
      const sendButton = screen.getByLabelText('Send message');
      
      fireEvent.changeText(textInput, 'test message');
      fireEvent.press(sendButton);
      
      // Should show typing indicator
      await waitFor(() => {
        expect(screen.getByLabelText('Assistant is typing')).toBeTruthy();
      });
    });

    it('should hide typing indicator after response', async () => {
      hydroChatService.sendMessage.mockResolvedValue({
        conversation_id: 'test-id',
        messages: [{ role: 'assistant', content: 'Test response' }],
        agent_op: 'NONE',
        agent_state: {}
      });

      render(<HydroChatScreen navigation={mockNavigation} route={mockRoute} />);
      
      const textInput = screen.getByPlaceholderText('Type your message here');
      const sendButton = screen.getByLabelText('Send message');
      
      fireEvent.changeText(textInput, 'test message');
      fireEvent.press(sendButton);
      
      await waitFor(() => {
        expect(screen.getByText('Test response')).toBeTruthy();
      });
      
      // Typing indicator should be gone
      expect(screen.queryByLabelText('Assistant is typing')).toBeNull();
    });
  });

  describe('Patient List Refresh Flag', () => {
    it('should set refresh flag when agent performs CRUD operation', async () => {
      const mockUseFocusEffect = require('@react-navigation/native').useFocusEffect;
      let focusEffectCallback;
      
      mockUseFocusEffect.mockImplementation((callback) => {
        focusEffectCallback = callback;
      });

      hydroChatService.sendMessage.mockResolvedValue({
        conversation_id: 'test-id',
        messages: [{ role: 'assistant', content: 'Patient created successfully' }],
        agent_op: 'CREATE',
        agent_state: { selected_patient_id: 123 }
      });

      render(<HydroChatScreen navigation={mockNavigation} route={mockRoute} />);
      
      const textInput = screen.getByPlaceholderText('Type your message here');
      const sendButton = screen.getByLabelText('Send message');
      
      fireEvent.changeText(textInput, 'create patient John Doe NRIC S1234567A');
      fireEvent.press(sendButton);
      
      await waitFor(() => {
        expect(screen.getByText('Patient created successfully')).toBeTruthy();
      });

      // Simulate screen unfocus (back navigation)
      const cleanupFunction = focusEffectCallback();
      if (cleanupFunction) {
        cleanupFunction();
      }
      
      expect(mockNavigation.navigate).toHaveBeenCalledWith('Patients List', { refresh: true });
    });

    it('should not set refresh flag when no CRUD operation performed', async () => {
      const mockUseFocusEffect = require('@react-navigation/native').useFocusEffect;
      let focusEffectCallback;
      
      mockUseFocusEffect.mockImplementation((callback) => {
        focusEffectCallback = callback;
      });

      hydroChatService.sendMessage.mockResolvedValue({
        conversation_id: 'test-id',
        messages: [{ role: 'assistant', content: 'Here are your patients...' }],
        agent_op: 'NONE',
        agent_state: {}
      });

      render(<HydroChatScreen navigation={mockNavigation} route={mockRoute} />);
      
      const textInput = screen.getByPlaceholderText('Type your message here');
      const sendButton = screen.getByLabelText('Send message');
      
      fireEvent.changeText(textInput, 'list patients');
      fireEvent.press(sendButton);
      
      await waitFor(() => {
        expect(screen.getByText('Here are your patients...')).toBeTruthy();
      });

      // Simulate screen unfocus (back navigation)
      const cleanupFunction = focusEffectCallback();
      if (cleanupFunction) {
        cleanupFunction();
      }
      
      expect(mockNavigation.navigate).not.toHaveBeenCalledWith('Patients List', { refresh: true });
    });
  });

  describe('Message Display', () => {
    it('should display user and assistant messages correctly', async () => {
      hydroChatService.sendMessage.mockResolvedValue({
        conversation_id: 'test-id',
        messages: [{ role: 'assistant', content: 'Hello! How can I help you?' }],
        agent_op: 'NONE',
        agent_state: {}
      });

      render(<HydroChatScreen navigation={mockNavigation} route={mockRoute} />);
      
      const textInput = screen.getByPlaceholderText('Type your message here');
      const sendButton = screen.getByLabelText('Send message');
      
      fireEvent.changeText(textInput, 'Hello');
      fireEvent.press(sendButton);
      
      // Wait for messages to appear
      await waitFor(() => {
        expect(screen.getByText('Hello')).toBeTruthy(); // User message
        expect(screen.getByText('Hello! How can I help you?')).toBeTruthy(); // Assistant message
      });
    });
  });

  describe('Error Handling', () => {
    it('should show error alert on network failure', async () => {
      hydroChatService.sendMessage.mockRejectedValue(new Error('Network error. Check your connection.'));
      
      // Mock canRetryMessage to allow retry
      hydroChatService.canRetryMessage.mockReturnValue({
        canRetry: true,
        attemptsRemaining: 3,
        totalAttempts: 0,
        maxAttempts: 3
      });

      render(<HydroChatScreen navigation={mockNavigation} route={mockRoute} />);
      
      const textInput = screen.getByPlaceholderText('Type your message here');
      const sendButton = screen.getByLabelText('Send message');
      
      fireEvent.changeText(textInput, 'test message');
      fireEvent.press(sendButton);
      
      await waitFor(() => {
        // Should call Alert.alert with retry options
        expect(Alert.alert).toHaveBeenCalled();
        const alertCall = Alert.alert.mock.calls[0];
        expect(alertCall[0]).toBe('Message Failed');
        expect(alertCall[1]).toContain('Network error');
      });
    });
  });

  describe('Proxy Message', () => {
    it('should show proxy message initially', () => {
      render(<HydroChatScreen navigation={mockNavigation} route={mockRoute} />);
      
      expect(screen.getByText('Try: "List patients" or "Create patient Jane Tan NRIC S1234567A"')).toBeTruthy();
    });

    it('should hide proxy message when user starts typing', () => {
      render(<HydroChatScreen navigation={mockNavigation} route={mockRoute} />);
      
      const textInput = screen.getByPlaceholderText('Type your message here');
      
      fireEvent.changeText(textInput, 'hello');
      
      expect(screen.queryByText('Try: "List patients" or "Create patient Jane Tan NRIC S1234567A"')).toBeNull();
    });
  });

  describe('Navigation', () => {
    it('should call goBack when back button pressed', () => {
      render(<HydroChatScreen navigation={mockNavigation} route={mockRoute} />);
      
      const backButton = screen.getByLabelText('Go back');
      fireEvent.press(backButton);
      
      expect(mockNavigation.goBack).toHaveBeenCalled();
    });
  });
});
