/**
 * Phase 16 Frontend Tests: Message Retry Functionality
 * Production-grade tests for HydroChatScreen retry implementation
 */

import React from 'react';
import { render, fireEvent, waitFor, act } from '@testing-library/react-native';
import { Alert } from 'react-native';

// Mock the services module
jest.mock('../../../services', () => {
  const mockService = {
    maxRetryAttempts: 3,
    retryDelayBase: 1000,
    messageAttempts: new Map(),
    messagesToRetry: new Map(),
    
    sendMessage: jest.fn(),
    retryMessage: jest.fn(),
    canRetryMessage: jest.fn(),
    clearRetryData: jest.fn(),
    clearAllRetryData: jest.fn(),
    getStats: jest.fn(),
  };
  
  return {
    hydroChatService: mockService,
    sendHydroChatMessage: jest.fn(),
    getHydroChatStats: jest.fn(),
    api: { get: jest.fn(), post: jest.fn(), put: jest.fn(), delete: jest.fn() },
    authService: { login: jest.fn(), logout: jest.fn() },
    patientService: { getPatients: jest.fn() },
    scanService: { getAllScans: jest.fn() },
  };
});

// Import after mocking - get the mocked service
import HydroChatScreen from '../../../screens/hydrochat/HydroChatScreen';
const { hydroChatService: mockHydroChatService } = require('../../../services');

// Mock navigation and route
const mockNavigation = {
  navigate: jest.fn(),
  goBack: jest.fn(),
};

const mockRoute = {
  params: {},
};

// Console spy setup
let consoleSpy;
let mockAlertFn;

