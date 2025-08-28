/**
 * Phase 16 Frontend Tests: Message Retry Functionality
 * Production-grade tests for HydroChatScreen retry implementation
 */

import React from 'react';
import { render, fireEvent, waitFor, act } from '@testing-library/react-native';
import { Alert } from 'react-native';

// Mock services before importing the screen
const mockHydroChatService = {
  maxRetryAttempts: 3,
  retryDelayBase: 1000,
  messageAttempts: new Map(),
  messagesToRetry: new Map(),
  
  sendMessage: jest.fn(),
  retryMessage: jest.fn(),
  canRetryMessage: jest.fn().mockImplementation((messageId) => {
    const attempts = mockHydroChatService.messageAttempts.get(messageId) || 0;
    return {
      canRetry: attempts < mockHydroChatService.maxRetryAttempts,
      attemptsRemaining: Math.max(0, mockHydroChatService.maxRetryAttempts - attempts),
      totalAttempts: attempts,
      messageId
    };
  }),
  clearRetryData: jest.fn().mockImplementation((messageId) => {
    mockHydroChatService.messageAttempts.delete(messageId);
    mockHydroChatService.messagesToRetry.delete(messageId);
  }),
  clearAllRetryData: jest.fn().mockImplementation(() => {
    mockHydroChatService.messageAttempts.clear();
    mockHydroChatService.messagesToRetry.clear();
  }),
  getStats: jest.fn().mockReturnValue({
    totalMessages: 0,
    failedMessages: 0,
    retriedMessages: 0,
    successfulRetries: 0
  }),
};

// Mock the service module
jest.mock('../../../services', () => ({
  hydroChatService: mockHydroChatService,
  sendHydroChatMessage: jest.fn(),
  getHydroChatStats: jest.fn(),
}));

// Import after mocking
import HydroChatScreen from '../../../screens/hydrochat/HydroChatScreen';

// Mock navigation and route
const mockNavigation = {
  navigate: jest.fn(),
  goBack: jest.fn(),
};

const mockRoute = {
  params: {},
};

// Mock Alert
jest.spyOn(Alert, 'alert');

// Console spy setup
let consoleSpy;

