// src/app/(auth)/register.tsx

import React, { useState } from 'react';
import {
  StyleSheet,
  Alert,
  Pressable,
  View,
  KeyboardAvoidingView,
  ScrollView,
  Platform,
} from 'react-native';
import { Text, TextInput, Button, Menu } from 'react-native-paper';
import { Link, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import ScreenWrapper from '../../components/ScreenWrapper';
import { IconButton } from '../../components/ui';
import { register } from '../../services/authService';
import { palette, space, radius, font, shadow } from '../../constants/theme';

// List of allowed colleges (must match backend)
const ALLOWED_COLLEGES = [
  'DJSCE',
  'SPIT',
  'VJTI',
  'KJ SOMAIYA COLLEGE OF ENGINEERING',
  'THAKUR COLLEGE OF ENGINEERING',
  'ST. FRANCIS COLLEGE OF ENGINEERING',
];

export default function RegisterScreen() {
  const router = useRouter();

  // State for each input field
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [collegeName, setCollegeName] = useState('');
  const [showPassword, setShowPassword] = useState(false);

  // State for dropdown menu
  const [menuVisible, setMenuVisible] = useState(false);

  // State for loading indicator on the button
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const goBack = () => {
    if (router.canGoBack()) router.back();
    else router.replace('/(auth)/landing');
  };

  const clearError = () => {
    if (error) setError(null);
  };

  const handleRegister = async () => {
    // Basic validation
    if (!fullName || !email || !password || !collegeName) {
      setError('Please fill in all fields.');
      return;
    }

    setError(null);
    setLoading(true); // Show loading spinner on the button
    try {
      await register({
        full_name: fullName,
        email: email,
        password: password,
        college_name: collegeName,
      });

      Alert.alert(
        'Success',
        'Your account has been created successfully!',
        [{ text: 'OK', onPress: () => router.push('./login') }] // Navigate on OK
      );
    } catch (error: any) {
      setError(error?.message || 'Registration failed. Please try again.');
    } finally {
      setLoading(false); // Hide loading spinner
    }
  };

  return (
    <ScreenWrapper>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <ScrollView
          contentContainerStyle={styles.scrollContent}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          <IconButton icon="chevron-back" label="Go back" onPress={goBack} />

          <View style={styles.header}>
            <Text style={styles.title} accessibilityRole="header">
              Create your account
            </Text>
            <Text style={styles.subtitle}>
              Join students from your college to plan shared rides.
            </Text>
          </View>

          <View style={styles.form}>
            <TextInput
              label="Full name"
              mode="outlined"
              value={fullName}
              onChangeText={(v) => {
                setFullName(v);
                clearError();
              }}
              autoCapitalize="words"
              autoComplete="name"
              textContentType="name"
              left={<TextInput.Icon icon="account-outline" />}
              outlineStyle={styles.outline}
              style={styles.input}
            />
            <TextInput
              label="Email"
              mode="outlined"
              value={email}
              onChangeText={(v) => {
                setEmail(v);
                clearError();
              }}
              keyboardType="email-address"
              autoCapitalize="none"
              autoComplete="email"
              textContentType="emailAddress"
              left={<TextInput.Icon icon="email-outline" />}
              outlineStyle={styles.outline}
              style={styles.input}
            />
            <TextInput
              label="Password"
              mode="outlined"
              value={password}
              onChangeText={(v) => {
                setPassword(v);
                clearError();
              }}
              secureTextEntry={!showPassword}
              autoCapitalize="none"
              autoComplete="password-new"
              textContentType="newPassword"
              left={<TextInput.Icon icon="lock-outline" />}
              right={
                <TextInput.Icon
                  icon={showPassword ? 'eye-off' : 'eye'}
                  onPress={() => setShowPassword(!showPassword)}
                  accessibilityLabel={showPassword ? 'Hide password' : 'Show password'}
                />
              }
              outlineStyle={styles.outline}
              style={styles.input}
            />

            {/* College Dropdown */}
            <Menu
              visible={menuVisible}
              onDismiss={() => setMenuVisible(false)}
              anchorPosition="bottom"
              anchor={
                <Pressable
                  onPress={() => setMenuVisible(true)}
                  accessibilityRole="button"
                  accessibilityLabel="Select your college"
                >
                  <View pointerEvents="none">
                    <TextInput
                      label="College"
                      mode="outlined"
                      value={collegeName}
                      editable={false}
                      placeholder="Select your college"
                      left={<TextInput.Icon icon="school-outline" />}
                      right={<TextInput.Icon icon="chevron-down" />}
                      outlineStyle={styles.outline}
                      style={styles.input}
                    />
                  </View>
                </Pressable>
              }
              contentStyle={styles.menuContent}
            >
              {ALLOWED_COLLEGES.map((college) => (
                <Menu.Item
                  key={college}
                  onPress={() => {
                    setCollegeName(college);
                    setMenuVisible(false);
                    clearError();
                  }}
                  title={college}
                  titleStyle={[
                    styles.menuItem,
                    college === collegeName && styles.menuItemSelected,
                  ]}
                />
              ))}
            </Menu>

            {error ? (
              <View style={styles.errorBox} accessibilityLiveRegion="polite">
                <Ionicons name="alert-circle" size={18} color={palette.danger} />
                <Text style={styles.errorText}>{error}</Text>
              </View>
            ) : null}

            <Button
              mode="contained"
              onPress={handleRegister}
              loading={loading}
              disabled={loading}
              style={styles.primaryButton}
              contentStyle={styles.buttonContent}
              labelStyle={styles.buttonLabel}
            >
              Create account
            </Button>
          </View>

          <View style={styles.switchRow}>
            <Text style={styles.switchText}>Already have an account?</Text>
            <Link href="./login" asChild>
              <Button mode="text" compact disabled={loading} labelStyle={styles.switchLink}>
                Log in
              </Button>
            </Link>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </ScreenWrapper>
  );
}

const styles = StyleSheet.create({
  flex: {
    flex: 1,
  },
  scrollContent: {
    flexGrow: 1,
    paddingHorizontal: space.xl,
    paddingTop: space.md,
    paddingBottom: space.xl,
  },
  header: {
    marginTop: space.xl,
    marginBottom: space.xl,
  },
  title: {
    fontSize: 28,
    lineHeight: 34,
    fontWeight: font.bold,
    color: palette.text,
    letterSpacing: -0.3,
  },
  subtitle: {
    marginTop: space.xs,
    fontSize: 15,
    lineHeight: 21,
    color: palette.textMuted,
  },
  form: {
    gap: space.sm,
  },
  input: {
    backgroundColor: palette.surface,
  },
  outline: {
    borderRadius: radius.md,
  },
  menuContent: {
    backgroundColor: palette.surface,
    borderRadius: radius.md,
    maxHeight: 300,
    ...shadow.raised,
  },
  menuItem: {
    fontSize: 14,
    color: palette.text,
  },
  menuItemSelected: {
    color: palette.primary,
    fontWeight: font.semibold,
  },
  errorBox: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: space.xs,
    padding: space.sm,
    borderRadius: radius.md,
    backgroundColor: palette.dangerSoft,
  },
  errorText: {
    flex: 1,
    fontSize: 14,
    lineHeight: 19,
    color: palette.danger,
  },
  primaryButton: {
    marginTop: space.xs,
    borderRadius: radius.md,
  },
  buttonContent: {
    height: 52,
  },
  buttonLabel: {
    fontSize: 16,
    fontWeight: font.semibold,
  },
  switchRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: space.lg,
  },
  switchText: {
    fontSize: 14,
    color: palette.textMuted,
  },
  switchLink: {
    fontSize: 14,
    fontWeight: font.semibold,
  },
});
