import hydroChatService from '../../services/hydroChatService';
import api from '../../services/api';

// Mock the api service
jest.mock('../../services/api', () => ({
  post: jest.fn(),
  get: jest.fn(),
}));

describe('HydroChatService', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('sendMessage', () => {
    it('should send message successfully', async () => {
      const mockResponse = {
        data: {
          conversation_id: 'test-uuid',
          messages: [{ role: 'assistant', content: 'Hello!' }],
          agent_op: 'NONE',
          agent_state: { intent: 'UNKNOWN' }
        }
      };

      api.post.mockResolvedValue(mockResponse);

      const result = await hydroChatService.sendMessage('test-uuid', 'Hello');

      expect(api.post).toHaveBeenCalledWith('/hydrochat/converse/', {
        conversation_id: 'test-uuid',
        message: 'Hello'
      });

      expect(result).toEqual(mockResponse.data);
    });

    it('should handle new conversation (null conversation_id)', async () => {
      const mockResponse = {
        data: {
          conversation_id: 'new-uuid',
          messages: [{ role: 'assistant', content: 'Welcome!' }],
          agent_op: 'NONE',
          agent_state: { intent: 'UNKNOWN' }
        }
      };

      api.post.mockResolvedValue(mockResponse);

      const result = await hydroChatService.sendMessage(null, 'Start chat');

      expect(api.post).toHaveBeenCalledWith('/hydrochat/converse/', {
        conversation_id: null,
        message: 'Start chat'
      });

      expect(result).toEqual(mockResponse.data);
    });

    it('should trim message whitespace', async () => {
      const mockResponse = {
        data: {
          conversation_id: 'test-uuid',
          messages: [{ role: 'assistant', content: 'Got it!' }],
          agent_op: 'NONE',
          agent_state: { intent: 'UNKNOWN' }
        }
      };

      api.post.mockResolvedValue(mockResponse);

      await hydroChatService.sendMessage('test-uuid', '  Hello world  ');

      expect(api.post).toHaveBeenCalledWith('/hydrochat/converse/', {
        conversation_id: 'test-uuid',
        message: 'Hello world'
      });
    });

    it('should include message_id when explicitly provided', async () => {
      const mockResponse = {
        data: {
          conversation_id: 'test-uuid',
          messages: [{ role: 'assistant', content: 'Retry received!' }],
          agent_op: 'NONE',
          agent_state: { intent: 'UNKNOWN' }
        }
      };

      api.post.mockResolvedValue(mockResponse);

      await hydroChatService.sendMessage('test-uuid', 'Hello', 'msg-123');

      expect(api.post).toHaveBeenCalledWith('/hydrochat/converse/', {
        conversation_id: 'test-uuid',
        message: 'Hello',
        message_id: 'msg-123'
      });
    });

    it('should not include message_id when empty string is provided', async () => {
      const mockResponse = {
        data: {
          conversation_id: 'test-uuid',
          messages: [{ role: 'assistant', content: 'Response' }],
          agent_op: 'NONE',
          agent_state: { intent: 'UNKNOWN' }
        }
      };

      api.post.mockResolvedValue(mockResponse);

      await hydroChatService.sendMessage('test-uuid', 'Hello', '');

      expect(api.post).toHaveBeenCalledWith('/hydrochat/converse/', {
        conversation_id: 'test-uuid',
        message: 'Hello'
        // Note: message_id should NOT be included when empty string
      });
    });

    it('should handle 400 validation errors', async () => {
      const mockError = {
        response: {
          status: 400,
          data: { detail: 'Invalid NRIC format' }
        }
      };

      api.post.mockRejectedValue(mockError);

      await expect(hydroChatService.sendMessage('test-uuid', 'invalid input'))
        .rejects.toThrow('Invalid NRIC format');
    });

    it('should handle 400 errors without detail', async () => {
      const mockError = {
        response: {
          status: 400,
          data: {}
        }
      };

      api.post.mockRejectedValue(mockError);

      await expect(hydroChatService.sendMessage('test-uuid', 'invalid input'))
        .rejects.toThrow('Invalid request');
    });

    it('should handle 500 server errors', async () => {
      const mockError = {
        response: { status: 500 }
      };

      api.post.mockRejectedValue(mockError);

      await expect(hydroChatService.sendMessage('test-uuid', 'test'))
        .rejects.toThrow('Server error. Please try again later.');
    });

    it('should handle timeout errors', async () => {
      const mockError = {
        code: 'ECONNABORTED',
        message: 'timeout of 15000ms exceeded'
      };

      api.post.mockRejectedValue(mockError);

      await expect(hydroChatService.sendMessage('test-uuid', 'test'))
        .rejects.toThrow('Request timed out. Please try again.');
    });

    it('should handle network errors', async () => {
      const mockError = {
        code: 'ERR_NETWORK',
        message: 'Network Error'
      };

      api.post.mockRejectedValue(mockError);

      await expect(hydroChatService.sendMessage('test-uuid', 'test'))
        .rejects.toThrow('Network error. Check your connection.');
    });

    it('should handle unknown errors', async () => {
      const mockError = new Error('Unknown error');

      api.post.mockRejectedValue(mockError);

      await expect(hydroChatService.sendMessage('test-uuid', 'test'))
        .rejects.toThrow('Unable to send message. Please try again.');
    });
  });

  describe('getStats', () => {
    it('should fetch stats successfully', async () => {
      const mockResponse = {
        data: {
          active_conversations: 5,
          total_messages: 100,
          successful_operations: 80
        }
      };

      api.get.mockResolvedValue(mockResponse);

      const result = await hydroChatService.getStats();

      expect(api.get).toHaveBeenCalledWith('/hydrochat/stats/');
      expect(result).toEqual(mockResponse.data);
    });

    it('should handle stats fetch error', async () => {
      const mockError = new Error('Stats unavailable');
      api.get.mockRejectedValue(mockError);

      await expect(hydroChatService.getStats()).rejects.toThrow('Stats unavailable');
    });
  });
});
