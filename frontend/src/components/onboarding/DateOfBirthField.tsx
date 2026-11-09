// src/components/onboarding/DateOfBirthField.tsx
// Date of birth as three numeric boxes (DD / MM / YYYY) that advance on their
// own, so there is no date-picker dependency.
import React, { forwardRef, useImperativeHandle, useRef, useState } from 'react';
import { NativeSyntheticEvent, StyleSheet, TextInput, TextInputKeyPressEventData, View } from 'react-native';
import { Text } from 'react-native-paper';
import { palette, radius, space, type } from '../../constants/theme';
import type { DateParts } from './validation';

export type DateOfBirthHandle = { focus: () => void };

type Part = keyof DateParts;

const FIELDS: { key: Part; placeholder: string; label: string; max: number; flex: number }[] = [
  { key: 'day', placeholder: 'DD', label: 'Day of birth', max: 2, flex: 1 },
  { key: 'month', placeholder: 'MM', label: 'Month of birth', max: 2, flex: 1 },
  { key: 'year', placeholder: 'YYYY', label: 'Year of birth', max: 4, flex: 1.5 },
];

const DateOfBirthField = forwardRef<
  DateOfBirthHandle,
  {
    value: DateParts;
    onChange: (value: DateParts) => void;
    onBlur?: () => void;
    onSubmitEditing?: () => void;
    error?: string | null;
    hint?: string;
  }
>(function DateOfBirthField({ value, onChange, onBlur, onSubmitEditing, error, hint }, ref) {
  const refs = {
    day: useRef<TextInput>(null),
    month: useRef<TextInput>(null),
    year: useRef<TextInput>(null),
  };
  const [focused, setFocused] = useState<Part | null>(null);
  useImperativeHandle(ref, () => ({ focus: () => refs.day.current?.focus() }));

  const setPart = (key: Part, raw: string) => {
    let text = raw.replace(/\D/g, '');
    // "4" can only be the start of "04" for a day, and "2" of "02" for a month.
    if (key === 'day' && text.length === 1 && Number(text) > 3) text = `0${text}`;
    if (key === 'month' && text.length === 1 && Number(text) > 1) text = `0${text}`;
    const max = FIELDS.find((f) => f.key === key)!.max;
    text = text.slice(0, max);
    onChange({ ...value, [key]: text });
    if (text.length === max) {
      if (key === 'day') refs.month.current?.focus();
      else if (key === 'month') refs.year.current?.focus();
    }
  };

  const handleKey = (key: Part) => (e: NativeSyntheticEvent<TextInputKeyPressEventData>) => {
    if (e.nativeEvent.key !== 'Backspace' || value[key]) return;
    if (key === 'month') refs.day.current?.focus();
    if (key === 'year') refs.month.current?.focus();
  };

  return (
    <View style={{ marginBottom: space.md }}>
      <Text style={[type.label, { color: palette.textMuted, marginBottom: 6 }]}>Date of birth</Text>
      <View style={styles.row}>
        {FIELDS.map((f, i) => (
          <React.Fragment key={f.key}>
            {i > 0 ? <Text style={[type.title3, styles.slash]}>/</Text> : null}
            <View style={{ flex: f.flex, minWidth: 0 }}>
              <TextInput
                ref={refs[f.key]}
                value={value[f.key]}
                onChangeText={(t) => setPart(f.key, t)}
                onKeyPress={handleKey(f.key)}
                placeholder={f.placeholder}
                placeholderTextColor={palette.textMuted}
                keyboardType="number-pad"
                inputMode="numeric"
                maxLength={f.key === 'year' ? 4 : 2}
                returnKeyType={f.key === 'year' ? 'next' : 'default'}
                onSubmitEditing={f.key === 'year' ? onSubmitEditing : undefined}
                autoComplete={
                  f.key === 'day' ? 'birthdate-day' : f.key === 'month' ? 'birthdate-month' : 'birthdate-year'
                }
                accessibilityLabel={f.label}
                onFocus={() => setFocused(f.key)}
                onBlur={() => {
                  setFocused(null);
                  onBlur?.();
                }}
                style={[
                  styles.box,
                  { borderColor: error ? palette.danger : focused === f.key ? palette.ink : palette.borderStrong },
                  focused === f.key && { borderWidth: 2 },
                ]}
              />
            </View>
          </React.Fragment>
        ))}
      </View>
      {error ? (
        <Text style={[type.caption, { color: palette.danger, marginTop: 4 }]} accessibilityLiveRegion="polite">
          {error}
        </Text>
      ) : hint ? (
        <Text style={[type.caption, { color: palette.textMuted, marginTop: 4 }]}>{hint}</Text>
      ) : null}
    </View>
  );
});

export default DateOfBirthField;

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  slash: {
    color: palette.textMuted,
    marginHorizontal: space.xs,
  },
  box: {
    width: '100%',
    outlineWidth: 0, // web: the border already shows focus
    minHeight: 56,
    borderRadius: radius.md,
    borderWidth: 1.5,
    backgroundColor: palette.surface,
    paddingHorizontal: space.sm,
    textAlign: 'center',
    ...type.title3,
    color: palette.text,
  },
});
