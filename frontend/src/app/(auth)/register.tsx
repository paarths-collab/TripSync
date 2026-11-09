// src/app/(auth)/register.tsx
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { StyleSheet, TextInput, View } from 'react-native';
import { Text } from 'react-native-paper';
import { useRouter } from 'expo-router';
import AuthFormLayout from '../../components/onboarding/AuthFormLayout';
import CollegePicker from '../../components/onboarding/CollegePicker';
import DateOfBirthField, { DateOfBirthHandle } from '../../components/onboarding/DateOfBirthField';
import LinkButton from '../../components/onboarding/LinkButton';
import PasswordField from '../../components/onboarding/PasswordField';
import {
  DateParts,
  GENERIC_ERROR_MESSAGE,
  MIN_AGE,
  NETWORK_ERROR_MESSAGE,
  formatDomains,
  messageForCode,
  normaliseEmail,
  validateCollegeEmail,
  validateDateOfBirth,
  validateFullName,
  validatePassword,
} from '../../components/onboarding/validation';
import { Banner, Button, TextField } from '../../components/ui';
import { APP_NAME } from '../../constants/brand';
import { palette, space, type } from '../../constants/theme';
import { AuthError, College, getColleges, register } from '../../services/authService';

type Field = 'fullName' | 'college' | 'email' | 'dob' | 'password';
type Errors = Partial<Record<Field, string | null>>;

