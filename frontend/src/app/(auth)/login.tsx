// src/app/(auth)/login.tsx

import React, { useState } from 'react';
import {
  View,
  StyleSheet,
  KeyboardAvoidingView,
  ScrollView,
  Platform,
} from 'react-native';
import { Text, TextInput, Button } from 'react-native-paper';
import { Link, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import ScreenWrapper from '../../components/ScreenWrapper';
import { IconButton } from '../../components/ui';
import apiClient from '../../services/api'; // We'll use the base client
import { useAuth } from '../../context/AuthContext';
import { palette, space, radius, font } from '../../constants/theme';

export default function LoginScreen() {
  const router = useRouter();
  const { signIn } = useAuth();

  // State for input fields
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const goBack = () => {
    if (router.canGoBack()) router.back();
    else router.replace('/(auth)/landing');
  };

  const handleLogin = async () => {
    if (!email || !password) {
      setError('Please enter both email and password.');
      return;
    }

    setError(null);
    setLoading(true);

    // The backend's /token endpoint expects 'x-www-form-urlencoded' data.
    // We create a URLSearchParams object to format the data correctly.
    const formData = new URLSearchParams();
    formData.append('username', email); // The API expects the email in the 'username' field
    formData.append('password', password);

    try {
      const response = await apiClient.post('/auth/token', formData, {
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
      });

      const accessToken = response.data.access_token;
      await signIn(accessToken);
    } catch (error: any) {
      const detail = error.response?.data?.detail;
      const errorMessage =
        typeof detail === 'string' && detail
          ? detail
          : 'Login failed. Please check your credentials.';
      setError(errorMessage);
    } finally {
      setLoading(false);
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
              Welcome back
            </Text>
            <Text style={styles.subtitle}>Log in to see your ride plans and chats.</Text>
          </View>

          <View style={styles.form}>
            <TextInput
              label="Email"
              mode="outlined"
              value={email}
              onChangeText={(v) => {
                setEmail(v);
                if (error) setError(null);
              }}
              keyboardType="email-address"
              autoCapitalize="none"
              autoComplete="email"
              textContentType="emailAddress"
              returnKeyType="next"
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
                if (error) setError(null);
              }}
              secureTextEntry={!showPassword}
              autoCapitalize="none"
              autoComplete="password"
              textContentType="password"
              returnKeyType="go"
              onSubmitEditing={handleLogin}
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

            {error ? (
              <View style={styles.errorBox} accessibilityLiveRegion="polite">
                <Ionicons name="alert-circle" size={18} color={palette.danger} />
                <Text style={styles.errorText}>{error}</Text>
              </View>
            ) : null}

            <Button
              mode="contained"
              onPress={handleLogin}
              loading={loading}
              disabled={loading}
              style={styles.primaryButton}
              contentStyle={styles.buttonContent}
              labelStyle={styles.buttonLabel}
            >
              Log in
            </Button>
          </View>

          <View style={styles.switchRow}>
            <Text style={styles.switchText}>Don&apos;t have an account?</Text>
            <Link href="./register" asChild>
              <Button mode="text" compact disabled={loading} labelStyle={styles.switchLink}>
                Create one
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
