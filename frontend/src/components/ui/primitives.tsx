import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Icon, type IconName } from "../icons";

export function Spinner({ className = "h-5 w-5", label }: { className?: string; label?: string }) {
  return (
    <span role="status" className="inline-flex items-center gap-2 text-ivory-300">
      <svg className={`${className} animate-spin`} viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="3" opacity="0.25" />
        <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
      </svg>
      {label ? <span className="text-sm">{label}</span> : <span className="sr-only">Loading</span>}
    </span>
  );
}

type Variant = "primary" | "secondary" | "ghost" | "danger";
const VARIANTS: Record<Variant, string> = {
  primary: "bg-accent-500 text-surface-950 hover:bg-accent-600 disabled:bg-accent-500/50",
  secondary: "bg-surface-800 text-ivory-100 border border-surface-600 hover:bg-surface-700 disabled:opacity-50",
  ghost: "text-ivory-200 hover:bg-surface-800 hover:text-ivory-50 disabled:opacity-50",
  danger: "bg-danger-500 text-white hover:bg-red-600 disabled:bg-danger-500/50",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  loading?: boolean;
  icon?: IconName;
  size?: "sm" | "md";
}

export function Button({ variant = "primary", loading = false, icon, size = "md", className = "", children, disabled, type = "button", ...rest }: ButtonProps) {
  const pad = size === "sm" ? "px-3 py-1.5 text-sm" : "px-4 py-2.5 text-sm";
  return (
    <button type={type} disabled={disabled || loading} aria-busy={loading || undefined}
      className={`inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors disabled:cursor-not-allowed ${pad} ${VARIANTS[variant]} ${className}`} {...rest}>
      {loading ? <Spinner className="h-4 w-4" /> : icon ? <Icon name={icon} className="h-4 w-4" /> : null}
      {children}
    </button>
  );
}

export function IconButton({ icon, label, className = "", ...rest }: { icon: IconName; label: string } & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button type="button" aria-label={label} title={label}
      className={`inline-flex h-9 w-9 items-center justify-center rounded-lg text-ivory-300 transition-colors hover:bg-surface-700 hover:text-ivory-50 ${className}`} {...rest}>
      <Icon name={icon} className="h-4.5 w-4.5" />
    </button>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-lg border border-surface-700 bg-surface-850 ${className}`}>{children}</div>;
}

export function Badge({ children, tone = "soon" }: { children: ReactNode; tone?: "soon" | "live" | "info" | "warn" }) {
  const cls =
    tone === "live"
      ? "border-ok-400/30 bg-ok-400/10 text-ok-400"
      : tone === "info"
        ? "border-ivory-400/30 bg-ivory-400/10 text-ivory-200"
        : "border-warn-400/30 bg-warn-400/10 text-warn-400";
  return <span className={`inline-flex items-center rounded border px-2 py-0.5 text-[10px] font-mono uppercase tracking-wider ${cls}`}>{children}</span>;
}

export function ErrorBanner({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex items-start gap-3 rounded border border-danger-500/40 bg-danger-500/10 p-4 text-sm text-red-200">
      <Icon name="alert" className="mt-0.5 h-5 w-5 shrink-0 text-danger-400" />
      <div className="flex-1">{message}</div>
      {onRetry && <Button variant="secondary" size="sm" onClick={onRetry}>Retry</Button>}
    </div>
  );
}

export function InfoBanner({ children }: { children: ReactNode }) {
  return <div role="status" className="rounded border border-accent-400/30 bg-accent-500/10 p-3 text-sm text-accent-300">{children}</div>;
}

export function EmptyState({ icon, title, children, action }: { icon: IconName; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center rounded border border-dashed border-surface-600 bg-surface-900/50 px-6 py-14 text-center">
      <span className="mb-4 flex h-12 w-12 items-center justify-center rounded bg-surface-800 text-accent-400"><Icon name={icon} className="h-6 w-6" /></span>
      <h3 className="text-base font-semibold text-ivory-50">{title}</h3>
      {children && <p className="mt-1.5 max-w-md text-sm text-ivory-300">{children}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4 border-b border-surface-800 pb-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ivory-50">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-ivory-300">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

export function FullPageSpinner() {
  return <div className="flex h-full min-h-screen items-center justify-center bg-surface-950"><Spinner className="h-7 w-7" label="Loading…" /></div>;
}
