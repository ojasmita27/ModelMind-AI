import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { AuthShell } from "../components/AuthShell";
import { TextField } from "../components/ui/Field";
import { Button, InfoBanner } from "../components/ui/primitives";
import { validateEmail } from "../lib/validation";

export default function Login() {
  const { login, notice, clearNotice } = useAuth();
  const navigate = useNavigate();
  const from = (useLocation().state as { from?: string } | null)?.from;
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<{ email?: string | null; password?: string | null; form?: string }>({});
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const found = { email: validateEmail(email), password: password ? null : "Enter your password." };
    if (found.email || found.password) { setErrors(found); return; }
    setErrors({});
    clearNotice();
    setBusy(true);
    try {
      await login(email, password);
      navigate(from && from.startsWith("/app") ? from : "/app", { replace: true });
    } catch (err) {
      setErrors({ form: err instanceof ApiError ? err.message : "Could not sign in. Please try again." });
      setBusy(false);
    }
  }

  return (
    <AuthShell title="Welcome back" subtitle="Sign in to your ModelMind workspace."
      footer={<>New to ModelMind? <Link to="/register" className="font-medium text-accent-400 hover:text-accent-300">Create an account</Link></>}>
      <form onSubmit={onSubmit} noValidate className="space-y-4">
        {notice && <InfoBanner>{notice}</InfoBanner>}
        {errors.form && <p role="alert" className="rounded border border-danger-500/40 bg-danger-500/10 p-3 text-sm text-red-200">{errors.form}</p>}
        <TextField label="Email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} error={errors.email} autoFocus />
        <TextField label="Password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} error={errors.password} />
        <Button type="submit" loading={busy} className="w-full">Sign in</Button>
      </form>
    </AuthShell>
  );
}
