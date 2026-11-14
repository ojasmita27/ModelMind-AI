import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { AuthShell } from "../components/AuthShell";
import { TextField } from "../components/ui/Field";
import { Button } from "../components/ui/primitives";
import { LIMITS, validateEmail, validateNewPassword } from "../lib/validation";

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [errors, setErrors] = useState<{ email?: string | null; password?: string | null; confirm?: string | null; form?: string }>({});
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const found = {
      email: validateEmail(email),
      password: validateNewPassword(password),
      confirm: confirm !== password ? "Passwords do not match." : null,
    };
    if (found.email || found.password || found.confirm) { setErrors(found); return; }
    setErrors({});
    setBusy(true);
    try {
      await register(email, password);
      navigate("/app", { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) setErrors({ email: "An account with this email already exists. Try signing in." });
      else if (err instanceof ApiError && Object.keys(err.fieldErrors).length) setErrors({ email: err.fieldErrors.email, password: err.fieldErrors.password });
      else setErrors({ form: err instanceof ApiError ? err.message : "Could not create the account. Please try again." });
      setBusy(false);
    }
  }

  return (
    <AuthShell title="Create your account" subtitle="Start organizing your ML experiments in projects."
      footer={<>Already registered? <Link to="/login" className="font-medium text-accent-400 hover:text-accent-300">Sign in</Link></>}>
      <form onSubmit={onSubmit} noValidate className="space-y-4">
        {errors.form && <p role="alert" className="rounded border border-danger-500/40 bg-danger-500/10 p-3 text-sm text-red-200">{errors.form}</p>}
        <TextField label="Email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} error={errors.email} autoFocus />
        <TextField label="Password" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)}
          error={errors.password} hint={`${LIMITS.passwordMin}-${LIMITS.passwordMax} characters.`} />
        <TextField label="Confirm password" type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} error={errors.confirm} />
        <Button type="submit" loading={busy} className="w-full">Create account</Button>
      </form>
    </AuthShell>
  );
}
