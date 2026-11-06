// src/hooks/usePoolingSocket.ts

import { useState, useEffect, useRef, useCallback } from 'react';
import { MatchedUser } from '../services/poolingService';
import { API_BASE_URL } from '../constants/config';
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
    if (socketRef.current) {
      console.log('WebSocket already connected.');
      return;
    }

    // Convert the http:// URL to a ws:// URL
    const wsUrl = API_BASE_URL.replace(/^http/, 'ws').replace('/api', '/api/ws/pool');
    console.log('Connecting to WebSocket:', wsUrl);

    // --- Create the WebSocket connection ---
    // We pass the token in the subprotocol array, as our backend expects.
    const ws = new WebSocket(wsUrl, ['token', token]);
    socketRef.current = ws;

    ws.onopen = () => {
      if (socketRef.current !== ws) return;
      console.log('WebSocket connection opened.');
      setIsConnected(true);
      setError(null);
    };

    ws.onmessage = (event) => {
      if (socketRef.current !== ws) return;
      console.log('Received message from server:', event.data);
      try {
        const message: WebSocketMessage = JSON.parse(event.data);
        
        switch (message.type) {
          case 'match_found':
            if (message.match) {
              setMatch(message.match); // A match has been found!
            }
            break;
            
          case 'connection_request_sent':
            // We sent a request successfully - update UI
            console.log('Request sent notification:', message);
            setConnectionUpdate({ type: 'request_sent', data: message });
            break;
            
          case 'connection_request_received':
            // Someone sent us a connection request
            Alert.alert(
              '🚗 Connection Request',
              `${message.from_user?.full_name} wants to pool with you!`,
              [{ text: 'View' }]
            );
            setConnectionUpdate({ type: 'request_received', data: message });
            break;
            
          case 'connection_approved':
            // Connection approved - both users get partner details
            Alert.alert(
              '✅ Connection Approved!',
              `You are now connected with ${message.partner?.full_name}. You can start your ride!`,
              [{ text: 'Great!' }]
            );
            setConnectionUpdate({ type: 'approved', data: message });
            break;
            
          case 'connection_rejected':
            // Our request was rejected
            Alert.alert(
              'Request Declined',
              `${message.by_user?.full_name} declined your connection request.`,
              [{ text: 'OK' }]
            );
            setConnectionUpdate({ type: 'rejected', data: message });
            break;
            
          case 'ride_cancelled':
            // Partner cancelled the ride
            Alert.alert(
              'Ride Cancelled',
              message.message || 'Your pooling partner cancelled the ride.',
              [{ text: 'OK' }]
            );
            setConnectionUpdate({ type: 'cancelled', data: message });
            break;
            
          case 'chat_message':
            // Received a chat message
            console.log('Chat message received:', message);
            setChatMessage(message);
            break;
        }
      } catch (e) {
        console.error('Failed to parse WebSocket message:', e);
      }
    };

    ws.onerror = (e) => {
      if (socketRef.current !== ws) return;
      console.error('WebSocket error:', e);
      setError('A connection error occurred.');
      setIsConnected(false);
    };

    ws.onclose = (e) => {
      if (socketRef.current !== ws) return;
      console.log('WebSocket connection closed:', e.code, e.reason);
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
      console.error('WebSocket is not connected');
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
