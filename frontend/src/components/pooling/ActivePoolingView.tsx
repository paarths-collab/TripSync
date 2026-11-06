// src/components/pooling/ActivePoolingView.tsx

import React from 'react';
import { StyleSheet, View } from 'react-native';
import { Text, TextInput, Button } from 'react-native-paper';
import ScreenWrapper from '../ScreenWrapper';
import AutocompleteInput from './AutocompleteInput';
import { AutocompleteSuggestion } from '../../services/locationService';
import { Card } from '../ui';
import { palette, space, radius, font } from '../../constants/theme';

interface ActivePoolingViewProps {
  startLocation: string;
  onStartLocationChange: (text: string) => void;
  onPlaceSelected: (place: AutocompleteSuggestion) => void;
  onSearch: () => void;
  onGoToCollege: () => void;
  isSearchDisabled: boolean; // Disables the search button until a destination is selected
}

export default function ActivePoolingView({
  startLocation,
  onStartLocationChange,
  onPlaceSelected,
  onSearch,
  onGoToCollege,
  isSearchDisabled,
}: ActivePoolingViewProps) {
  return (
    <ScreenWrapper style={styles.container}>
      <Card>
        <Text style={styles.label}>Your location</Text>
        <TextInput
          mode="outlined"
          value={startLocation}
          onChangeText={onStartLocationChange}
          outlineColor={palette.border}
          activeOutlineColor={palette.primary}
          outlineStyle={{ borderRadius: radius.md }}
          style={styles.input}
        />

        <Text style={styles.label}>Where to?</Text>
        <AutocompleteInput label="Destination" onPlaceSelected={onPlaceSelected} />

        <View style={styles.actions}>
          <Button
            mode="outlined"
            onPress={onGoToCollege}
            style={styles.button}
            contentStyle={styles.buttonContent}
          >
            Go to college
          </Button>
          <Button
            mode="contained"
            onPress={onSearch}
            style={styles.button}
            contentStyle={styles.buttonContent}
            disabled={isSearchDisabled}
          >
            Find a ride partner
          </Button>
        </View>
      </Card>
    </ScreenWrapper>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: space.lg, justifyContent: 'center' },
  label: {
    fontSize: 13,
    fontWeight: font.semibold,
    color: palette.textMuted,
    marginBottom: space.xxs,
  },
  input: { marginBottom: space.md, backgroundColor: palette.surface },
  actions: { marginTop: space.md, gap: space.xs },
  button: { borderRadius: radius.md },
  buttonContent: { height: 48 },
});
