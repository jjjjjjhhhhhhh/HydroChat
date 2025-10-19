import React, { useState, useEffect, useRef } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  ScrollView,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
  Alert,
  Keyboard,
  TouchableWithoutFeedback,
} from 'react-native';
import Svg, { Path } from 'react-native-svg';
import { hydroChatService } from '../../services';
import { RetryIcon } from '../../components/ui/Icons';
import { useFocusEffect } from '@react-navigation/native';

const TYPING_INDICATOR_ID = '__typing_indicator__';

const TypingIndicator = () => {
  const [dotCount, setDotCount] = useState(1);
  
  useEffect(() => {
    const interval = setInterval(() => {
      setDotCount((prev) => (prev % 3) + 1);
    }, 500);
    
    return () => clearInterval(interval);
  }, []);
  
  const dots = '•'.repeat(dotCount) + ' '.repeat(3 - dotCount);
  
  return (
    <View style={[styles.messageBubble, styles.assistantBubble]}>
      <Text style={[styles.messageText, styles.typingText]} accessibilityLabel="Assistant is typing">
        {dots}
      </Text>
    </View>
  );
};

const MessageBubble = ({ message, isUser, onRetry }) => {
  if (message.id === TYPING_INDICATOR_ID) {
    return <TypingIndicator />;
  }
  
  return (
    <View style={[
      styles.messageBubble,
      isUser ? styles.userBubble : styles.assistantBubble,
      message.error && styles.errorBubble
    ]}>
      <Text style={[
        styles.messageText,
        message.error && styles.errorText
      ]}>
        {message.content}
      </Text>
      {message.error && onRetry && (
        <View style={styles.errorActions}>
          <TouchableOpacity 
            style={[styles.retryButton, message.retrying && styles.retryButtonDisabled]}
            onPress={() => onRetry(message.id)}
            disabled={message.retrying}
          >
            {message.retrying ? (
              <ActivityIndicator size="small" color="#fff" />
            ) : (
              <View style={styles.retryButtonContent}>
                <RetryIcon color="#fff" size={14} />
                <Text style={styles.retryButtonText}>Retry</Text>
              </View>
            )}
          </TouchableOpacity>
          <Text style={styles.retryInfo}>
            {message.retryAttempts ? `Attempt ${message.retryAttempts + 1}` : ''}
          </Text>
        </View>
      )}
    </View>
  );
};

const ProxyMessage = ({ visible, onDismiss }) => {
  if (!visible) return null;
  
  return (
    <TouchableOpacity style={styles.proxyMessage} onPress={onDismiss} activeOpacity={0.7}>
      <Text style={styles.proxyMessageText}>
        Try: "List patients" or "Create patient Jane Tan NRIC S1234567A"
      </Text>
    </TouchableOpacity>
  );
};

