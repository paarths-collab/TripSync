// src/app/(auth)/forgot-password.tsx
import React, { useState } from 'react';
import { StyleSheet } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import AuthFormLayout from '../../components/onboarding/AuthFormLayout';
import {
  GENERIC_ERROR_MESSAGE,
  NETWORK_ERROR_MESSAGE,
  messageForCode,
  normaliseEmail,
  validateLoginEmail,
} from '../../components/onboarding/validation';
import { Banner, Button, TextField } from '../../components/ui';
import { space } from '../../constants/theme';
import { AuthError, requestPasswordReset } from '../../services/authService';

export default function ForgotPasswordScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ email?: string }>();
  const [email, setEmail] = useState(params.email ?? '');
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const goBack = () => {
    if (router.canGoBack()) router.back();
    else router.replace('/(auth)/login');
  };

  const submit = async () => {
    if (loading) return;
    const invalid = validateLoginEmail(email);
    setFieldError(invalid);
    if (invalid) return;
    setLoading(true);
    setFormError(null);
    const address = normaliseEmail(email);
    try {
      const res = await requestPasswordReset(address);
      router.push({
        pathname: '/(auth)/reset-password',
        params: { email: address, resend: String(res.resend_after_seconds ?? 60) },
      });
    } catch (error) {
      if (error instanceof AuthError && error.isNetworkError) setFormError(NETWORK_ERROR_MESSAGE);
      else if (error instanceof AuthError && error.status === 429)
        setFormError(messageForCode('too_many_requests', { retryAfterSeconds: error.retryAfterSeconds }));
      else setFormError(GENERIC_ERROR_MESSAGE);
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthFormLayout
      title="Forgot your password?"
      subtitle="Enter the email you signed up with. If it has an account, we’ll send a 6-digit code to reset your password."
      icon="key-outline"
      onBack={goBack}
    >
      <TextField
        label="College email"
        icon="mail-outline"
        value={email}
        onChangeText={(v) => {
          setEmail(v);
          if (fieldError) setFieldError(null);
          if (formError) setFormError(null);
        }}
        error={fieldError}
        placeholder="you@college.ac.in"
        keyboardType="email-address"
        autoCapitalize="none"
        autoCorrect={false}
        autoComplete="email"
        textContentType="username"
        returnKeyType="send"
        onSubmitEditing={submit}
        editable={!loading}
        autoFocus={!params.email}
      />
      {formError ? <Banner tone="danger" icon="alert-circle" text={formError} style={styles.banner} /> : null}
      <Button label="Send code" variant="dark" onPress={submit} loading={loading} />
    </AuthFormLayout>
  );
}

const styles = StyleSheet.create({
  banner: {
    marginBottom: space.md,
  },
});
