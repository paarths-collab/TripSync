// src/app/(auth)/reset-password.tsx
// Enter the emailed code and a new password. Success returns to Log in.
import React, { useRef, useState } from 'react';
import { StyleSheet, TextInput, View } from 'react-native';
import { Text } from 'react-native-paper';
import { useLocalSearchParams, useRouter } from 'expo-router';
import AuthFormLayout from '../../components/onboarding/AuthFormLayout';
import CodeInput, { CodeInputHandle } from '../../components/onboarding/CodeInput';
import LinkButton from '../../components/onboarding/LinkButton';
import PasswordField from '../../components/onboarding/PasswordField';
import { useCountdown } from '../../components/onboarding/useCountdown';
import {
  CODE_LENGTH,
  GENERIC_ERROR_MESSAGE,
  NETWORK_ERROR_MESSAGE,
  formatCountdown,
  messageForCode,
  normaliseEmail,
  validatePassword,
} from '../../components/onboarding/validation';
import { Banner, Button } from '../../components/ui';
import { fonts, palette, space, type } from '../../constants/theme';
import { AuthError, requestPasswordReset, resetPassword } from '../../services/authService';

export default function ResetPasswordScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ email?: string; resend?: string }>();
  const email = normaliseEmail(params.email ?? '');

  const [code, setCode] = useState('');
  const [password, setPassword] = useState('');
  const [codeError, setCodeError] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const resend = useCountdown(Math.max(0, Number(params.resend) || 60));
  const codeRef = useRef<CodeInputHandle>(null);
  const passwordRef = useRef<TextInput>(null);

  const goBack = () => {
    if (router.canGoBack()) router.back();
    else router.replace('/(auth)/forgot-password');
  };

  const sendAgain = async () => {
    setSending(true);
    setFormError(null);
    setNotice(null);
    try {
      const res = await requestPasswordReset(email);
      resend.start(res.resend_after_seconds ?? 60);
      setNotice('If that email has an account, a new code is on its way.');
    } catch (error) {
      if (error instanceof AuthError && error.status === 429) {
        resend.start(error.retryAfterSeconds ?? 60);
        setFormError(messageForCode('too_many_requests', { retryAfterSeconds: error.retryAfterSeconds }));
      } else {
        setFormError(
          error instanceof AuthError && error.isNetworkError ? NETWORK_ERROR_MESSAGE : GENERIC_ERROR_MESSAGE,
        );
      }
    } finally {
      setSending(false);
    }
  };

  const submit = async () => {
    if (loading) return;
    const cErr = code.length === CODE_LENGTH ? null : `Enter the ${CODE_LENGTH}-digit code from the email.`;
    const pErr = validatePassword(password);
    setCodeError(cErr);
    setPasswordError(pErr);
    if (cErr || pErr) return;

    setLoading(true);
    setFormError(null);
    setNotice(null);
    try {
      await resetPassword(email, code, password);
      router.dismissTo({ pathname: '/(auth)/login', params: { email, reset: '1' } });
    } catch (error) {
      if (!(error instanceof AuthError)) setFormError(GENERIC_ERROR_MESSAGE);
      else if (error.isNetworkError) setFormError(NETWORK_ERROR_MESSAGE);
      else if (error.code === 'invalid_code' || error.code === 'code_expired') {
        setCodeError(messageForCode(error.code));
        setCode('');
        codeRef.current?.focus();
      } else if (error.code === 'weak_password') setPasswordError(messageForCode(error.code));
      else if (error.status === 429)
        setFormError(messageForCode('too_many_requests', { retryAfterSeconds: error.retryAfterSeconds }));
      else setFormError(messageForCode(error.code) ?? GENERIC_ERROR_MESSAGE);
    } finally {
      setLoading(false);
    }
  };

  if (!email) {
    return (
      <AuthFormLayout
        title="Reset your password"
        subtitle="Start again so we know which email to send the code to."
        icon="key-outline"
        onBack={goBack}
      >
        <Button label="Enter my email" variant="dark" onPress={() => router.replace('/(auth)/forgot-password')} />
      </AuthFormLayout>
    );
  }

  return (
    <AuthFormLayout
      title="Reset your password"
      subtitle={
        <Text style={[type.body, styles.subtitle]}>
          If <Text style={[type.bodyStrong, { color: palette.text, fontFamily: fonts.semibold }]}>{email}</Text> has an
          account, we’ve emailed it a {CODE_LENGTH}-digit code.
        </Text>
      }
      icon="key-outline"
      onBack={goBack}
    >
      <Text style={[type.label, styles.label]}>Code</Text>
      <CodeInput
        ref={codeRef}
        value={code}
        onChange={(v) => {
          setCode(v);
          if (codeError) setCodeError(null);
        }}
        onComplete={() => passwordRef.current?.focus()}
        error={!!codeError}
        autoFocus
      />
      <View style={styles.codeMessage}>
        {codeError ? (
          <Text style={[type.caption, { color: palette.danger }]} accessibilityLiveRegion="polite">
            {codeError}
          </Text>
        ) : null}
      </View>

      <PasswordField
        ref={passwordRef}
        label="New password"
        isNew
        value={password}
        onChangeText={(v) => {
          setPassword(v);
          if (passwordError) setPasswordError(null);
        }}
        error={passwordError}
        returnKeyType="done"
        onSubmitEditing={submit}
        editable={!loading}
      />

      {formError ? <Banner tone="danger" icon="alert-circle" text={formError} style={styles.banner} /> : null}
      {notice && !formError ? (
        <Banner tone="success" icon="checkmark-circle" text={notice} style={styles.banner} />
      ) : null}

      <Button label="Reset password" variant="dark" onPress={submit} loading={loading} />

      <View style={styles.resendRow}>
        <Text style={[type.body, { color: palette.textMuted }]}>No code?</Text>
        {resend.active ? (
          <Text style={[type.bodyStrong, styles.timer]}>Resend in {formatCountdown(resend.secondsLeft)}</Text>
        ) : (
          <LinkButton label={sending ? 'Sending…' : 'Resend code'} onPress={sendAgain} disabled={sending || loading} />
        )}
      </View>
    </AuthFormLayout>
  );
}

const styles = StyleSheet.create({
  subtitle: {
    color: palette.textMuted,
    marginTop: space.xs,
  },
  label: {
    color: palette.textMuted,
    marginBottom: 6,
  },
  codeMessage: {
    minHeight: space.lg,
    marginTop: 4,
    marginBottom: space.xs,
  },
  banner: {
    marginBottom: space.md,
  },
  resendRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    flexWrap: 'wrap',
    gap: space.xxs,
    marginTop: space.lg,
  },
  timer: {
    color: palette.textMuted,
    fontFamily: fonts.semibold,
    lineHeight: 44,
    paddingHorizontal: 4,
  },
});
