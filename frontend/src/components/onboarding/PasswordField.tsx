// src/components/onboarding/PasswordField.tsx
// Password input with a show/hide toggle and an optional strength meter.
import React, { forwardRef, useState } from 'react';
import { Pressable, StyleSheet, TextInput, TextInputProps, View } from 'react-native';
import { Text } from 'react-native-paper';
import { Ionicons } from '@expo/vector-icons';
import { palette, space, type } from '../../constants/theme';
import { TextField } from '../ui';
import { PASSWORD_MIN_LENGTH, passwordStrength } from './validation';

const METER_COLORS = ['', palette.danger, palette.warning, palette.success, palette.success];

type Props = Omit<TextInputProps, 'secureTextEntry'> & {
  label?: string;
  error?: string | null;
  /** New-password mode: strength meter and password-manager hints for a new password. */
  isNew?: boolean;
};

const PasswordField = forwardRef<TextInput, Props>(function PasswordField(
  { label = 'Password', error, isNew = false, value = '', ...props },
  ref,
) {
  const [visible, setVisible] = useState(false);
  const strength = passwordStrength(value);
  const showMeter = isNew && !!value && !error;

  return (
    <View style={{ marginBottom: space.md }}>
      <TextField
        ref={ref}
        label={label}
        value={value}
        error={error}
        hint={isNew && !value ? `At least ${PASSWORD_MIN_LENGTH} characters.` : undefined}
        icon="lock-closed-outline"
        secureTextEntry={!visible}
        autoCapitalize="none"
        autoCorrect={false}
        autoComplete={isNew ? 'new-password' : 'current-password'}
        textContentType={isNew ? 'newPassword' : 'password'}
        containerStyle={{ marginBottom: 0 }}
        right={
          <Pressable
            onPress={() => setVisible((v) => !v)}
            accessibilityRole="button"
            accessibilityLabel={visible ? 'Hide password' : 'Show password'}
            hitSlop={4}
            style={styles.toggle}
          >
            <Ionicons name={visible ? 'eye-off-outline' : 'eye-outline'} size={22} color={palette.textMuted} />
          </Pressable>
        }
        {...props}
      />
      {showMeter ? (
        <View style={styles.meterWrap} accessibilityLiveRegion="polite">
          <View style={styles.meter}>
            {[1, 2, 3, 4].map((i) => (
              <View
                key={i}
                style={[
                  styles.bar,
                  { backgroundColor: i <= strength.score ? METER_COLORS[strength.score] : palette.border },
                ]}
              />
            ))}
          </View>
          <Text
            style={[type.caption, { color: strength.score <= 1 ? palette.danger : palette.textMuted, marginTop: 6 }]}
          >
            {strength.score >= 2 ? `Strength: ${strength.label}` : strength.label}
          </Text>
        </View>
      ) : null}
    </View>
  );
});

export default PasswordField;

const styles = StyleSheet.create({
  toggle: {
    width: 44,
    height: 44,
    marginRight: -space.xs,
    alignItems: 'center',
    justifyContent: 'center',
  },
  meterWrap: {
    marginTop: space.xs,
  },
  meter: {
    flexDirection: 'row',
    gap: 4,
  },
  bar: {
    flex: 1,
    height: 4,
    borderRadius: 2,
  },
});
