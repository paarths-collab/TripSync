// src/components/pooling/RideRequestSheet.tsx
import React from 'react';
import { View, StyleSheet } from 'react-native';
import { Text, TextInput, Button, Portal, Modal } from 'react-native-paper';
import { AutocompleteSuggestion } from '../../services/locationService';
import AutocompleteInput from './AutocompleteInput';
import { palette, space, radius, font, shadow } from '../../constants/theme';

interface RideRequestSheetProps {
  visible: boolean;
  onClose: () => void;
  startLocation: string;
  onPlaceSelected: (place: AutocompleteSuggestion) => void;
  onSearch: () => void;
  isSearchDisabled: boolean;
}

export default function RideRequestSheet({
  visible,
  onClose,
  startLocation,
  onPlaceSelected,
  onSearch,
  isSearchDisabled,
}: RideRequestSheetProps) {
  return (
    <Portal>
      <Modal
        visible={visible}
        onDismiss={onClose}
        style={styles.modalWrapper}
        contentContainerStyle={styles.sheet}
      >
        <View style={styles.handle} />
        <Text style={styles.title}>Plan your ride</Text>

        <TextInput
          mode="outlined"
          label="From"
          value={startLocation}
          disabled
          outlineColor={palette.border}
          outlineStyle={{ borderRadius: radius.md }}
          style={styles.input}
          left={<TextInput.Icon icon="map-marker-circle" color={palette.success} />}
        />

        <AutocompleteInput label="To" onPlaceSelected={onPlaceSelected} />

        <Button
          mode="contained"
          onPress={onSearch}
          disabled={isSearchDisabled}
          style={styles.button}
          contentStyle={styles.buttonContent}
          labelStyle={styles.buttonLabel}
        >
          Find a ride partner
        </Button>
      </Modal>
    </Portal>
  );
}

const styles = StyleSheet.create({
  modalWrapper: {
    justifyContent: 'flex-end',
  },
  sheet: {
    backgroundColor: palette.surface,
    paddingHorizontal: space.lg,
    paddingBottom: space.xl,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    ...shadow.raised,
  },
  handle: {
    alignSelf: 'center',
    width: 40,
    height: 4,
    borderRadius: radius.pill,
    backgroundColor: palette.border,
    marginTop: space.xs,
    marginBottom: space.md,
  },
  title: {
    fontSize: 20,
    fontWeight: font.bold,
    color: palette.text,
    marginBottom: space.md,
  },
  input: {
    marginBottom: space.sm,
    backgroundColor: palette.surface,
  },
  button: {
    marginTop: space.lg,
    borderRadius: radius.md,
  },
  buttonContent: { height: 50 },
  buttonLabel: { fontSize: 16, fontWeight: font.semibold },
});
