// src/components/onboarding/validation.ts
// Client-side checks that mirror the server's sign-up rules, plus friendly text
// for the API's error codes. Pure functions only, so they are easy to test.
import { APP_NAME } from '../../constants/brand';

export const PASSWORD_MIN_LENGTH = 8;
export const PASSWORD_MAX_BYTES = 72;
export const MIN_AGE = 18;
export const CODE_LENGTH = 6;

export function normaliseEmail(value: string): string {
  return value.trim().toLowerCase();
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function isEmailFormat(value: string): boolean {
  return EMAIL_RE.test(normaliseEmail(value));
}

export function emailDomain(value: string): string | null {
  const email = normaliseEmail(value);
  const at = email.lastIndexOf('@');
  return at > 0 && at < email.length - 1 ? email.slice(at + 1) : null;
}

/** The server requires the email's domain to be exactly one of the college's domains. */
export function emailMatchesDomains(value: string, domains: string[]): boolean {
  const domain = emailDomain(value);
  return !!domain && domains.some((d) => d.trim().toLowerCase() === domain);
}

/** "@djsce.ac.in" or "@a.ac.in or @b.ac.in". */
export function formatDomains(domains: string[]): string {
  const list = domains.map((d) => `@${d.trim().toLowerCase()}`);
  if (list.length <= 1) return list[0] ?? '';
  return `${list.slice(0, -1).join(', ')} or ${list[list.length - 1]}`;
}

export function validateFullName(value: string): string | null {
  const name = value.trim();
  if (!name) return 'Enter your full name.';
  if (name.length < 2) return 'Enter your full name.';
  return null;
}

export function validateLoginEmail(value: string): string | null {
  if (!value.trim()) return 'Enter your email.';
  if (!isEmailFormat(value)) return 'Enter a valid email address.';
  return null;
}

export function validateCollegeEmail(
  value: string,
  college: { name: string; email_domains: string[] } | null,
): string | null {
  const basic = validateLoginEmail(value);
  if (basic) return value.trim() ? basic : 'Enter your college email.';
  if (college && college.email_domains.length > 0 && !emailMatchesDomains(value, college.email_domains)) {
    return `Use your ${formatDomains(college.email_domains)} email for ${college.name}.`;
  }
  return null;
}

/** UTF-8 byte length without relying on TextEncoder being available. */
export function utf8ByteLength(value: string): number {
  let bytes = 0;
  for (const ch of value) {
    const cp = ch.codePointAt(0) ?? 0;
    bytes += cp < 0x80 ? 1 : cp < 0x800 ? 2 : cp < 0x10000 ? 3 : 4;
  }
  return bytes;
}

export function validatePassword(value: string): string | null {
  if (!value) return 'Choose a password.';
  if (value.length < PASSWORD_MIN_LENGTH) return `Use at least ${PASSWORD_MIN_LENGTH} characters.`;
  if (utf8ByteLength(value) > PASSWORD_MAX_BYTES) return 'That password is too long. Use a shorter one.';
  return null;
}

const COMMON_PASSWORDS = new Set([
  'password',
  'password1',
  'password123',
  '12345678',
  '123456789',
  '1234567890',
  'qwerty123',
  'qwertyuiop',
  'iloveyou',
  '11111111',
  'abcd1234',
  'letmein1',
]);

export type PasswordStrength = { score: 0 | 1 | 2 | 3 | 4; label: string };

/** A rough strength hint for the meter under the password field. */
export function passwordStrength(value: string): PasswordStrength {
  if (!value) return { score: 0, label: '' };
  if (value.length < PASSWORD_MIN_LENGTH) {
    return { score: 1, label: `Too short. Use at least ${PASSWORD_MIN_LENGTH} characters.` };
  }
  if (COMMON_PASSWORDS.has(value.toLowerCase()))
    return { score: 1, label: 'Too common. Try something less guessable.' };
  const classes = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter((re) => re.test(value)).length;
  let score = 1;
  if (value.length >= 12) score += 1;
  if (classes >= 2) score += 1;
  if (classes >= 3) score += 1;
  const clamped = Math.min(4, score) as PasswordStrength['score'];
  const labels = ['', 'Weak. Add numbers, symbols or more words.', 'Okay', 'Good', 'Strong'];
  return { score: clamped, label: labels[clamped] };
}

export type DateParts = { day: string; month: string; year: string };

function daysInMonth(year: number, month: number): number {
  return new Date(Date.UTC(year, month, 0)).getUTCDate();
}

/** Whole years between the birth date and `today` (local calendar date). */
export function ageOn(year: number, month: number, day: number, today: Date): number {
  let age = today.getFullYear() - year;
  const m = today.getMonth() + 1;
  if (m < month || (m === month && today.getDate() < day)) age -= 1;
  return age;
}

/**
 * Validate DD / MM / YYYY. Returns the ISO date the API expects ("YYYY-MM-DD")
 * or a friendly error.
 */
export function validateDateOfBirth(
  parts: DateParts,
  today: Date = new Date(),
): { iso: string; error: null } | { iso: null; error: string } {
  const { day, month, year } = parts;
  if (!day && !month && !year) return { iso: null, error: 'Enter your date of birth.' };
  if (!/^\d{1,2}$/.test(day) || !/^\d{1,2}$/.test(month) || !/^\d{4}$/.test(year)) {
    return { iso: null, error: 'Enter your date of birth as DD / MM / YYYY.' };
  }
  const d = Number(day);
  const m = Number(month);
  const y = Number(year);
  if (m < 1 || m > 12 || d < 1 || d > daysInMonth(y, m) || y < 1900) {
    return { iso: null, error: 'Enter a real date of birth.' };
  }
  const todayKey = today.getFullYear() * 10000 + (today.getMonth() + 1) * 100 + today.getDate();
  if (y * 10000 + m * 100 + d > todayKey) return { iso: null, error: 'Your date of birth can’t be in the future.' };
  if (ageOn(y, m, d, today) < MIN_AGE) {
    return { iso: null, error: `You need to be ${MIN_AGE} or older to use ${APP_NAME}.` };
  }
  const pad = (n: number) => String(n).padStart(2, '0');
  return { iso: `${y}-${pad(m)}-${pad(d)}`, error: null };
}

/** "45 seconds", "1 minute", "3 minutes". */
export function formatWait(seconds: number): string {
  const s = Math.max(1, Math.ceil(seconds));
  if (s < 60) return `${s} second${s === 1 ? '' : 's'}`;
  const m = Math.ceil(s / 60);
  return `${m} minute${m === 1 ? '' : 's'}`;
}

/** "0:42" for countdowns. */
export function formatCountdown(seconds: number): string {
  const s = Math.max(0, Math.ceil(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

export const NETWORK_ERROR_MESSAGE = "Can't reach the server. Check your connection and try again.";
export const GENERIC_ERROR_MESSAGE = 'Something went wrong. Please try again.';

/** Friendly text for the API's error codes. */
export function messageForCode(
  code: string | null | undefined,
  opts: { retryAfterSeconds?: number | null; collegeName?: string; domains?: string[] } = {},
): string | null {
  switch (code) {
    case 'email_taken':
      return 'An account with this email already exists. Log in instead.';
    case 'email_domain_mismatch':
      return opts.domains && opts.domains.length
        ? `Use your ${formatDomains(opts.domains)} email${opts.collegeName ? ` for ${opts.collegeName}` : ''}.`
        : 'That email isn’t from your college. Use your college email.';
    case 'underage':
      return `You need to be ${MIN_AGE} or older to use ${APP_NAME}.`;
    case 'invalid_date_of_birth':
      return 'Enter a real date of birth.';
    case 'weak_password':
      return `Choose a stronger password with at least ${PASSWORD_MIN_LENGTH} characters.`;
    case 'invalid_college':
      return 'We couldn’t find that college. Choose it again from the list.';
    case 'invalid_code':
      return 'That code isn’t right. Check the email and try again.';
    case 'code_expired':
      return 'That code has expired. Send a new one and try again.';
    case 'too_many_requests':
      return opts.retryAfterSeconds
        ? `Too many attempts. Try again in ${formatWait(opts.retryAfterSeconds)}.`
        : 'Too many attempts. Wait a moment and try again.';
    case 'email_not_verified':
      return 'Verify your email to continue.';
    case 'wrong_password':
      return 'Your current password isn’t right.';
    default:
      return null;
  }
}
