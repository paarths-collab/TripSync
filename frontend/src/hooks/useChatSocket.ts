// src/hooks/useChatSocket.ts
import { useState, useEffect, useRef, useCallback } from 'react';
import { WS_BASE_URL } from '../constants/config';

interface ChatMessage {
  type: string;
  message_id?: number;
  connection_id: number;
  sender_id: number;
  sender_name?: string;
  content: string;
  created_at: string;
}

interface UseChatSocketReturn {
  isConnected: boolean;
  chatMessage: ChatMessage | null;
  sendChatMessage: (receiverId: number, connectionId: number, content: string, messageId?: number) => void;
  connect: (token: string) => void;
  disconnect: () => void;
}

export const useChatSocket = (): UseChatSocketReturn => {
  const [isConnected, setIsConnected] = useState(false);
  const [chatMessage, setChatMessage] = useState<ChatMessage | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const connect = useCallback((token: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      console.log('Chat WebSocket already connected');
      return;
    }

    try {
      const ws = new WebSocket(`${WS_BASE_URL}/ws/chat?token=${token}`);

      ws.onopen = () => {
        console.log('Chat WebSocket connected');
        setIsConnected(true);
      };

      ws.onmessage = (event) => {
        try {
          // Never log the payload: it carries message text and user details.
          const data = JSON.parse(event.data);

          if (data.type === 'chat_message') {
            setChatMessage({
              type: data.type,
              message_id: data.message_id,
              connection_id: data.connection_id,
              sender_id: data.sender_id,
              content: data.content,
              created_at: data.created_at,
            });
          }
        } catch {
          console.error('Could not parse a chat WebSocket message');
        }
      };

      // The socket URL carries the auth token, so don't log raw error objects.
      ws.onerror = () => {
        console.error('Chat WebSocket error');
      };

      ws.onclose = () => {
        console.log('Chat WebSocket disconnected');
        setIsConnected(false);
        wsRef.current = null;

        // Auto-reconnect after 3 seconds
        reconnectTimeoutRef.current = setTimeout(() => {
          console.log('Attempting to reconnect chat WebSocket...');
          // Note: reconnection needs token, which should be handled by the component
        }, 3000);
      };

      wsRef.current = ws;
    } catch {
      console.error('Could not open the chat WebSocket');
    }
  }, []);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    
    setIsConnected(false);
  }, []);

  const sendChatMessage = useCallback(
    (receiverId: number, connectionId: number, content: string, messageId?: number) => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        const message = {
          type: 'chat_message',
          receiver_id: receiverId,
          connection_id: connectionId,
          content: content,
          message_id: messageId,
          created_at: new Date().toISOString(),
        };
        wsRef.current.send(JSON.stringify(message));
      } else {
        console.error('Chat WebSocket not connected');
      }
    },
    []
  );

  useEffect(() => {
    return () => {
      disconnect();
    };
  }, [disconnect]);

  return {
    isConnected,
    chatMessage,
    sendChatMessage,
    connect,
    disconnect,
  };
};
