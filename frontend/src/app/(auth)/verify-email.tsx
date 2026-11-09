// src/app/(auth)/verify-email.tsx
// Enter the 6-digit code emailed after sign-up (or when an unverified account
// logs in). A correct code logs the user in.
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { StyleSheet, View } from 'react-native';
import { Text } from 'react-native-paper';
import { useLocalSearchParams, useRouter } from 'expo-router';
import AuthFormLayout from '../../components/onboarding/AuthFormLayout';
import CodeInput, { CodeInputHandle } from '../../components/onboarding/CodeInput';
import LinkButton from '../../components/onboarding/LinkButton';
import { useCountdown } from '../../components/onboarding/useCountdown';
import {
  CODE_LENGTH,
  GENERIC_ERROR_MESSAGE,
  NETWORK_ERROR_MESSAGE,
  formatCountdown,
  formatWait,
  messageForCode,
  normaliseEmail,
} from '../../components/onboarding/validation';
import { Banner, Button } from '../../components/ui';
import { fonts, palette, space, type } from '../../constants/theme';
import { useAuth } from '../../context/AuthContext';
import { AuthError, confirmEmailVerification, requestEmailVerification } from '../../services/authService';

export default function VerifyEmailScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ email?: string; sent?: string; resend?: string }>();
  const { token, user, signIn, signOut } = useAuth();

  const email = normaliseEmail(params.email || user?.email || '');
  const alreadySent = params.sent === '1';

  const [code, setCode] = useState('');
  const [verifying, setVerifying] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const resend = useCountdown(alreadySent ? Math.max(0, Number(params.resend) || 60) : 0);
  const lock = useCountdown(0); // waiting out a rate limit on confirm
  const codeRef = useRef<CodeInputHandle>(null);
  const autoSent = useRef(false);
  const startResend = resend.start;

  const sendCode = useCallback(
    async (auto: boolean) => {
      if (!email) return;
      setSending(true);
      setError(null);
      setNotice(null);
      try {
        const res = await requestEmailVerification(email);
        startResend(res.resend_after_seconds ?? 60);
        setNotice(auto ? null : 'New code sent. It can take a minute to arrive.');
      } catch (e) {
        if (e instanceof AuthError && e.status === 429) {
          // A code went out recently; the timer shows when another can be sent.
          startResend(e.retryAfterSeconds ?? 60);
          if (!auto) setNotice('A code was sent recently. You can ask for another when the timer runs out.');
        } else {
          setError(
            e instanceof AuthError && e.isNetworkError ? NETWORK_ERROR_MESSAGE : 'We couldn’t send a code. Try again.',
          );
        }
      } finally {
        setSending(false);
      }
    },
    [email, startResend],
  );

  // Arrived without a fresh code (e.g. an older account): send one.
  useEffect(() => {
    if (!alreadySent && email && !autoSent.current) {
      autoSent.current = true;
      sendCode(true);
    }
  }, [alreadySent, email, sendCode]);

  const verify = async (value: string) => {
    if (verifying || lock.active) return;
    if (value.length !== CODE_LENGTH) {
      setError(`Enter the ${CODE_LENGTH}-digit code from the email.`);
      codeRef.current?.focus();
      return;
    }
    setVerifying(true);
    setError(null);
    setNotice(null);
    try {
      const { access_token } = await confirmEmailVerification(email, value);
      await signIn(access_token);
      // AuthContext moves on to the location primer.
    } catch (e) {
      if (!(e instanceof AuthError)) {
        setError(e instanceof Error && e.message ? e.message : GENERIC_ERROR_MESSAGE);
      } else if (e.isNetworkError) {
        setError(NETWORK_ERROR_MESSAGE);
      } else if (e.status === 429) {
        lock.start(e.retryAfterSeconds ?? 60);
      } else if (e.code === 'invalid_code' || e.code === 'code_expired') {
        setError(messageForCode(e.code));
        setCode('');
        codeRef.current?.focus();
      } else {
        setError(messageForCode(e.code) ?? GENERIC_ERROR_MESSAGE);
      }
    } finally {
      setVerifying(false);
    }
  };

  const goBack = () => {
    if (router.canGoBack()) router.back();
    else router.replace('/(auth)/welcome');
  };

  if (!email) {
    return (
      <AuthFormLayout
        title="Verify your email"
        subtitle="Log in again so we know which email to verify."
        icon="mail-unread-outline"
        onBack={token ? undefined : goBack}
      >
        <Button label="Go to log in" variant="dark" onPress={() => router.replace('/(auth)/login')} />
      </AuthFormLayout>
    );
  }

  const shownError = lock.active ? `Too many attempts. Try again in ${formatWait(lock.secondsLeft)}.` : error;

  return (
    <AuthFormLayout
      title="Check your email"
      subtitle={
        <Text style={[type.body, styles.subtitle]}>
          Enter the {CODE_LENGTH}-digit code we sent to{' '}
          <Text style={[type.bodyStrong, { color: palette.text, fontFamily: fonts.semibold }]}>{email}</Text>. It
          expires in 10 minutes.
        </Text>
      }
      icon="mail-unread-outline"
      onBack={token ? undefined : goBack}
    >
      <CodeInput
        ref={codeRef}
        value={code}
        onChange={(v) => {
          setCode(v);
          if (error) setError(null);
        }}
        onComplete={verify}
        error={!!shownError}
        autoFocus
      />

      <View style={styles.messages}>
        {shownError ? (
          <Text style={[type.label, { color: palette.danger }]} accessibilityLiveRegion="polite">
            {shownError}
          </Text>
        ) : notice ? (
          <Banner tone="success" icon="checkmark-circle" text={notice} />
        ) : null}
      </View>

      <Button
        label="Verify email"
        variant="dark"
        onPress={() => verify(code)}
        loading={verifying}
        disabled={lock.active}
      />

      <View style={styles.resendRow}>
        <Text style={[type.body, { color: palette.textMuted }]}>Didn’t get it?</Text>
        {resend.active ? (
          <Text style={[type.bodyStrong, styles.timer]} accessibilityLiveRegion="none">
            Resend in {formatCountdown(resend.secondsLeft)}
          </Text>
        ) : (
          <LinkButton
            label={sending ? 'Sending…' : 'Resend code'}
            onPress={() => sendCode(false)}
            disabled={sending || verifying}
          />
        )}
      </View>
      <Text style={[type.caption, styles.tip]}>Check your spam or promotions folder too.</Text>

      <View style={styles.footer}>
        {token ? (
          <LinkButton label="Log out" muted onPress={signOut} />
        ) : (
          <>
            <Text style={[type.body, { color: palette.textMuted }]}>Wrong email?</Text>
            <LinkButton label="Change it" onPress={goBack} />
          </>
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
  messages: {
    minHeight: space.lg,
    marginTop: space.sm,
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
    minHeight: 44,
    textAlignVertical: 'center',
    lineHeight: 44,
    paddingHorizontal: 4,
  },
  tip: {
    color: palette.textMuted,
    textAlign: 'center',
  },
  footer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.xxs,
    marginTop: space.xl,
  },
});
