// src/services/authService.ts
// Calls for sign-up, email verification, log in and password reset. Every call
// throws an AuthError carrying the server's status, error code and retry time,
// so screens can show the right message next to the right field.
import apiClient, { parseApiError } from './api';
const TIMEOUT_MS = 20000;

// The server lowercases and trims emails too; doing it here keeps requests consistent.
const normaliseEmail = (email: string) => email.trim().toLowerCase();

export interface College {
  id: number;
  name: string;
  email_domains: string[];
}

export interface RegisterData {
  email: string;
  full_name: string;
  password: string;
  college_id: number;
  /** YYYY-MM-DD */
  date_of_birth: string;
}

export interface RegisterResponse {
  id: number;
  email: string;
  full_name: string;
  email_verified: boolean;
  verification?: { sent: boolean; resend_after_seconds?: number };
}

export interface CodeSentResponse {
  sent: boolean;
  resend_after_seconds?: number;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export class AuthError extends Error {
  status: number | null;
  code: string | null;
  retryAfterSeconds: number | null;
  isNetworkError: boolean;

  constructor(info: {
    status: number | null;
    code: string | null;
    message: string | null;
    retryAfterSeconds: number | null;
    isNetworkError: boolean;
  }) {
    super(info.message || (info.isNetworkError ? 'Network error' : 'Request failed'));
    this.name = 'AuthError';
    this.status = info.status;
    this.code = info.code;
    this.retryAfterSeconds = info.retryAfterSeconds;
    this.isNetworkError = info.isNetworkError;
  }
}

function toAuthError(error: unknown): AuthError {
  return new AuthError(parseApiError(error));
}

export async function getColleges(): Promise<College[]> {
  try {
    const { data } = await apiClient.get<College[]>('/auth/colleges', { timeout: TIMEOUT_MS });
    return (Array.isArray(data) ? data : []).map((c) => ({
      id: c.id,
      name: c.name,
      email_domains: Array.isArray(c.email_domains) ? c.email_domains : [],
    }));
  } catch (error) {
    throw toAuthError(error);
  }
}

export async function register(input: RegisterData): Promise<RegisterResponse> {
  try {
    const { data } = await apiClient.post<RegisterResponse>(
      '/auth/register',
      { ...input, email: normaliseEmail(input.email), full_name: input.full_name.trim() },
      { timeout: TIMEOUT_MS },
    );
    return data;
  } catch (error) {
    throw toAuthError(error);
  }
}

export async function requestEmailVerification(email: string): Promise<CodeSentResponse> {
  try {
    const { data } = await apiClient.post<CodeSentResponse>(
      '/auth/verify-email/request',
      { email: normaliseEmail(email) },
      { timeout: TIMEOUT_MS },
    );
    return data;
  } catch (error) {
    throw toAuthError(error);
  }
}

export async function confirmEmailVerification(email: string, code: string): Promise<TokenResponse> {
  try {
    const { data } = await apiClient.post<TokenResponse>(
      '/auth/verify-email/confirm',
      { email: normaliseEmail(email), code },
      { timeout: TIMEOUT_MS },
    );
    return data;
  } catch (error) {
    throw toAuthError(error);
  }
}

/** OAuth2 password form: the email goes in `username`. */
export async function logIn(email: string, password: string): Promise<TokenResponse> {
  const body = `username=${encodeURIComponent(normaliseEmail(email))}&password=${encodeURIComponent(password)}`;
  try {
    const { data } = await apiClient.post<TokenResponse>('/auth/token', body, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      timeout: TIMEOUT_MS,
    });
    return data;
  } catch (error) {
    throw toAuthError(error);
  }
}

export async function requestPasswordReset(email: string): Promise<CodeSentResponse> {
  try {
    const { data } = await apiClient.post<CodeSentResponse>(
      '/auth/password/forgot',
      { email: normaliseEmail(email) },
      { timeout: TIMEOUT_MS },
    );
    return data;
  } catch (error) {
    throw toAuthError(error);
  }
}

export async function resetPassword(email: string, code: string, newPassword: string): Promise<void> {
  try {
    await apiClient.post(
      '/auth/password/reset',
      { email: normaliseEmail(email), code, new_password: newPassword },
      { timeout: TIMEOUT_MS },
    );
  } catch (error) {
    throw toAuthError(error);
  }
}

/** Signed-in password change. Old tokens are revoked, so store the returned one. */
export async function changePassword(currentPassword: string, newPassword: string): Promise<TokenResponse> {
  try {
    const { data } = await apiClient.post<TokenResponse>(
      '/auth/password/change',
      { current_password: currentPassword, new_password: newPassword },
      { timeout: TIMEOUT_MS },
    );
    return data;
  } catch (error) {
    throw toAuthError(error);
  }
}
