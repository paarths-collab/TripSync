// src/app/(auth)/login.tsx
import React, { useEffect, useRef, useState } from 'react';
import { StyleSheet, TextInput, View } from 'react-native';
import { Text } from 'react-native-paper';
import { useLocalSearchParams, useRouter } from 'expo-router';
import AuthFormLayout from '../../components/onboarding/AuthFormLayout';
import LinkButton from '../../components/onboarding/LinkButton';
import PasswordField from '../../components/onboarding/PasswordField';
import {
  GENERIC_ERROR_MESSAGE,
  NETWORK_ERROR_MESSAGE,
  messageForCode,
  normaliseEmail,
  validateLoginEmail,
} from '../../components/onboarding/validation';
import { Banner, Button, TextField } from '../../components/ui';
import { APP_NAME } from '../../constants/brand';
import { palette, space, type } from '../../constants/theme';
import { useAuth } from '../../context/AuthContext';
import { AuthError, logIn, requestEmailVerification } from '../../services/authService';

function loginErrorMessage(error: unknown): string {
  if (error instanceof AuthError) {
    if (error.isNetworkError) return NETWORK_ERROR_MESSAGE;
    if (error.status === 401) return 'That email and password don’t match. Try again or reset your password.';
    const code = error.status === 429 ? 'too_many_requests' : error.code;
    return messageForCode(code, { retryAfterSeconds: error.retryAfterSeconds }) ?? GENERIC_ERROR_MESSAGE;
  }
  // signIn() throws a plain Error with readable text if the new session is rejected.
  return error instanceof Error && error.message ? error.message : GENERIC_ERROR_MESSAGE;
}

export default function LoginScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ email?: string; reset?: string }>();
  const { signIn } = useAuth();

  const [email, setEmail] = useState(params.email ?? '');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState<{ email?: string | null; password?: string | null }>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const passwordRef = useRef<TextInput>(null);

  // Coming back from a password reset pre-fills the email and clears the old password.
  useEffect(() => {
    if (params.email) setEmail(params.email);
    if (params.reset === '1') {
      setPassword('');
      setErrors({});
      setFormError(null);
    }
  }, [params.email, params.reset]);

  const goBack = () => {
    if (router.canGoBack()) router.back();
    else router.replace('/(auth)/welcome');
  };

  const goVerify = async (address: string) => {
    let sent = '1';
    let resend = 60;
    try {
      const res = await requestEmailVerification(address);
      resend = res.resend_after_seconds ?? 60;
    } catch (error) {
      if (error instanceof AuthError && error.status === 429) resend = error.retryAfterSeconds ?? 60;
      else sent = '0'; // the verify screen will try again
    }
    router.push({ pathname: '/(auth)/verify-email', params: { email: address, sent, resend: String(resend) } });
  };

  const submit = async () => {
    if (loading) return;
    const emailError = validateLoginEmail(email);
    const passwordError = password ? null : 'Enter your password.';
    setErrors({ email: emailError, password: passwordError });
    if (emailError || passwordError) return;

    setFormError(null);
    setLoading(true);
    const address = normaliseEmail(email);
    try {
      const { access_token } = await logIn(address, password);
      await signIn(access_token);
      // AuthContext moves on to the location primer or the app.
    } catch (error) {
      if (error instanceof AuthError && error.status === 403 && error.code === 'email_not_verified') {
        await goVerify(address);
      } else {
        setFormError(loginErrorMessage(error));
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthFormLayout
      title="Welcome back"
      subtitle="Log in with your college email to find students heading your way."
      icon="log-in-outline"
      onBack={goBack}
    >
      {params.reset === '1' ? (
        <Banner
          tone="success"
          icon="checkmark-circle"
          text="Password updated. Log in with your new password."
          style={styles.banner}
        />
      ) : null}

      <TextField
        label="College email"
        icon="mail-outline"
        value={email}
        onChangeText={(v) => {
          setEmail(v);
          if (errors.email) setErrors((e) => ({ ...e, email: null }));
          if (formError) setFormError(null);
        }}
        error={errors.email}
        placeholder="you@college.ac.in"
        keyboardType="email-address"
        autoCapitalize="none"
        autoCorrect={false}
        autoComplete="email"
        textContentType="username"
        returnKeyType="next"
        onSubmitEditing={() => passwordRef.current?.focus()}
        editable={!loading}
      />

      <PasswordField
        ref={passwordRef}
        value={password}
        onChangeText={(v) => {
          setPassword(v);
          if (errors.password) setErrors((e) => ({ ...e, password: null }));
          if (formError) setFormError(null);
        }}
        error={errors.password}
        returnKeyType="go"
        onSubmitEditing={submit}
        editable={!loading}
      />

      <View style={styles.forgotRow}>
        <LinkButton
          label="Forgot password?"
          onPress={() => router.push({ pathname: '/(auth)/forgot-password', params: email ? { email } : {} })}
          disabled={loading}
        />
      </View>

      {formError ? <Banner tone="danger" icon="alert-circle" text={formError} style={styles.banner} /> : null}

      <Button label="Log in" variant="dark" onPress={submit} loading={loading} />

      <View style={styles.switchRow}>
        <Text style={[type.body, { color: palette.textMuted }]}>New to {APP_NAME}?</Text>
        <LinkButton label="Create account" onPress={() => router.replace('/(auth)/register')} disabled={loading} />
      </View>
    </AuthFormLayout>
  );
}

const styles = StyleSheet.create({
  banner: {
    marginBottom: space.md,
  },
  forgotRow: {
    alignItems: 'flex-end',
    marginTop: -space.xs,
    marginBottom: space.sm,
  },
  switchRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    flexWrap: 'wrap',
    gap: space.xxs,
    marginTop: space.lg,
  },
});
