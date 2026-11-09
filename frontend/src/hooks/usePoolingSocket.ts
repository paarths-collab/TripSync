// src/hooks/usePoolingSocket.ts

import { useState, useEffect, useRef, useCallback } from 'react';
import { MatchedUser } from '../services/poolingService';
import { WS_BASE_URL, joinUrl } from '../constants/config';
import { Alert } from 'react-native';

// Define the shape of messages we expect from the server
interface WebSocketMessage {
  type: 'match_found' | 'connection_request_received' | 'connection_request_sent' | 'connection_approved' | 'connection_rejected' | 'ride_cancelled' | 'chat_message';
  match?: MatchedUser;
  connection_id?: number;
  from_user?: Partial<MatchedUser>;
  to_user?: Partial<MatchedUser>;
  partner?: Partial<MatchedUser>;
  by_user?: Partial<MatchedUser>;
  message?: string;
  // Chat message fields
  sender_id?: number;
  sender_name?: string;
  content?: string;
  created_at?: string;
}

/** ws(s)://host/api/ws/pool, built from WS_BASE_URL (EXPO_PUBLIC_WS_BASE_URL or derived from the API URL). */
export const POOLING_SOCKET_URL = joinUrl(WS_BASE_URL, 'ws/pool');

export function usePoolingSocket(token: string | null) {
  const [isConnected, setIsConnected] = useState(false);
  const [match, setMatch] = useState<MatchedUser | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [connectionUpdate, setConnectionUpdate] = useState<{ type: string; data: any } | null>(null);
  const [chatMessage, setChatMessage] = useState<WebSocketMessage | null>(null);

  // useRef is used to hold a reference to the WebSocket object itself.
  // This prevents it from being recreated on every component re-render.
  const socketRef = useRef<WebSocket | null>(null);

  // This function will be called by our UI to start the connection
  const connect = useCallback(() => {
    if (!token) {
      setError('Cannot connect without an authentication token.');
      return;
    }
    if (socketRef.current) return; // already connected

    // --- Create the WebSocket connection ---
    // We pass the token in the subprotocol array, as our backend expects.
    const ws = new WebSocket(POOLING_SOCKET_URL, ['token', token]);
    socketRef.current = ws;

    ws.onopen = () => {
      if (socketRef.current !== ws) return;
      setIsConnected(true);
      setError(null);
    };

    ws.onmessage = (event) => {
      if (socketRef.current !== ws) return;
      // Never log payloads: they carry names, contact details and trip data.
      let message: WebSocketMessage;
      try {
        message = JSON.parse(event.data);
      } catch {
        console.warn('Ignored a malformed pooling socket message');
        return;
      }
      if (!message || typeof message !== 'object' || typeof message.type !== 'string') return;

      switch (message.type) {
        case 'match_found':
          if (message.match) {
            setMatch(message.match); // A match has been found!
          }
          break;

        case 'connection_request_sent':
          setConnectionUpdate({ type: 'request_sent', data: message });
          break;

        case 'connection_request_received':
          Alert.alert(
            'New trip request',
            `${message.from_user?.full_name || 'A student'} wants to share a trip with you.`,
            [{ text: 'View' }]
          );
          setConnectionUpdate({ type: 'request_received', data: message });
          break;

        case 'connection_approved':
          // Connection approved - both users get partner details
          Alert.alert(
            'Request accepted',
            `You and ${message.partner?.full_name || 'your trip partner'} agreed to share a trip. Sort out the details in chat.`,
            [{ text: 'OK' }]
          );
          setConnectionUpdate({ type: 'approved', data: message });
          break;

        case 'connection_rejected':
          Alert.alert(
            'Request declined',
            `${message.by_user?.full_name || 'The other student'} declined your request.`,
            [{ text: 'OK' }]
          );
          setConnectionUpdate({ type: 'rejected', data: message });
          break;

        case 'ride_cancelled':
          Alert.alert(
            'Trip match ended',
            message.message || 'Your trip partner ended the match.',
            [{ text: 'OK' }]
          );
          setConnectionUpdate({ type: 'cancelled', data: message });
          break;

        case 'chat_message':
          setChatMessage(message);
          break;
      }
    };

    ws.onerror = () => {
      if (socketRef.current !== ws) return;
      console.warn('Pooling socket error');
      setError('A connection error occurred.');
      setIsConnected(false);
    };

    ws.onclose = () => {
      if (socketRef.current !== ws) return;
      setIsConnected(false);
      socketRef.current = null; // Clean up the ref
    };
  }, [token]);

  // This function will be called by our UI to close the connection
  const disconnect = useCallback(() => {
    const socket = socketRef.current;
    socketRef.current = null;
    setIsConnected(false);
    socket?.close();
  }, []);

  // This function clears the match state
  const clearMatch = useCallback(() => {
    setMatch(null);
  }, []);

  // Send a message through WebSocket
  const sendWebSocketMessage = useCallback((message: any) => {
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify(message));
    } else {
      console.warn('Pooling socket is not connected');
    }
  }, []);

  // This useEffect ensures that if the component using the hook unmounts,
  // the WebSocket connection is cleanly closed.
  useEffect(() => {
    setMatch(null);
    setConnectionUpdate(null);
    setChatMessage(null);
    return () => {
      disconnect();
    };
  }, [token, disconnect]);

  return {
    isConnected,
    match,
    error,
    connectionUpdate,
    chatMessage,
    connect,
    disconnect,
    clearMatch,
    sendWebSocketMessage
  };
}
