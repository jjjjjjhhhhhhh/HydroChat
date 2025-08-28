import api from './api';

class HydroChatService {
  constructor() {
    // Message retry configuration per Phase 16
    this.maxRetryAttempts = 3;
    this.retryDelayBase = 1000; // 1 second base delay
    
    // Track message attempts for idempotency
    this.messageAttempts = new Map(); // messageId -> attempt count
    this.messagesToRetry = new Map(); // messageId -> { conversationId, message, originalTimestamp }
  }

  /**
   * Send a message to HydroChat and get the response
   * @param {string|null} conversationId - The conversation ID (null for new conversations)
   * @param {string} message - The user message
   * @param {string|null} messageId - Unique message ID for retry tracking
   * @returns {Promise<Object>} The API response
   */
  async sendMessage(conversationId, message, messageId = null) {
    try {
      console.log(`[HydroChatService] Sending message to HydroChat API...`);
      console.log(`[HydroChatService] Conversation ID: ${conversationId || 'new'}`);
      console.log(`[HydroChatService] Message: "${message}"`);
      console.log(`[HydroChatService] Message ID: ${messageId || 'none'}`);
      
      const response = await api.post('/hydrochat/converse/', {
        conversation_id: conversationId,
        message: message.trim(),
        message_id: messageId, // Include for backend idempotency tracking
      });
      
      console.log(`[HydroChatService] Received response from HydroChat API`);
      console.log(`[HydroChatService] New conversation ID: ${response.data.conversation_id}`);
      console.log(`[HydroChatService] Agent operation: ${response.data.agent_op}`);
      
      // Clear any retry tracking for successful message
      if (messageId) {
        this.messageAttempts.delete(messageId);
        this.messagesToRetry.delete(messageId);
      }
      
      return response.data;
    } catch (error) {
      console.error('[HydroChatService] Error sending message:', error);
      
      // Store message for potential retry if messageId provided
      if (messageId) {
        this.messagesToRetry.set(messageId, {
          conversationId,
          message: message.trim(),
          originalTimestamp: Date.now()
        });
      }
      
      // Handle specific error types
      if (error.response?.status === 400) {
        throw new Error(error.response.data?.detail || 'Invalid request');
      } else if (error.response?.status >= 500) {
        throw new Error('Server error. Please try again later.');
      } else if (error.code === 'ECONNABORTED' || error.message.includes('timeout')) {
        throw new Error('Request timed out. Please try again.');
      } else if (error.code === 'ERR_NETWORK') {
        throw new Error('Network error. Check your connection.');
      }
      
      throw new Error('Unable to send message. Please try again.');
    }
  }

  /**
   * Retry a failed message with exponential backoff
   * @param {string} messageId - The message ID to retry
   * @returns {Promise<Object>} The API response
   */
  async retryMessage(messageId) {
    console.log(`[HydroChatService] Attempting to retry message: ${messageId}`);
    
    // Check if we have retry data for this message
    const retryData = this.messagesToRetry.get(messageId);
    if (!retryData) {
      throw new Error('No retry data found for this message');
    }
    
    // Check retry attempt count
    const currentAttempts = this.messageAttempts.get(messageId) || 0;
    if (currentAttempts >= this.maxRetryAttempts) {
      console.error(`[HydroChatService] Max retry attempts (${this.maxRetryAttempts}) reached for message ${messageId}`);
      throw new Error(`Maximum retry attempts (${this.maxRetryAttempts}) exceeded`);
    }
    
    // Increment attempt count
    this.messageAttempts.set(messageId, currentAttempts + 1);
    
    // Calculate exponential backoff delay
    const delay = this.retryDelayBase * Math.pow(2, currentAttempts);
    console.log(`[HydroChatService] Retrying message ${messageId} after ${delay}ms delay (attempt ${currentAttempts + 1}/${this.maxRetryAttempts})`);
    
    // Wait for delay
    await new Promise(resolve => setTimeout(resolve, delay));
    
    try {
      // Attempt the retry
      const result = await this.sendMessage(
        retryData.conversationId,
        retryData.message,
        messageId
      );
      
      console.log(`[HydroChatService] Successfully retried message ${messageId}`);
      return result;
      
    } catch (error) {
      console.error(`[HydroChatService] Retry attempt ${currentAttempts + 1} failed for message ${messageId}:`, error);
      
      // If we haven't reached max attempts, keep the retry data
      if (currentAttempts + 1 < this.maxRetryAttempts) {
        console.log(`[HydroChatService] Will allow ${this.maxRetryAttempts - (currentAttempts + 1)} more retry attempts`);
      } else {
        // Clean up after max attempts
        this.messageAttempts.delete(messageId);
        this.messagesToRetry.delete(messageId);
      }
      
      throw error;
    }
  }

  /**
   * Check if a message can be retried
   * @param {string} messageId - The message ID to check
   * @returns {Object} { canRetry: boolean, attemptsRemaining: number }
   */
  canRetryMessage(messageId) {
    const hasRetryData = this.messagesToRetry.has(messageId);
    const currentAttempts = this.messageAttempts.get(messageId) || 0;
    const attemptsRemaining = Math.max(0, this.maxRetryAttempts - currentAttempts);
    
    return {
      canRetry: hasRetryData && attemptsRemaining > 0,
      attemptsRemaining,
      totalAttempts: currentAttempts,
      maxAttempts: this.maxRetryAttempts
    };
  }

  /**
   * Clear retry data for a specific message
   * @param {string} messageId - The message ID to clear
   */
  clearRetryData(messageId) {
    console.log(`[HydroChatService] Clearing retry data for message ${messageId}`);
    this.messageAttempts.delete(messageId);
    this.messagesToRetry.delete(messageId);
  }

  /**
   * Clear all retry data (useful for conversation resets)
   */
  clearAllRetryData() {
    console.log(`[HydroChatService] Clearing all retry data`);
    this.messageAttempts.clear();
    this.messagesToRetry.clear();
  }

  /**
   * Get conversation statistics (if implemented)
   * @returns {Promise<Object>} Stats response
   */
  async getStats() {
    try {
      console.log('[HydroChatService] Fetching HydroChat stats...');
      const response = await api.get('/hydrochat/stats/');
      return response.data;
    } catch (error) {
      console.error('[HydroChatService] Error fetching stats:', error);
      throw error;
    }
  }
}

export const hydroChatService = new HydroChatService();
export default hydroChatService;
