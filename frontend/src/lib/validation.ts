/** Client-side checks that mirror the backend rules (the server still validates everything). */
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export const LIMITS = { passwordMin: 8, passwordMax: 128, nameMax: 120, descriptionMax: 2000 } as const;

export function validateEmail(value: string): string | null {
  const v = value.trim();
  if (!v) return "Enter your email address.";
  if (v.length > 254 || !EMAIL_RE.test(v)) return "Enter a valid email address, like name@example.com.";
  return null;
}

export function validateNewPassword(value: string): string | null {
  if (!value) return "Choose a password.";
  if (value.length < LIMITS.passwordMin) return `Use at least ${LIMITS.passwordMin} characters.`;
  if (value.length > LIMITS.passwordMax) return `Use at most ${LIMITS.passwordMax} characters.`;
  return null;
}

export function validateProjectName(value: string): string | null {
  const v = value.trim();
  if (!v) return "Give your project a name.";
  if (v.length > LIMITS.nameMax) return `Keep the name under ${LIMITS.nameMax} characters.`;
  return null;
}

export function validateDescription(value: string): string | null {
  return value.length > LIMITS.descriptionMax ? `Keep the description under ${LIMITS.descriptionMax} characters.` : null;
}
