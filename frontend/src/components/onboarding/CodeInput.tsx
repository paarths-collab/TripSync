// src/components/onboarding/CodeInput.tsx
// Six digit boxes backed by one hidden text field, so typing advances box by box
// and pasting or autofilling a whole code just works on every platform.
import React, { forwardRef, useImperativeHandle, useRef, useState } from 'react';
import { Platform, Pressable, StyleSheet, TextInput, View } from 'react-native';
import { Text } from 'react-native-paper';
import { fonts, palette, radius, space } from '../../constants/theme';
import { CODE_LENGTH } from './validation';

export type CodeInputHandle = { focus: () => void };

const CodeInput = forwardRef<
  CodeInputHandle,
  {
    value: string;
    onChange: (code: string) => void;
    onComplete?: (code: string) => void;
    error?: boolean;
    disabled?: boolean;
    autoFocus?: boolean;
  }
>(function CodeInput({ value, onChange, onComplete, error = false, disabled = false, autoFocus = false }, ref) {
  const inputRef = useRef<TextInput>(null);
  const [focused, setFocused] = useState(false);
  useImperativeHandle(ref, () => ({ focus: () => inputRef.current?.focus() }), []);

  const handleChange = (text: string) => {
    const digits = text.replace(/\D/g, '').slice(0, CODE_LENGTH);
    onChange(digits);
    if (digits.length === CODE_LENGTH && digits !== value) onComplete?.(digits);
  };

  const activeIndex = Math.min(value.length, CODE_LENGTH - 1);

  return (
    <Pressable onPress={() => inputRef.current?.focus()} disabled={disabled} accessible={false} style={styles.row}>
      {Array.from({ length: CODE_LENGTH }, (_, i) => {
        const digit = value[i] ?? '';
        const active = focused && i === activeIndex;
        return (
          <View
            key={i}
            importantForAccessibility="no-hide-descendants"
            accessibilityElementsHidden
            style={[
              styles.box,
              digit ? styles.boxFilled : null,
              active ? styles.boxActive : null,
              error ? styles.boxError : null,
              disabled ? styles.boxDisabled : null,
            ]}
          >
            <Text style={styles.digit}>{digit}</Text>
            {active && !digit ? <View style={styles.caret} /> : null}
          </View>
        );
      })}
      <TextInput
        ref={inputRef}
        value={value}
        onChangeText={handleChange}
        editable={!disabled}
        autoFocus={autoFocus}
        keyboardType="number-pad"
        inputMode="numeric"
        textContentType="oneTimeCode"
        autoComplete={Platform.OS === 'android' ? 'sms-otp' : 'one-time-code'}
        caretHidden
        contextMenuHidden={false}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        accessibilityLabel={`${CODE_LENGTH}-digit code`}
        accessibilityHint={value ? `${value.length} of ${CODE_LENGTH} digits entered` : undefined}
        style={styles.hiddenInput}
      />
    </Pressable>
  );
});

export default CodeInput;

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    gap: space.xs,
    position: 'relative',
  },
  box: {
    flex: 1,
    height: 60,
    maxWidth: 64,
    borderRadius: radius.md,
    borderWidth: 1.5,
    borderColor: palette.borderStrong,
    backgroundColor: palette.surface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  boxFilled: {
    borderColor: palette.ink,
  },
  boxActive: {
    borderColor: palette.ink,
    borderWidth: 2,
    backgroundColor: palette.yellowTint,
  },
  boxError: {
    borderColor: palette.danger,
  },
  boxDisabled: {
    opacity: 0.55,
  },
  digit: {
    fontFamily: fonts.bold,
    fontSize: 26,
    lineHeight: 32,
    color: palette.ink,
  },
  caret: {
    position: 'absolute',
    width: 2,
    height: 26,
    borderRadius: 1,
    backgroundColor: palette.ink,
  },
  hiddenInput: {
    ...StyleSheet.absoluteFillObject,
    opacity: 0,
    color: 'transparent',
    fontSize: 1,
  },
});
