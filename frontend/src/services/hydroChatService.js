import api from './api';

class HydroChatService {
  /**
   * Send a message to HydroChat and get the response
   * @param {string|null} conversationId - The conversation ID (null for new conversations)
   * @param {string} message - The user message
   * @returns {Promise<Object>} The API response
   */
  async sendMessage(conversationId, message) {
    try {
      console.log(`[HydroChatService] Sending message to HydroChat API...`);
      console.log(`[HydroChatService] Conversation ID: ${conversationId || 'new'}`);
      console.log(`[HydroChatService] Message: "${message}"`);
      
      const response = await api.post('/hydrochat/converse/', {
        conversation_id: conversationId,
        message: message.trim(),
      });
      
      console.log(`[HydroChatService] Received response from HydroChat API`);
      console.log(`[HydroChatService] New conversation ID: ${response.data.conversation_id}`);
      console.log(`[HydroChatService] Agent operation: ${response.data.agent_op}`);
      
      return response.data;
    } catch (error) {
      console.error('[HydroChatService] Error sending message:', error);
      
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
