// src/components/pooling/IdlePoolingView.tsx

import React from 'react';
import { StyleSheet } from 'react-native';
import { Button } from 'react-native-paper';
import ScreenWrapper from '../ScreenWrapper';
import { EmptyState } from '../ui';
import { space, radius, font } from '../../constants/theme';

interface IdlePoolingViewProps {
  onFindPoolers: () => void; // Called when the button is pressed
  isLoading: boolean;
}

export default function IdlePoolingView({ onFindPoolers, isLoading }: IdlePoolingViewProps) {
  return (
    <ScreenWrapper style={styles.container}>
      <EmptyState
        icon="car-outline"
        title="Share a taxi with a classmate"
        body="Find students heading the same way, then book and split the ride yourselves."
        action={
          <Button
            mode="contained"
            onPress={onFindPoolers}
            loading={isLoading}
            disabled={isLoading}
            style={styles.button}
            contentStyle={styles.buttonContent}
            labelStyle={styles.buttonLabel}
          >
            Find ride partners
          </Button>
        }
      />
    </ScreenWrapper>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  button: { borderRadius: radius.md },
  buttonContent: { height: 50, paddingHorizontal: space.md },
  buttonLabel: { fontSize: 16, fontWeight: font.semibold },
});