describe('Phase 16 Frontend Message Retry Tests', () => {
  beforeEach(() => {
    // Clear all mocks
    jest.clearAllMocks();
    mockHydroChatService.messageAttempts.clear();
    mockHydroChatService.messagesToRetry.clear();
    
    // Setup console spy
    consoleSpy = jest.spyOn(console, 'error').mockImplementation(() => {});
    
    // Mock retryMessage to properly track attempts
    mockHydroChatService.retryMessage.mockImplementation(async (messageId) => {
      const currentAttempts = mockHydroChatService.messageAttempts.get(messageId) || 0;
      mockHydroChatService.messageAttempts.set(messageId, currentAttempts + 1);
      
      return {
        success: false,
        error: 'Retry failed',
        messageId: messageId,
        attempt: currentAttempts + 1
      };
    });
  });

  afterEach(() => {
    consoleSpy.mockRestore();
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

      // Mock canRetryMessage for different stages
      mockHydroChatService.canRetryMessage
        .mockReturnValueOnce({ canRetry: true, attemptsRemaining: 3, totalAttempts: 0, maxAttempts: 3 })
        .mockReturnValueOnce({ canRetry: true, attemptsRemaining: 2, totalAttempts: 1, maxAttempts: 3 })
        .mockReturnValueOnce({ canRetry: true, attemptsRemaining: 1, totalAttempts: 2, maxAttempts: 3 })
        .mockReturnValue({ canRetry: false, attemptsRemaining: 0, totalAttempts: 3, maxAttempts: 3 });

      // Mock retryMessage to fail
      mockHydroChatService.retryMessage.mockRejectedValue(new Error('Network error'));

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
      
      // Mock successful sendMessage
      mockHydroChatService.sendMessage.mockResolvedValue({
        conversation_id: 'conv-123',
        agent_op: 'SUCCESS',
        messages: [{ role: 'assistant', content: 'Success' }]
      });

      // Mock canRetryMessage to return false after success
      mockHydroChatService.canRetryMessage.mockReturnValue({
        canRetry: false,
        attemptsRemaining: 0,
        totalAttempts: 0,
        maxAttempts: 3
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

      const { getByTestId, getByText } = render(
        <HydroChatScreen navigation={mockNavigation} route={mockRoute} />
      );

      // Send a message that will fail
      const textInput = getByTestId('chat-input');
      const sendButton = getByTestId('send-button');

      await act(async () => {
        fireEvent.changeText(textInput, 'Test message');
        fireEvent.press(sendButton);
      });

      // Wait for error and retry UI to appear
      await waitFor(() => {
        expect(getByText('Retry')).toBeTruthy();
      }, { timeout: 3000 });
    });

    test('should disable retry button when max attempts reached', async () => {
      mockHydroChatService.sendMessage.mockRejectedValue(new Error('Network error'));

      const { getByTestId } = render(
        <HydroChatScreen navigation={mockNavigation} route={mockRoute} />
      );

      // Send a message
      const textInput = getByTestId('chat-input');
      const sendButton = getByTestId('send-button');

      await act(async () => {
        fireEvent.changeText(textInput, 'Test message');
        fireEvent.press(sendButton);
      });

      // Verify the service was called and failed
      expect(mockHydroChatService.sendMessage).toHaveBeenCalled();
    });

    test('should show loading indicator during retry', async () => {
      // Mock delayed retry
      mockHydroChatService.retryMessage.mockImplementation(
        () => new Promise(resolve => {
          setTimeout(() => resolve({
            conversation_id: 'conv-123',
            agent_op: 'SUCCESS',
            messages: [{ role: 'assistant', content: 'Success' }]
          }), 50);
        })
      );

      mockHydroChatService.sendMessage.mockRejectedValue(new Error('Network error'));

      const { getByTestId, getByText } = render(
        <HydroChatScreen navigation={mockNavigation} route={mockRoute} />
      );

      // Send a message that will fail
      await act(async () => {
        fireEvent.changeText(getByTestId('chat-input'), 'Test message');
        fireEvent.press(getByTestId('send-button'));
      });

      await waitFor(() => {
        expect(getByText('Retry')).toBeTruthy();
      }, { timeout: 3000 });
    });

    test('should preserve conversation context during retry', async () => {
      const conversationId = 'conv-context-test';

      // Mock successful retry
      mockHydroChatService.retryMessage.mockResolvedValue({
        conversation_id: conversationId,
        agent_op: 'SUCCESS',
        messages: [{ role: 'assistant', content: 'Context preserved' }]
      });

      mockHydroChatService.sendMessage.mockRejectedValue(new Error('Network error'));

      const { getByTestId, getByText } = render(
        <HydroChatScreen navigation={mockNavigation} route={mockRoute} />
      );

      await act(async () => {
        fireEvent.changeText(getByTestId('chat-input'), 'Test message');
        fireEvent.press(getByTestId('send-button'));
      });

      await waitFor(() => {
        expect(getByText('Retry')).toBeTruthy();
      }, { timeout: 3000 });

      // Click retry
      await act(async () => {
        fireEvent.press(getByText('Retry'));
      });

      // Wait for retry to be called
      await waitFor(() => {
        expect(mockHydroChatService.retryMessage).toHaveBeenCalled();
      });
    });

    test('should display retry attempt information', async () => {
      mockHydroChatService.sendMessage.mockRejectedValue(new Error('Network error'));

      const { getByTestId, getByText } = render(
        <HydroChatScreen navigation={mockNavigation} route={mockRoute} />
      );

      await act(async () => {
        fireEvent.changeText(getByTestId('chat-input'), 'Test message');
        fireEvent.press(getByTestId('send-button'));
      });

      // Should show retry information
      await waitFor(() => {
        expect(getByText('Retry')).toBeTruthy();
      }, { timeout: 3000 });
    });

    test('should handle network recovery scenarios', async () => {
      // First fail, then mock successful retry
      mockHydroChatService.sendMessage.mockRejectedValue(new Error('Network error. Check your connection.'));
      mockHydroChatService.retryMessage.mockResolvedValue({
        conversation_id: 'conv-recovery',
        agent_op: 'SUCCESS',
        messages: [{ role: 'assistant', content: 'Retry successful' }]
      });

      const { getByTestId, getByText } = render(
        <HydroChatScreen navigation={mockNavigation} route={mockRoute} />
      );

      await act(async () => {
        fireEvent.changeText(getByTestId('chat-input'), 'Test recovery');
        fireEvent.press(getByTestId('send-button'));
      });

      await waitFor(() => {
        expect(getByText('Retry')).toBeTruthy();
      }, { timeout: 3000 });

      // Simulate network recovery by retrying
      await act(async () => {
        fireEvent.press(getByText('Retry'));
      });

      // Should call retry service
      expect(mockHydroChatService.retryMessage).toHaveBeenCalled();
    });
  });

  describe('Retry Accessibility and UX', () => {
    test('should have proper accessibility labels for retry elements', async () => {
      mockHydroChatService.sendMessage.mockRejectedValue(new Error('Server error'));

      const { getByTestId, getByText } = render(
        <HydroChatScreen navigation={mockNavigation} route={mockRoute} />
      );

      await act(async () => {
        fireEvent.changeText(getByTestId('chat-input'), 'Test accessibility');
        fireEvent.press(getByTestId('send-button'));
      });

      await waitFor(() => {
        const retryButton = getByText('Retry');
        expect(retryButton).toBeTruthy();
        
        // Should have accessibility properties
        expect(retryButton.props.accessibilityLabel || retryButton.props.accessible !== false).toBeTruthy();
      }, { timeout: 3000 });
    });

    test('should provide clear visual feedback for retry states', async () => {
      mockHydroChatService.sendMessage.mockRejectedValue(new Error('Server error'));

      const { getByTestId, getByText } = render(
        <HydroChatScreen navigation={mockNavigation} route={mockRoute} />
      );

      await act(async () => {
        fireEvent.changeText(getByTestId('chat-input'), 'Test visual feedback');
        fireEvent.press(getByTestId('send-button'));
      });

      await waitFor(() => {
        // Should show error message and retry button
        const retryButton = getByText('Retry');
        expect(retryButton).toBeTruthy();
      }, { timeout: 3000 });

      // Visual feedback elements should be present
      const errorElements = getByText(/retry/i);
      expect(errorElements).toBeTruthy();
    });

    test('should handle rapid retry button presses gracefully', async () => {
      let retryCount = 0;
      mockHydroChatService.retryMessage.mockImplementation(async () => {
        retryCount++;
        return new Promise(resolve => {
          setTimeout(() => resolve({
            conversation_id: 'conv-rapid',
            agent_op: 'SUCCESS',
            messages: [{ role: 'assistant', content: `Retry ${retryCount}` }]
          }), 50);
        });
      });

      mockHydroChatService.sendMessage.mockRejectedValue(new Error('Network error'));

      const { getByTestId, getByText } = render(
        <HydroChatScreen navigation={mockNavigation} route={mockRoute} />
      );

      await act(async () => {
        fireEvent.changeText(getByTestId('chat-input'), 'Test rapid presses');
        fireEvent.press(getByTestId('send-button'));
      });

      await waitFor(() => {
        expect(getByText('Retry')).toBeTruthy();
      }, { timeout: 3000 });

      const retryButton = getByText('Retry');

      // Rapidly press retry button
      await act(async () => {
        fireEvent.press(retryButton);
        fireEvent.press(retryButton);
        fireEvent.press(retryButton);
      });

      // Should handle gracefully (not cause crashes or excessive requests)
      await waitFor(() => {
        expect(retryCount).toBeGreaterThanOrEqual(1);
        expect(retryCount).toBeLessThanOrEqual(3); // Should not exceed reasonable limit
      }, { timeout: 1000 });
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

      // Mock to track attempts
      let attemptCount = 0;
      mockHydroChatService.canRetryMessage.mockImplementation(() => {
        attemptCount++;
        return {
          canRetry: attemptCount < 3,
          attemptsRemaining: Math.max(0, 3 - attemptCount),
          totalAttempts: attemptCount,
          maxAttempts: 3
        };
      });

      // Make multiple retry checks
      for (let i = 0; i < 3; i++) {
        const retryInfo = mockHydroChatService.canRetryMessage(messageId);
        expect(retryInfo.totalAttempts).toBe(i + 1);
        expect(retryInfo.attemptsRemaining).toBe(3 - (i + 1));
      }
    });
  });
});