export default function RegisterScreen() {
  const router = useRouter();

  const [colleges, setColleges] = useState<College[]>([]);
  const [collegesLoading, setCollegesLoading] = useState(true);
  const [collegesError, setCollegesError] = useState<string | null>(null);

  const [fullName, setFullName] = useState('');
  const [college, setCollege] = useState<College | null>(null);
  const [email, setEmail] = useState('');
  const [dob, setDob] = useState<DateParts>({ day: '', month: '', year: '' });
  const [password, setPassword] = useState('');

  const [touched, setTouched] = useState<Partial<Record<Field, boolean>>>({});
  const [submitted, setSubmitted] = useState(false);
  const [serverErrors, setServerErrors] = useState<Errors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [emailTaken, setEmailTaken] = useState(false);
  const [loading, setLoading] = useState(false);

  const emailRef = useRef<TextInput>(null);
  const dobRef = useRef<DateOfBirthHandle>(null);
  const passwordRef = useRef<TextInput>(null);

  const loadColleges = useCallback(async () => {
    setCollegesLoading(true);
    setCollegesError(null);
    try {
      setColleges(await getColleges());
    } catch (error) {
      setCollegesError(
        error instanceof AuthError && error.isNetworkError ? NETWORK_ERROR_MESSAGE : 'Please try again in a moment.',
      );
    } finally {
      setCollegesLoading(false);
    }
  }, []);

  useEffect(() => {
    loadColleges();
  }, [loadColleges]);

  const clientErrors: Errors = useMemo(
    () => ({
      fullName: validateFullName(fullName),
      college: college ? null : 'Choose your college.',
      email: validateCollegeEmail(email, college),
      dob: validateDateOfBirth(dob).error,
      password: validatePassword(password),
    }),
    [fullName, college, email, dob, password],
  );

  const errorFor = (field: Field) => serverErrors[field] ?? (submitted || touched[field] ? clientErrors[field] : null);

  const touch = (field: Field) => setTouched((t) => (t[field] ? t : { ...t, [field]: true }));

  const clearServer = (field: Field) => {
    if (serverErrors[field]) setServerErrors((e) => ({ ...e, [field]: null }));
    if (field === 'email') setEmailTaken(false);
    if (formError) setFormError(null);
  };

  const goBack = () => {
    if (router.canGoBack()) router.back();
    else router.replace('/(auth)/welcome');
  };

  const submit = async () => {
    if (loading) return;
    setSubmitted(true);
    const hasErrors = Object.values(clientErrors).some(Boolean);
    const dobResult = validateDateOfBirth(dob);
    if (hasErrors || !college || !dobResult.iso) return;

    setLoading(true);
    setFormError(null);
    setServerErrors({});
    setEmailTaken(false);
    const address = normaliseEmail(email);
    try {
      const res = await register({
        full_name: fullName,
        email: address,
        password,
        college_id: college.id,
        date_of_birth: dobResult.iso,
      });
      const sent = res.verification?.sent !== false;
      router.push({
        pathname: '/(auth)/verify-email',
        params: {
          email: res.email || address,
          sent: sent ? '1' : '0',
          resend: String(res.verification?.resend_after_seconds ?? 60),
        },
      });
    } catch (error) {
      if (!(error instanceof AuthError)) {
        setFormError(GENERIC_ERROR_MESSAGE);
      } else if (error.isNetworkError) {
        setFormError(NETWORK_ERROR_MESSAGE);
      } else {
        const message = messageForCode(error.code, {
          retryAfterSeconds: error.retryAfterSeconds,
          collegeName: college.name,
          domains: college.email_domains,
        });
        switch (error.code) {
          case 'email_taken':
            setServerErrors({ email: 'An account with this email already exists.' });
            setEmailTaken(true);
            break;
          case 'email_domain_mismatch':
            setServerErrors({ email: message });
            break;
          case 'underage':
          case 'invalid_date_of_birth':
            setServerErrors({ dob: message });
            break;
          case 'weak_password':
            setServerErrors({ password: message });
            break;
          case 'invalid_college':
            setServerErrors({ college: message });
            setCollege(null);
            loadColleges();
            break;
          default:
            setFormError(
              error.status === 429
                ? messageForCode('too_many_requests', { retryAfterSeconds: error.retryAfterSeconds })
                : message || (error.status === 422 ? 'Check your details and try again.' : GENERIC_ERROR_MESSAGE),
            );
        }
      }
    } finally {
      setLoading(false);
    }
  };

  const domainHint = college?.email_domains.length
    ? `Use your ${formatDomains(college.email_domains)} email`
    : undefined;

  return (
    <AuthFormLayout
      title="Create your account"
      subtitle="Use your college email so you’re matched with students from your campus."
      icon="person-add-outline"
      onBack={goBack}
    >
      <TextField
        label="Full name"
        icon="person-outline"
        value={fullName}
        onChangeText={(v) => {
          setFullName(v);
          clearServer('fullName');
        }}
        onBlur={() => fullName && touch('fullName')}
        error={errorFor('fullName')}
        placeholder="As on your college ID"
        autoCapitalize="words"
        autoComplete="name"
        textContentType="name"
        returnKeyType="next"
        editable={!loading}
      />

      <CollegePicker
        colleges={colleges}
        loading={collegesLoading}
        loadError={collegesError}
        onRetry={loadColleges}
        value={college}
        onChange={(c) => {
          setCollege(c);
          clearServer('college');
          touch('college');
          if (!email) setTimeout(() => emailRef.current?.focus(), 350);
        }}
        error={errorFor('college')}
      />

      <TextField
        ref={emailRef}
        label="College email"
        icon="mail-outline"
        value={email}
        onChangeText={(v) => {
          setEmail(v);
          clearServer('email');
        }}
        onBlur={() => email && touch('email')}
        error={errorFor('email')}
        hint={domainHint}
        placeholder={college?.email_domains[0] ? `you@${college.email_domains[0]}` : 'you@college.ac.in'}
        keyboardType="email-address"
        autoCapitalize="none"
        autoCorrect={false}
        autoComplete="email"
        textContentType="username"
        returnKeyType="next"
        onSubmitEditing={() => dobRef.current?.focus()}
        editable={!loading}
      />
      {emailTaken ? (
        <View style={styles.inlineAction}>
          <LinkButton
            label="Log in instead"
            onPress={() => router.replace({ pathname: '/(auth)/login', params: { email: normaliseEmail(email) } })}
          />
        </View>
      ) : null}

      <DateOfBirthField
        ref={dobRef}
        value={dob}
        onChange={(v) => {
          setDob(v);
          clearServer('dob');
        }}
        onBlur={() => dob.year.length === 4 && touch('dob')}
        onSubmitEditing={() => passwordRef.current?.focus()}
        error={errorFor('dob')}
        hint={`You need to be ${MIN_AGE} or older.`}
      />

      <PasswordField
        ref={passwordRef}
        isNew
        value={password}
        onChangeText={(v) => {
          setPassword(v);
          clearServer('password');
        }}
        onBlur={() => password && touch('password')}
        error={errorFor('password')}
        returnKeyType="done"
        onSubmitEditing={submit}
        editable={!loading}
      />

      {formError ? <Banner tone="danger" icon="alert-circle" text={formError} style={styles.banner} /> : null}

      <Button label="Create account" variant="dark" onPress={submit} loading={loading} style={styles.submit} />

      <Text style={[type.caption, styles.footnote]}>
        {APP_NAME} matches students for shared trips. You arrange and pay for travel yourselves.
      </Text>

      <View style={styles.switchRow}>
        <Text style={[type.body, { color: palette.textMuted }]}>Already have an account?</Text>
        <LinkButton label="Log in" onPress={() => router.replace('/(auth)/login')} disabled={loading} />
      </View>
    </AuthFormLayout>
  );
}

const styles = StyleSheet.create({
  inlineAction: {
    alignItems: 'flex-start',
    marginTop: -space.sm,
    marginBottom: space.sm,
  },
  banner: {
    marginBottom: space.md,
  },
  submit: {
    marginTop: space.xs,
  },
  footnote: {
    color: palette.textMuted,
    textAlign: 'center',
    marginTop: space.md,
  },
  switchRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    flexWrap: 'wrap',
    gap: space.xxs,
    marginTop: space.sm,
  },
});
