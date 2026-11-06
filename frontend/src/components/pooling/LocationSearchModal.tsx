// src/components/pooling/LocationSearchModal.tsx
import React, { useState } from 'react';
import { View, StyleSheet, SafeAreaView, FlatList } from 'react-native';
import { Modal, Portal, List, Text } from 'react-native-paper';

import AutocompleteInput from './AutocompleteInput';
import { AutocompleteSuggestion } from '../../services/locationService';
import { IconButton } from '../ui';
import { palette, space, radius, font, shadow } from '../../constants/theme';

interface LocationSearchModalProps {
  visible: boolean;
  onDismiss: () => void;
  pickupLocationName: string;
  onPlaceSelected: (place: AutocompleteSuggestion) => void;
}

export default function LocationSearchModal({
  visible,
  onDismiss,
  pickupLocationName,
  onPlaceSelected,
}: LocationSearchModalProps) {
  const [suggestions, setSuggestions] = useState<AutocompleteSuggestion[]>([]);

  const handleSuggestionPress = (suggestion: AutocompleteSuggestion) => {
    console.log('Suggestion pressed:', suggestion);
    setSuggestions([]);
    onPlaceSelected(suggestion);
    // Modal will be closed by the parent (handlePlaceSelected calls setIsSearchModalVisible(false))
  };

  return (
    <Portal>
      <Modal
        visible={visible}
        onDismiss={onDismiss}
        contentContainerStyle={styles.sheet}
        style={styles.modalWrapper}
      >
        <SafeAreaView style={styles.container}>
          <View style={styles.handle} />

          <View style={styles.header}>
            <Text style={styles.title}>Where are you going?</Text>
            <IconButton icon="close" label="Close search" onPress={onDismiss} size={36} />
          </View>

          <View style={styles.pickupRow}>
            <View style={styles.pickupDot} />
            <View style={styles.pickupTextWrap}>
              <Text style={styles.pickupLabel}>Pickup</Text>
              <Text style={styles.pickupText} numberOfLines={1}>
                {pickupLocationName}
              </Text>
            </View>
          </View>

          <View style={styles.inputWrap}>
            <AutocompleteInput
              label=""
              onPlaceSelected={onPlaceSelected}
              onSuggestionsChange={setSuggestions}
            />
          </View>

          <FlatList
            data={suggestions}
            keyExtractor={(item) => item.place_id}
            renderItem={({ item }) => (
              <List.Item
                title={item.structured_formatting?.main_text || item.description}
                description={item.structured_formatting?.secondary_text || undefined}
                onPress={() => handleSuggestionPress(item)}
                titleStyle={styles.itemTitle}
                descriptionStyle={styles.itemDescription}
                titleNumberOfLines={1}
                descriptionNumberOfLines={1}
                style={styles.item}
                left={() => (
                  <View style={styles.itemIcon}>
                    <List.Icon icon="map-marker-outline" color={palette.primary} />
                  </View>
                )}
              />
            )}
            ItemSeparatorComponent={() => <View style={styles.separator} />}
            ListEmptyComponent={
              <Text style={styles.hint}>Type at least 3 letters to see places.</Text>
            }
            style={styles.list}
            keyboardShouldPersistTaps="handled"
          />
        </SafeAreaView>
      </Modal>
    </Portal>
  );
}

const styles = StyleSheet.create({
  modalWrapper: {
    justifyContent: 'flex-end',
  },
  sheet: {
    height: '70%',
    backgroundColor: palette.surface,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    ...shadow.raised,
  },
  container: {
    flex: 1,
  },
  handle: {
    alignSelf: 'center',
    width: 40,
    height: 4,
    borderRadius: radius.pill,
    backgroundColor: palette.border,
    marginTop: space.xs,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: space.lg,
    paddingTop: space.sm,
    paddingBottom: space.xs,
  },
  title: {
    fontSize: 20,
    fontWeight: font.bold,
    color: palette.text,
  },
  pickupRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginHorizontal: space.lg,
    marginTop: space.xs,
    paddingVertical: space.sm,
    paddingHorizontal: space.md,
    borderRadius: radius.md,
    backgroundColor: palette.surfaceMuted,
  },
  pickupDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: palette.success,
  },
  pickupTextWrap: {
    flex: 1,
    marginLeft: space.sm,
  },
  pickupLabel: {
    fontSize: 12,
    color: palette.textMuted,
    marginBottom: 2,
  },
  pickupText: {
    fontSize: 15,
    color: palette.text,
    fontWeight: font.medium,
  },
  inputWrap: {
    paddingHorizontal: space.lg,
    paddingTop: space.sm,
    paddingBottom: space.xs,
  },
  list: {
    flex: 1,
  },
  item: {
    paddingHorizontal: space.sm,
  },
  itemIcon: {
    justifyContent: 'center',
  },
  itemTitle: {
    fontSize: 15,
    fontWeight: font.medium,
    color: palette.text,
  },
  itemDescription: {
    fontSize: 13,
    color: palette.textMuted,
  },
  separator: {
    height: StyleSheet.hairlineWidth,
    backgroundColor: palette.border,
    marginLeft: space.xxxl + space.lg,
    marginRight: space.lg,
  },
  hint: {
    fontSize: 14,
    color: palette.textMuted,
    textAlign: 'center',
    paddingHorizontal: space.xl,
    paddingTop: space.xl,
  },
});
