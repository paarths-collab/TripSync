import { useCallback, useEffect, useRef } from 'react';
import { AppState } from 'react-native';
import { useFocusEffect } from 'expo-router';
import { getCurrentPoolingState, type CurrentPoolingState } from '../services/poolingService';
import { createPoolingRecovery } from '../utils/poolingRecovery';

export function usePoolingRecovery(token: string | null, onState: (state: CurrentPoolingState) => void) {
  const onStateRef = useRef(onState);
  const recoveryRef = useRef<ReturnType<typeof createPoolingRecovery<CurrentPoolingState>> | null>(null);
  useEffect(() => { onStateRef.current = onState; }, [onState]);

  useFocusEffect(useCallback(() => {
    if (!token) return;
    const recovery = createPoolingRecovery(
      () => getCurrentPoolingState(token),
      state => onStateRef.current(state),
      () => console.warn('Could not recover pooling state'),
    );
    recoveryRef.current = recovery;
    void recovery.refresh();
    const timer = setInterval(() => {
      if (AppState.currentState === 'active') void recovery.refresh();
    }, 5000);
    const subscription = AppState.addEventListener('change', state => {
      if (state === 'active') void recovery.refresh();
    });
    return () => {
      clearInterval(timer);
      subscription.remove();
      recovery.dispose();
      if (recoveryRef.current === recovery) recoveryRef.current = null;
    };
  }, [token]));

  const invalidate = useCallback(() => { recoveryRef.current?.invalidate(); }, []);
  const runAction = useCallback(<T,>(action: () => Promise<T>): Promise<T> => {
    const recovery = recoveryRef.current;
    return recovery ? recovery.runAction(action) : action();
  }, []);
  return { invalidate, runAction };
}
