// src/components/onboarding/CollegePicker.tsx
// A field that opens a list of colleges. Colleges without an email domain are
// shown but can't be picked yet, since sign-up needs a college email.
import React, { useMemo, useState } from 'react';
import { FlatList, Modal, Platform, Pressable, StyleSheet, View } from 'react-native';
import { Text } from 'react-native-paper';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { fonts, palette, radius, space, type } from '../../constants/theme';
import { Button, EmptyState, IconButton, LoadingState, SearchBar, Tag } from '../ui';
import type { College } from '../../services/authService';
import { formatDomains } from './validation';

export default function CollegePicker({
  colleges,
  loading,
  loadError,
  onRetry,
  value,
  onChange,
  error,
  hint,
}: {
  colleges: College[];
  loading: boolean;
  loadError: string | null;
  onRetry: () => void;
  value: College | null;
  onChange: (college: College) => void;
  error?: string | null;
  hint?: string;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const insets = useSafeAreaInsets();

  const list = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = q
      ? colleges.filter((c) => c.name.toLowerCase().includes(q) || c.email_domains.some((d) => d.includes(q)))
      : colleges;
    // Colleges people can sign up with first.
    return [...filtered].sort((a, b) => Number(b.email_domains.length > 0) - Number(a.email_domains.length > 0));
  }, [colleges, query]);

  const close = () => {
    setOpen(false);
    setQuery('');
  };

  return (
    <View style={{ marginBottom: space.md }}>
      <Text style={[type.label, { color: palette.textMuted, marginBottom: 6 }]}>College</Text>
      <Pressable
        onPress={() => setOpen(true)}
        accessibilityRole="button"
        accessibilityLabel={value ? `College: ${value.name}. Change college` : 'Choose your college'}
        style={({ pressed }) => [
          styles.field,
          { borderColor: error ? palette.danger : palette.borderStrong },
          pressed && { backgroundColor: palette.surfaceMuted },
        ]}
      >
        <Ionicons name="school-outline" size={20} color={palette.textMuted} style={{ marginRight: space.xs }} />
        <Text style={[type.body, { flex: 1, color: value ? palette.text : palette.textMuted }]} numberOfLines={1}>
          {value ? value.name : 'Choose your college'}
        </Text>
        <Ionicons name="chevron-down" size={20} color={palette.textMuted} />
      </Pressable>
      {error ? (
        <Text style={[type.caption, { color: palette.danger, marginTop: 4 }]} accessibilityLiveRegion="polite">
          {error}
        </Text>
      ) : hint ? (
        <Text style={[type.caption, { color: palette.textMuted, marginTop: 4 }]}>{hint}</Text>
      ) : null}

      <Modal
        visible={open}
        animationType="slide"
        presentationStyle={Platform.OS === 'ios' ? 'pageSheet' : undefined}
        transparent={Platform.OS !== 'ios'}
        onRequestClose={close}
      >
        <View style={[styles.backdrop, Platform.OS === 'ios' && { backgroundColor: palette.background }]}>
          {Platform.OS !== 'ios' ? (
            <Pressable
              style={StyleSheet.absoluteFill}
              onPress={close}
              accessibilityRole="button"
              accessibilityLabel="Close college list"
            />
          ) : null}
          <View
            style={[
              styles.sheet,
              Platform.OS === 'ios'
                ? styles.sheetFull
                : { paddingBottom: insets.bottom + space.md, marginTop: insets.top + space.xxl },
            ]}
          >
            <View style={styles.header}>
              <Text style={[type.title2, { flex: 1 }]} accessibilityRole="header">
                Choose your college
              </Text>
              <IconButton icon="close" label="Close" onPress={close} size={44} round />
            </View>

            {loading ? (
              <LoadingState label="Loading colleges…" />
            ) : loadError ? (
              <EmptyState
                icon="cloud-offline-outline"
                title="Couldn't load colleges"
                body={loadError}
                action={<Button label="Try again" variant="dark" onPress={onRetry} />}
              />
            ) : colleges.length === 0 ? (
              <EmptyState
                icon="school-outline"
                title="No colleges yet"
                body="Sign-ups will open as colleges are added."
              />
            ) : (
              <>
                {colleges.length > 6 ? (
                  <SearchBar
                    value={query}
                    onChangeText={setQuery}
                    placeholder="Search colleges"
                    style={styles.search}
                  />
                ) : null}
                <FlatList
                  data={list}
                  keyExtractor={(c) => String(c.id)}
                  keyboardShouldPersistTaps="handled"
                  contentContainerStyle={{ paddingBottom: space.lg }}
                  ListEmptyComponent={
                    <Text style={[type.body, { color: palette.textMuted, textAlign: 'center', marginTop: space.xl }]}>
                      No colleges match “{query}”.
                    </Text>
                  }
                  renderItem={({ item }) => {
                    const available = item.email_domains.length > 0;
                    const selected = value?.id === item.id;
                    return (
                      <Pressable
                        disabled={!available}
                        onPress={() => {
                          onChange(item);
                          close();
                        }}
                        accessibilityRole="button"
                        accessibilityState={{ disabled: !available, selected }}
                        accessibilityLabel={
                          available
                            ? `${item.name}, ${formatDomains(item.email_domains)} email`
                            : `${item.name}, not available yet`
                        }
                        style={({ pressed }) => [
                          styles.row,
                          selected && { backgroundColor: palette.yellowTint },
                          pressed && { backgroundColor: palette.surfaceMuted },
                        ]}
                      >
                        <View style={{ flex: 1 }}>
                          <Text
                            style={[
                              type.bodyStrong,
                              { fontFamily: fonts.semibold, color: available ? palette.text : palette.textMuted },
                            ]}
                          >
                            {item.name}
                          </Text>
                          <Text style={[type.label, { color: palette.textMuted, marginTop: 2 }]}>
                            {available ? `${formatDomains(item.email_domains)} email` : 'Sign-ups not open yet'}
                          </Text>
                        </View>
                        {selected ? (
                          <Ionicons name="checkmark-circle" size={24} color={palette.ink} />
                        ) : !available ? (
                          <Tag label="Unavailable" />
                        ) : null}
                      </Pressable>
                    );
                  }}
                />
              </>
            )}
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  field: {
    flexDirection: 'row',
    alignItems: 'center',
    minHeight: 56,
    borderRadius: radius.md,
    borderWidth: 1.5,
    backgroundColor: palette.surface,
    paddingHorizontal: space.md,
  },
  backdrop: {
    flex: 1,
    backgroundColor: palette.overlay,
    justifyContent: 'flex-end',
  },
  sheet: {
    backgroundColor: palette.background,
    borderTopLeftRadius: radius.xxl,
    borderTopRightRadius: radius.xxl,
    paddingTop: space.md,
    flexShrink: 1,
    width: '100%',
    maxWidth: 560,
    alignSelf: 'center',
  },
  sheetFull: {
    flex: 1,
    borderTopLeftRadius: 0,
    borderTopRightRadius: 0,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: space.lg,
    paddingBottom: space.sm,
  },
  search: {
    marginHorizontal: space.lg,
    marginBottom: space.sm,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    minHeight: 64,
    paddingHorizontal: space.lg,
    paddingVertical: space.sm,
    gap: space.sm,
  },
});