const HydroChatScreen = ({ navigation, route }) => {
  const [conversationState, setConversationState] = useState({
    conversationId: null,
    messages: [],
    sending: false,
    typing: false,
    lastAgentOperation: { type: 'NONE', patientId: null }
  });
  
  const [inputText, setInputText] = useState('');
  const [showProxyMessage, setShowProxyMessage] = useState(true);
  const scrollViewRef = useRef(null);
  const textInputRef = useRef(null);
  
  // Auto-scroll to bottom when messages change
  useEffect(() => {
    if (scrollViewRef.current && conversationState.messages.length > 0) {
      setTimeout(() => {
        scrollViewRef.current?.scrollToEnd({ animated: true });
      }, 100);
    }
  }, [conversationState.messages]);
  
  // Handle navigation back with patient list refresh
  useFocusEffect(
    React.useCallback(() => {
      return () => {
        // On screen unfocus (back navigation)
        if (conversationState.lastAgentOperation?.type !== 'NONE') {
          console.log('[HydroChatScreen] Agent performed CRUD operation, triggering patient list refresh');
          // Navigate back with refresh flag
          navigation.navigate('Patients List', { refresh: true });
        }
      };
    }, [conversationState.lastAgentOperation, navigation])
  );
  
  const generateMessageId = () => {
    return Date.now().toString() + Math.random().toString(36).substring(2, 11);
  };
  
  const addMessage = (role, content, options = {}) => {
    const message = {
      id: options.id || generateMessageId(),
      role,
      content,
      pending: options.pending || false,
      error: options.error || false,
    };
    
    setConversationState(prev => ({
      ...prev,
      messages: [...prev.messages, message]
    }));
    
    return message.id;
  };
  
  const removeTypingIndicator = () => {
    setConversationState(prev => ({
      ...prev,
      messages: prev.messages.filter(msg => msg.id !== TYPING_INDICATOR_ID),
      typing: false
    }));
  };
  
  const addTypingIndicator = () => {
    setConversationState(prev => ({
      ...prev,
      messages: [...prev.messages, {
        id: TYPING_INDICATOR_ID,
        role: 'assistant',
        content: '',
        pending: true
      }],
      typing: true
    }));
  };
  
  const handleSendMessage = async () => {
    const message = inputText.trim();
    if (!message || conversationState.sending) {
      return;
    }
    
    await sendMessageWithId(message);
  };
  
  const sendMessageWithId = async (message, messageId = null) => {
    const actualMessageId = messageId || generateMessageId();
    
    // Hide proxy message on first user input
    if (showProxyMessage) {
      setShowProxyMessage(false);
    }
    
    // Add user message (or update existing one for retry)
    if (!messageId) {
      addMessage('user', message, { id: actualMessageId });
      setInputText('');
    }
    
    // Set sending state and add typing indicator
    setConversationState(prev => ({
      ...prev,
      sending: true,
      messages: prev.messages.map(msg => 
        msg.id === actualMessageId 
          ? { ...msg, error: false, retrying: true }
          : msg
      )
    }));
    
    addTypingIndicator();
    
    try {
      console.log(`[HydroChatScreen] Sending message to HydroChat (ID: ${actualMessageId})...`);
      const response = await hydroChatService.sendMessage(
        conversationState.conversationId,
        message,
        actualMessageId
      );
      
      // Remove typing indicator
      removeTypingIndicator();
      
      // Update conversation state with response
      setConversationState(prev => ({
        ...prev,
        conversationId: response.conversation_id,
        sending: false,
        messages: prev.messages.map(msg => 
          msg.id === actualMessageId 
            ? { ...msg, retrying: false }
            : msg
        ),
        lastAgentOperation: {
          type: response.agent_op || 'NONE',
          patientId: response.agent_state?.selected_patient_id || null
        }
      }));
      
      // Add assistant message(s)
      if (response.messages && response.messages.length > 0) {
        response.messages.forEach(msg => {
          if (msg.role === 'assistant') {
            addMessage('assistant', msg.content);
          }
        });
      } else {
        addMessage('assistant', 'I received your message but had no response. Please try again.');
      }
      
      console.log(`[HydroChatScreen] Successfully processed HydroChat response (ID: ${actualMessageId})`);
      
    } catch (error) {
      console.error(`[HydroChatScreen] Error sending message (ID: ${actualMessageId}):`, error);
      
      // Remove typing indicator
      removeTypingIndicator();
      
      // Get retry info
      const retryInfo = hydroChatService.canRetryMessage(actualMessageId);
      
      // Mark user message as failed with retry info
      setConversationState(prev => ({
        ...prev,
        messages: prev.messages.map(msg => 
          msg.id === actualMessageId 
            ? { 
                ...msg, 
                error: true, 
                retrying: false,
                retryAttempts: retryInfo.totalAttempts,
                canRetry: retryInfo.canRetry
              }
            : msg
        ),
        sending: false
      }));
      
      // Show error to user with retry option
      const errorMessage = error.message || 'Unable to send message. Please check your connection and try again.';
      
      if (retryInfo.canRetry) {
        Alert.alert(
          'Message Failed',
          `${errorMessage}\n\nYou have ${retryInfo.attemptsRemaining} retry attempt(s) remaining.`,
          [
            { text: 'Cancel', style: 'cancel' },
            { 
              text: 'Retry Now', 
              onPress: () => handleRetryMessage(actualMessageId)
            }
          ]
        );
      } else {
        Alert.alert(
          'Message Failed',
          `${errorMessage}\n\nMaximum retry attempts reached.`,
          [{ text: 'OK' }]
        );
      }
    }
  };
  
  const handleRetryMessage = async (messageId) => {
    const retryInfo = hydroChatService.canRetryMessage(messageId);
    
    if (!retryInfo.canRetry) {
      Alert.alert(
        'Cannot Retry',
        `Maximum retry attempts (${retryInfo.maxAttempts}) reached for this message.`,
        [{ text: 'OK' }]
      );
      return;
    }
    
    // Find the original message
    const originalMessage = conversationState.messages.find(msg => msg.id === messageId);
    if (!originalMessage) {
      Alert.alert('Error', 'Original message not found', [{ text: 'OK' }]);
      return;
    }
    
    console.log(`[HydroChatScreen] Retrying message ${messageId} (${retryInfo.totalAttempts + 1}/${retryInfo.maxAttempts})`);
    
    try {
      await sendMessageWithId(originalMessage.content, messageId);
    } catch (error) {
      console.error(`[HydroChatScreen] Retry failed for message ${messageId}:`, error);
    }
  };
  
  const handleInputChange = (text) => {
    setInputText(text);
    
    // Hide proxy message when user starts typing
    if (text.trim() && showProxyMessage) {
      setShowProxyMessage(false);
    }
  };
  
  const dismissKeyboard = () => {
    Keyboard.dismiss();
  };
  
  const canSend = inputText.trim().length > 0 && !conversationState.sending;
  
  return (
    <TouchableWithoutFeedback onPress={dismissKeyboard}>
      <KeyboardAvoidingView 
        style={styles.container} 
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 90 : 0}
      >
        {/* Header */}
        <View style={styles.header}>
          <TouchableOpacity 
            style={styles.backButton}
            onPress={() => navigation.goBack()}
            accessibilityLabel="Go back"
          >
            <Svg width="18" height="16" viewBox="0 0 18 16" fill="none">
              <Path d="M16 9.01626C16.5613 9.01626 17.0163 8.56126 17.0163 8C17.0163 7.43874 16.5613 6.98374 16 6.98374L16 9.01626ZM1.2814 7.2814C0.884525 7.67827 0.884525 8.32173 1.2814 8.7186L7.74882 15.186C8.14569 15.5829 8.78915 15.5829 9.18602 15.186C9.58289 14.7891 9.58289 14.1457 9.18602 13.7488L3.4372 8L9.18602 2.25118C9.58289 1.85431 9.58289 1.21085 9.18602 0.813981C8.78915 0.417108 8.14569 0.417108 7.74881 0.813981L1.2814 7.2814ZM16 6.98374L2 6.98375L2 9.01626L16 9.01626L16 6.98374Z" fill="black"/>
            </Svg>
          </TouchableOpacity>
          
          <View style={styles.titleContainer}>
            <Text style={styles.titleHydro}>Hydro</Text>
            <Text style={styles.titleChat}>Chat</Text>
          </View>
          
          <View style={styles.headerSpacer} />
        </View>
        
        {/* Messages Area */}
        <ScrollView 
          ref={scrollViewRef}
          style={styles.messagesContainer}
          contentContainerStyle={styles.messagesContent}
          showsVerticalScrollIndicator={false}
        >
          {conversationState.messages.map((message) => (
            <View
              key={message.id}
              style={message.role === 'user' ? styles.userMessageContainer : styles.assistantMessageContainer}
            >
              <MessageBubble 
                message={message} 
                isUser={message.role === 'user'}
                onRetry={message.role === 'user' ? handleRetryMessage : null}
              />
            </View>
          ))}
        </ScrollView>
        
        {/* Proxy Message */}
        <ProxyMessage 
          visible={showProxyMessage && conversationState.messages.length === 0}
          onDismiss={() => setShowProxyMessage(false)}
        />
        
        {/* Composer */}
        <View style={styles.composerContainer}>
          <View style={styles.composerRow}>
            <TextInput
              ref={textInputRef}
              testID="chat-input"
              style={styles.textInput}
              value={inputText}
              onChangeText={handleInputChange}
              placeholder="Type your message here"
              placeholderTextColor="#707070"
              multiline
              maxLength={500}
              editable={!conversationState.sending}
            />
            
            <TouchableOpacity
              testID="send-button"
              style={[
                styles.sendButton,
                !canSend && styles.sendButtonDisabled
              ]}
              onPress={handleSendMessage}
              disabled={!canSend}
              accessibilityLabel="Send message"
            >
              {conversationState.sending ? (
                <ActivityIndicator size="small" color="white" />
              ) : (
                <Svg width="14" height="13" viewBox="0 0 14 13" fill="none">
                  <Path d="M12.1702 4.6915C13.6982 5.41305 13.6982 7.58695 12.1702 8.3085L3.1893 12.5495C1.47609 13.3585 -0.297068 11.5536 0.542231 9.85502L1.76222 7.386C2.03815 6.82757 2.03815 6.17247 1.76222 5.61404L0.542213 3.14497C-0.297081 1.44639 1.47607 -0.358522 3.18928 0.450492L12.1702 4.6915Z" fill="white"/>
                </Svg>
              )}
            </TouchableOpacity>
          </View>
        </View>
      </KeyboardAvoidingView>
    </TouchableWithoutFeedback>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#FCFFF8',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingTop: 50,
    paddingBottom: 20,
  },
  backButton: {
    width: 40,
    height: 40,
    justifyContent: 'center',
    alignItems: 'center',
  },
  titleContainer: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  titleHydro: {
    fontSize: 22,
    fontWeight: '700',
    color: '#27CFA0',
    fontFamily: 'Urbanist',
  },
  titleChat: {
    fontSize: 22,
    fontWeight: '700',
    color: '#0D6457',
    fontFamily: 'Urbanist',
  },
  headerSpacer: {
    width: 40,
  },
  messagesContainer: {
    flex: 1,
    paddingHorizontal: 20,
  },
  messagesContent: {
    paddingBottom: 10,
  },
  userMessageContainer: {
    alignItems: 'flex-end',
    marginVertical: 2,
  },
  assistantMessageContainer: {
    alignItems: 'flex-start',
    marginVertical: 2,
  },
  messageBubble: {
    borderRadius: 16,
    paddingHorizontal: 16,
    paddingVertical: 12,
    marginVertical: 4,
    maxWidth: '85%',
  },
  userBubble: {
    backgroundColor: '#EEEEEE',
    maxWidth: '78%',
    borderBottomRightRadius: 6,
  },
  assistantBubble: {
    backgroundColor: '#EEEEEE',
    borderBottomLeftRadius: 6,
  },
  errorBubble: {
    borderWidth: 1,
    borderColor: '#FF6B6B',
  },
  messageText: {
    fontSize: 16,
    color: '#707070',
    fontFamily: 'Urbanist',
    lineHeight: 22,
  },
  errorText: {
    color: '#FF6B6B',
  },
  typingText: {
    fontStyle: 'italic',
    fontSize: 18,
  },
  retryButton: {
    marginTop: 8,
    paddingHorizontal: 12,
    paddingVertical: 6,
    backgroundColor: '#27CFA0',
    borderRadius: 8,
    alignSelf: 'flex-start',
    minWidth: 60,
    alignItems: 'center',
  },
  retryButtonDisabled: {
    opacity: 0.7,
    backgroundColor: '#707070',
  },
  retryButtonText: {
    color: 'white',
    fontSize: 12,
    fontWeight: '600',
    marginLeft: 4,
  },
  retryButtonContent: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
  },
  errorActions: {
    marginTop: 8,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  retryInfo: {
    fontSize: 10,
    color: '#707070',
    marginLeft: 8,
    fontStyle: 'italic',
  },
  proxyMessage: {
    marginHorizontal: 20,
    marginBottom: 10,
    padding: 12,
    backgroundColor: '#EEEEEE',
    borderRadius: 16,
    borderBottomLeftRadius: 6,
  },
  proxyMessageText: {
    fontSize: 14,
    color: '#707070',
    fontFamily: 'Urbanist',
    fontStyle: 'italic',
  },
  composerContainer: {
    paddingHorizontal: 20,
    paddingVertical: 8,
    paddingBottom: Platform.OS === 'ios' ? 34 : 8, // Safe area aware
  },
  composerRow: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: 8,
  },
  textInput: {
    flex: 1,
    backgroundColor: '#EEEEEE',
    borderRadius: 13,
    paddingHorizontal: 16,
    paddingVertical: 12,
    fontSize: 16,
    fontFamily: 'Urbanist',
    color: '#707070',
    minHeight: 40,
    maxHeight: 120,
    textAlignVertical: 'top',
  },
  sendButton: {
    width: 44,
    height: 44,
    backgroundColor: '#27CFA0',
    borderRadius: 22,
    justifyContent: 'center',
    alignItems: 'center',
  },
  sendButtonDisabled: {
    opacity: 0.5,
  },
});

export default HydroChatScreen;