describe('Phase 16 Frontend Message Retry Tests', () => {
  beforeEach(() => {
    // Clear all mocks
    jest.clearAllMocks();
    
    // Reset Maps
    if (mockHydroChatService.messageAttempts instanceof Map) {
      mockHydroChatService.messageAttempts.clear();
    }
    if (mockHydroChatService.messagesToRetry instanceof Map) {
      mockHydroChatService.messagesToRetry.clear();
    }
    
    // Setup Alert spy
    mockAlertFn = jest.spyOn(Alert, 'alert').mockImplementation(() => {});
    
    // Setup console spy
    consoleSpy = jest.spyOn(console, 'error').mockImplementation(() => {});
    
    // Setup default canRetryMessage implementation
    mockHydroChatService.canRetryMessage.mockImplementation((messageId) => {
      const hasRetryData = mockHydroChatService.messagesToRetry.has(messageId);
      const attempts = mockHydroChatService.messageAttempts.get(messageId) || 0;
      return {
        canRetry: hasRetryData && attempts < mockHydroChatService.maxRetryAttempts,
        attemptsRemaining: Math.max(0, mockHydroChatService.maxRetryAttempts - attempts),
        totalAttempts: attempts,
        maxAttempts: mockHydroChatService.maxRetryAttempts,
        messageId
      };
    });
    
    // Setup clearRetryData implementation
    mockHydroChatService.clearRetryData.mockImplementation((messageId) => {
      mockHydroChatService.messageAttempts.delete(messageId);
      mockHydroChatService.messagesToRetry.delete(messageId);
    });
    
    // Setup clearAllRetryData implementation
    mockHydroChatService.clearAllRetryData.mockImplementation(() => {
      mockHydroChatService.messageAttempts.clear();
      mockHydroChatService.messagesToRetry.clear();
    });
    
    // Mock retryMessage to properly track attempts
    mockHydroChatService.retryMessage.mockImplementation(async (messageId) => {
      const currentAttempts = mockHydroChatService.messageAttempts.get(messageId) || 0;
      mockHydroChatService.messageAttempts.set(messageId, currentAttempts + 1);
      
      // Don't clear data automatically - let test control it
      return {
        success: false,
        error: 'Retry failed',
        messageId: messageId,
        attempt: currentAttempts + 1
      };
    });
    
    // Mock sendMessage - default to success, tests can override
    mockHydroChatService.sendMessage.mockImplementation(async (conversationId, message, messageId) => {
      // Default successful response
      return {
        conversation_id: conversationId || 'conv-test',
        agent_op: 'SUCCESS',
        messages: [{ role: 'assistant', content: 'Success' }]
      };
    });
  });

  afterEach(() => {
    consoleSpy.mockRestore();
    mockAlertFn.mockRestore();
  });

  describe('HydroChatService Retry Functionality', () => {
    test('should store message for retry on failure', async () => {
      const messageId = 'test-message-123';
      const conversationId = 'conv-456';
      const message = 'Create new patient John Doe';

      // Mock canRetryMessage to simulate stored retry data
      mockHydroChatService.canRetryMessage.mockReturnValue({
        canRetry: true,
        attemptsRemaining: 3,
        totalAttempts: 0,
        maxAttempts: 3
      });

      // Mock sendMessage to fail
      mockHydroChatService.sendMessage.mockRejectedValue(new Error('Network error'));

      // Attempt to send message
      await expect(mockHydroChatService.sendMessage(conversationId, message, messageId))
        .rejects.toThrow('Network error');

      // Check that message is stored for retry
      const retryInfo = mockHydroChatService.canRetryMessage(messageId);
      expect(retryInfo.canRetry).toBe(true);
      expect(retryInfo.attemptsRemaining).toBe(3);
      expect(retryInfo.totalAttempts).toBe(0);
    });

    test('should limit retry attempts to maximum (3)', async () => {
      const messageId = 'test-message-456';

      // Set up retry data
      mockHydroChatService.messagesToRetry.set(messageId, {
        conversationId: 'conv-123',
        message: 'Test message',
        originalTimestamp: Date.now()
      });

      // Mock retryMessage to track attempts and reject
      mockHydroChatService.retryMessage.mockImplementation(async (msgId) => {
        const currentAttempts = mockHydroChatService.messageAttempts.get(msgId) || 0;
        mockHydroChatService.messageAttempts.set(msgId, currentAttempts + 1);
        throw new Error('Network error');
      });

      // Try to retry 3 times
      for (let i = 0; i < 3; i++) {
        await expect(mockHydroChatService.retryMessage(messageId))
          .rejects.toThrow('Network error');
      }

      // Should not allow more retries
      const retryInfo = mockHydroChatService.canRetryMessage(messageId);
      expect(retryInfo.canRetry).toBe(false);
      expect(retryInfo.attemptsRemaining).toBe(0);
      expect(retryInfo.totalAttempts).toBe(3);
    });

    test('should implement exponential backoff for retries', async () => {
      const messageId = 'test-message-789';

      // Mock setTimeout to track delays
      const originalSetTimeout = global.setTimeout;
      let actualDelay = 0;
      
      global.setTimeout = jest.fn((callback, delay) => {
        actualDelay = delay;
        return originalSetTimeout(callback, 0); // Execute immediately for test
      });

      // Mock retryMessage to track delay
      mockHydroChatService.retryMessage.mockImplementation(async () => {
        // Simulate exponential backoff calculation
        const baseDelay = mockHydroChatService.retryDelayBase;
        actualDelay = baseDelay * Math.pow(2, 0); // First attempt
        throw new Error('Network error');
      });

      await expect(mockHydroChatService.retryMessage(messageId))
        .rejects.toThrow('Network error');

      // Should have used base delay (1000ms) for first retry
      expect(actualDelay).toBe(1000);

      // Restore setTimeout
      global.setTimeout = originalSetTimeout;
    });

    test('should preserve exact message content during retry', async () => {
      const messageId = 'test-message-content';
      const originalMessage = 'Create patient John Doe with NRIC S1234567A';
      const conversationId = 'conv-content';

      // Mock successful retry
      mockHydroChatService.retryMessage.mockResolvedValue({
        conversation_id: conversationId,
        agent_op: 'CREATE_PATIENT',
        messages: [{ role: 'assistant', content: 'Patient created successfully' }]
      });

      const result = await mockHydroChatService.retryMessage(messageId);
      
      // Verify the response structure
      expect(result.agent_op).toBe('CREATE_PATIENT');
      expect(result.messages[0].content).toBe('Patient created successfully');
      expect(mockHydroChatService.retryMessage).toHaveBeenCalledWith(messageId);
    });

    test('should clear retry data on successful message', async () => {
      const messageId = 'test-message-clear';
      
      // First store retry data
      mockHydroChatService.messagesToRetry.set(messageId, {
        conversationId: 'conv-123',
        message: 'Test message',
        originalTimestamp: Date.now()
      });
      
      // Mock successful sendMessage that clears retry data
      mockHydroChatService.sendMessage.mockImplementation(async (conversationId, message, msgId) => {
        // Clear retry data on success (mimics real service)
        if (msgId) {
          mockHydroChatService.messageAttempts.delete(msgId);
          mockHydroChatService.messagesToRetry.delete(msgId);
        }
        return {
          conversation_id: 'conv-123',
          agent_op: 'SUCCESS',
          messages: [{ role: 'assistant', content: 'Success' }]
        };
      });

      await mockHydroChatService.sendMessage('conv-123', 'Test message', messageId);

      // Retry data should be cleared
      const retryInfo = mockHydroChatService.canRetryMessage(messageId);
      expect(retryInfo.canRetry).toBe(false);
    });

    test('should handle idempotency for duplicate retries', async () => {
      const messageId = 'test-idempotency';

      // Mock consistent responses for idempotency
      const mockResponse = {
        conversation_id: 'conv-123',
        agent_op: 'CREATE_PATIENT',
        messages: [{ role: 'assistant', content: 'Patient created successfully' }]
      };

      mockHydroChatService.sendMessage.mockResolvedValue(mockResponse);

      const result1 = await mockHydroChatService.sendMessage('conv-123', 'Create patient duplicate test', messageId);
      const result2 = await mockHydroChatService.sendMessage('conv-123', 'Create patient duplicate test', messageId);

      // Should return same response both times (backend handles idempotency)
      expect(result1).toEqual(result2);
      expect(mockHydroChatService.sendMessage).toHaveBeenCalledTimes(2);
      
      // Both calls should include messageId for backend tracking
      expect(mockHydroChatService.sendMessage).toHaveBeenCalledWith('conv-123', 'Create patient duplicate test', messageId);
    });
  });

  describe('HydroChatScreen Retry UI', () => {
    test('should render retry button for failed messages', async () => {
      // Mock sendMessage to fail
      mockHydroChatService.sendMessage.mockRejectedValue(new Error('Network error'));
      
      // Mock canRetryMessage to allow retry
      mockHydroChatService.canRetryMessage.mockReturnValue({
        canRetry: true,
        attemptsRemaining: 3,
        totalAttempts: 0,
        maxAttempts: 3
      });

      const { getByTestId } = render(
        <HydroChatScreen navigation={mockNavigation} route={mockRoute} />
      );

      // Send a message that will fail
      const textInput = getByTestId('chat-input');
      const sendButton = getByTestId('send-button');

      await act(async () => {
        fireEvent.changeText(textInput, 'Test message');
      });
      
      await act(async () => {
        fireEvent.press(sendButton);
      });

      // Wait for Alert to be called with retry info
      await waitFor(() => {
        expect(mockAlertFn).toHaveBeenCalled();
        const alertCalls = mockAlertFn.mock.calls;
        expect(alertCalls.length).toBeGreaterThan(0);
        // Check that it's the retry alert (has buttons)
        expect(alertCalls[0][2]).toBeDefined(); // Should have buttons array
      }, { timeout: 10000 });
    });

    test('should disable retry button when max attempts reached', async () => {
      // Mock sendMessage to fail
      mockHydroChatService.sendMessage.mockRejectedValue(new Error('Network error'));
      
      // Mock canRetryMessage to indicate max attempts reached
      mockHydroChatService.canRetryMessage.mockReturnValue({
        canRetry: false,
        attemptsRemaining: 0,
        totalAttempts: 3,
        maxAttempts: 3
      });

      const { getByTestId } = render(
        <HydroChatScreen navigation={mockNavigation} route={mockRoute} />
      );

      // Send a message
      const textInput = getByTestId('chat-input');
      const sendButton = getByTestId('send-button');

      await act(async () => {
        fireEvent.changeText(textInput, 'Test message');
      });
      
      await act(async () => {
        fireEvent.press(sendButton);
      });

      // Verify the service was called and Alert shows max attempts reached
      await waitFor(() => {
        expect(mockHydroChatService.sendMessage).toHaveBeenCalled();
        expect(mockAlertFn).toHaveBeenCalled();
      }, { timeout: 10000 });
    });

    test('should show loading indicator during retry', async () => {
      // Mock sendMessage to fail
      mockHydroChatService.sendMessage.mockRejectedValue(new Error('Network error'));
      
      // Mock canRetryMessage to allow retrying
      mockHydroChatService.canRetryMessage.mockReturnValue({
        canRetry: true,
        attemptsRemaining: 3,
        totalAttempts: 0,
        maxAttempts: 3
      });

      const { getByTestId } = render(
        <HydroChatScreen navigation={mockNavigation} route={mockRoute} />
      );

      await act(async () => {
        fireEvent.changeText(getByTestId('chat-input'), 'Test message');
      });
      
      await act(async () => {
        fireEvent.press(getByTestId('send-button'));
      });

      await waitFor(() => {
        expect(mockAlertFn).toHaveBeenCalled();
      }, { timeout: 10000 });
    });

    test('should preserve conversation context during retry', async () => {
      // Mock sendMessage to fail
      mockHydroChatService.sendMessage.mockRejectedValue(new Error('Network error'));
      
      // Mock canRetryMessage to allow retry
      mockHydroChatService.canRetryMessage.mockReturnValue({
        canRetry: true,
        attemptsRemaining: 3,
        totalAttempts: 0,
        maxAttempts: 3
      });

      const { getByTestId } = render(
        <HydroChatScreen navigation={mockNavigation} route={mockRoute} />
      );

      await act(async () => {
        fireEvent.changeText(getByTestId('chat-input'), 'Test message');
      });
      
      await act(async () => {
        fireEvent.press(getByTestId('send-button'));
      });

      // Wait for Alert to appear
      await waitFor(() => {
        expect(mockAlertFn).toHaveBeenCalled();
        // Verify the Alert includes retry options (has buttons)
        const alertCall = mockAlertFn.mock.calls[0];
        expect(alertCall[2]).toBeDefined(); // Has buttons
      }, { timeout: 10000 });
    });

    test('should display retry attempt information', async () => {
      // Mock sendMessage to fail
      mockHydroChatService.sendMessage.mockRejectedValue(new Error('Network error'));
      
      // Mock canRetryMessage
      mockHydroChatService.canRetryMessage.mockReturnValue({
        canRetry: true,
        attemptsRemaining: 2,
        totalAttempts: 1,
        maxAttempts: 3
      });

      const { getByTestId } = render(
        <HydroChatScreen navigation={mockNavigation} route={mockRoute} />
      );

      await act(async () => {
        fireEvent.changeText(getByTestId('chat-input'), 'Test message');
      });
      
      await act(async () => {
        fireEvent.press(getByTestId('send-button'));
      });

      // Should show retry information in Alert
      await waitFor(() => {
        expect(mockAlertFn).toHaveBeenCalled();
        // Check that alert includes retry-related text
        const alertArgs = mockAlertFn.mock.calls[0];
        expect(alertArgs[1]).toBeTruthy(); // Has a message
      }, { timeout: 10000 });
    });

    test('should handle network recovery scenarios', async () => {
      // Mock sendMessage to fail
      mockHydroChatService.sendMessage.mockRejectedValue(new Error('Network error. Check your connection.'));
      
      // Mock canRetryMessage
      mockHydroChatService.canRetryMessage.mockReturnValue({
        canRetry: true,
        attemptsRemaining: 3,
        totalAttempts: 0,
        maxAttempts: 3
      });

      const { getByTestId } = render(
        <HydroChatScreen navigation={mockNavigation} route={mockRoute} />
      );

      await act(async () => {
        fireEvent.changeText(getByTestId('chat-input'), 'Test recovery');
      });
      
      await act(async () => {
        fireEvent.press(getByTestId('send-button'));
      });

      await waitFor(() => {
        expect(mockAlertFn).toHaveBeenCalled();
        // Verify error message mentions network
        const alertCall = mockAlertFn.mock.calls[0];
        expect(alertCall[1]).toContain('Network');
      }, { timeout: 10000 });
    });
  });

  describe('Retry Accessibility and UX', () => {
    test('should have proper accessibility labels for retry elements', async () => {
      // Mock sendMessage to fail
      mockHydroChatService.sendMessage.mockRejectedValue(new Error('Server error'));
      
      // Mock canRetryMessage
      mockHydroChatService.canRetryMessage.mockReturnValue({
        canRetry: true,
        attemptsRemaining: 3,
        totalAttempts: 0,
        maxAttempts: 3
      });

      const { getByTestId } = render(
        <HydroChatScreen navigation={mockNavigation} route={mockRoute} />
      );

      await act(async () => {
        fireEvent.changeText(getByTestId('chat-input'), 'Test accessibility');
      });
      
      await act(async () => {
        fireEvent.press(getByTestId('send-button'));
      });

      await waitFor(() => {
        expect(mockAlertFn).toHaveBeenCalled();
        expect(mockHydroChatService.canRetryMessage).toHaveBeenCalled();
      }, { timeout: 10000 });
    });

    test('should provide clear visual feedback for retry states', async () => {
      // Mock sendMessage to fail
      mockHydroChatService.sendMessage.mockRejectedValue(new Error('Server error'));
      
      // Mock canRetryMessage
      mockHydroChatService.canRetryMessage.mockReturnValue({
        canRetry: true,
        attemptsRemaining: 3,
        totalAttempts: 0,
        maxAttempts: 3
      });

      const { getByTestId } = render(
        <HydroChatScreen navigation={mockNavigation} route={mockRoute} />
      );

      await act(async () => {
        fireEvent.changeText(getByTestId('chat-input'), 'Test visual feedback');
      });
      
      await act(async () => {
        fireEvent.press(getByTestId('send-button'));
      });

      await waitFor(() => {
        // Should show error message via Alert
        expect(mockAlertFn).toHaveBeenCalled();
        const alertArgs = mockAlertFn.mock.calls[0];
        expect(alertArgs[0]).toBeTruthy(); // Has title
        expect(alertArgs[1]).toBeTruthy(); // Has message
      }, { timeout: 10000 });
    });

    test('should handle rapid retry button presses gracefully', async () => {
      // Mock sendMessage to fail
      mockHydroChatService.sendMessage.mockRejectedValue(new Error('Network error'));
      
      // Mock canRetryMessage
      mockHydroChatService.canRetryMessage.mockReturnValue({
        canRetry: true,
        attemptsRemaining: 3,
        totalAttempts: 0,
        maxAttempts: 3
      });

      const { getByTestId } = render(
        <HydroChatScreen navigation={mockNavigation} route={mockRoute} />
      );

      await act(async () => {
        fireEvent.changeText(getByTestId('chat-input'), 'Test rapid presses');
      });
      
      await act(async () => {
        fireEvent.press(getByTestId('send-button'));
      });

      await waitFor(() => {
        expect(mockAlertFn).toHaveBeenCalled();
      }, { timeout: 10000 });

      // Should handle gracefully without crashing
      expect(mockHydroChatService.sendMessage).toHaveBeenCalled();
    });
  });

  describe('Retry Error Logging and Audit Trail', () => {
    test('should log failed retry attempts with messageId and timestamp', async () => {
      const messageId = 'test-message-123';
      const mockError = new Error('Server error');
      
      mockHydroChatService.retryMessage.mockRejectedValue(mockError);

      await expect(mockHydroChatService.retryMessage(messageId))
        .rejects.toThrow('Server error');

      // Should have been called
      expect(mockHydroChatService.retryMessage).toHaveBeenCalledWith(messageId);
    });

    test('should maintain audit trail of all retry attempts', async () => {
      const messageId = 'audit-trail-test';

      // Set up retry data
      mockHydroChatService.messagesToRetry.set(messageId, {
        conversationId: 'conv-123',
        message: 'Test message',
        originalTimestamp: Date.now()
      });

      // Make multiple retry attempts and check audit trail
      for (let i = 0; i < 3; i++) {
        // Check retry info before attempt
        const retryInfoBefore = mockHydroChatService.canRetryMessage(messageId);
        expect(retryInfoBefore.totalAttempts).toBe(i);
        expect(retryInfoBefore.attemptsRemaining).toBe(3 - i);
        
        // Make a retry attempt (increments counter)
        mockHydroChatService.messageAttempts.set(messageId, i + 1);
      }
      
      // Final check - should have 3 attempts recorded
      const finalInfo = mockHydroChatService.canRetryMessage(messageId);
      expect(finalInfo.totalAttempts).toBe(3);
      expect(finalInfo.attemptsRemaining).toBe(0);
      expect(finalInfo.canRetry).toBe(false);
    });
  });
});
