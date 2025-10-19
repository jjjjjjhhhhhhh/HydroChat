/**
 * Shared Test Utilities: Service Mocks
 * 
 * Centralized mock factory for HydroChat and other services to reduce
 * duplication across test files and improve maintainability.
 * 
 * Usage in test files:
 * ```javascript
 * import { createMockHydroChatService, createMockServices } from '../__setup__/mockServices';
 * 
 * jest.mock('../../../services/hydroChatService', createMockHydroChatService);
 * // or
 * jest.mock('../../../services', createMockServices);
 * ```
 */

/**
 * Creates a mock HydroChat service with all retry functionality
 * @returns {Object} Mock service configuration for jest.mock()
 */
export const createMockHydroChatService = () => ({
  hydroChatService: {
    // Retry configuration constants
    maxRetryAttempts: 3,
    retryDelayBase: 1000,
    
    // Retry state tracking (Maps)
    messageAttempts: new Map(),
    messagesToRetry: new Map(),
    
    // Service methods (all jest.fn())
    sendMessage: jest.fn(),
    retryMessage: jest.fn(),
    canRetryMessage: jest.fn(),
    clearRetryData: jest.fn(),
    clearAllRetryData: jest.fn(),
    getStats: jest.fn(),
  },
});

/**
 * Creates a full services module mock (includes all services)
 * @returns {Object} Mock services configuration for jest.mock()
 */
export const createMockServices = () => {
  const hydroChatMock = createMockHydroChatService();
  
  return {
    ...hydroChatMock,
    
    // Additional service mocks
    sendHydroChatMessage: jest.fn(),
    getHydroChatStats: jest.fn(),
    api: {
      get: jest.fn(),
      post: jest.fn(),
      put: jest.fn(),
      delete: jest.fn(),
    },
    authService: {
      login: jest.fn(),
      logout: jest.fn(),
    },
    patientService: {
      getPatients: jest.fn(),
    },
    scanService: {
      getAllScans: jest.fn(),
    },
  };
};

/**
 * Setup default mock implementations for hydroChatService
 * Call this in beforeEach() to configure common behaviors
 * 
 * @param {Object} mockService - The mocked hydroChatService instance
 * @param {Object} options - Configuration options
 */
export const setupHydroChatServiceMocks = (mockService, options = {}) => {
  const {
    maxRetryAttempts = 3,
    defaultSendResponse = null,
  } = options;
  
  // Setup canRetryMessage implementation
  mockService.canRetryMessage.mockImplementation((messageId) => {
    const hasRetryData = mockService.messagesToRetry.has(messageId);
    const attempts = mockService.messageAttempts.get(messageId) || 0;
    return {
      canRetry: hasRetryData && attempts < mockService.maxRetryAttempts,
      attemptsRemaining: Math.max(0, mockService.maxRetryAttempts - attempts),
      totalAttempts: attempts,
      maxAttempts: mockService.maxRetryAttempts,
      messageId,
    };
  });
  
  // Setup clearRetryData implementation
  mockService.clearRetryData.mockImplementation((messageId) => {
    mockService.messageAttempts.delete(messageId);
    mockService.messagesToRetry.delete(messageId);
  });
  
  // Setup clearAllRetryData implementation
  mockService.clearAllRetryData.mockImplementation(() => {
    mockService.messageAttempts.clear();
    mockService.messagesToRetry.clear();
  });
  
  // Setup retryMessage to track attempts
  mockService.retryMessage.mockImplementation(async (messageId) => {
    const currentAttempts = mockService.messageAttempts.get(messageId) || 0;
    mockService.messageAttempts.set(messageId, currentAttempts + 1);
    
    return {
      success: false,
      error: 'Retry failed',
      messageId: messageId,
      attempt: currentAttempts + 1,
    };
  });
  
  // Setup sendMessage with default or custom response
  const defaultResponse = defaultSendResponse || {
    conversation_id: 'conv-test',
    agent_op: 'SUCCESS',
    messages: [{ role: 'assistant', content: 'Success' }],
  };
  
  mockService.sendMessage.mockImplementation(async (conversationId, message, messageId) => {
    return {
      ...defaultResponse,
      conversation_id: conversationId || defaultResponse.conversation_id,
    };
  });
};

/**
 * Reset all mock service state
 * Call this in beforeEach() to ensure clean state between tests
 * 
 * @param {Object} mockService - The mocked hydroChatService instance
 */
export const resetMockServiceState = (mockService) => {
  // Clear all mocks
  jest.clearAllMocks();
  
  // Reset Maps
  if (mockService.messageAttempts instanceof Map) {
    mockService.messageAttempts.clear();
  }
  if (mockService.messagesToRetry instanceof Map) {
    mockService.messagesToRetry.clear();
  }
};

/**
 * Create a mock navigation object for React Navigation tests
 * @returns {Object} Mock navigation object with common methods
 */
export const createMockNavigation = () => ({
  navigate: jest.fn(),
  goBack: jest.fn(),
  setParams: jest.fn(),
  addListener: jest.fn(),
  removeListener: jest.fn(),
});

/**
 * Create a mock route object for React Navigation tests
 * @param {Object} params - Route parameters
 * @returns {Object} Mock route object
 */
export const createMockRoute = (params = {}) => ({
  params,
  key: 'test-route-key',
  name: 'TestRoute',
});

