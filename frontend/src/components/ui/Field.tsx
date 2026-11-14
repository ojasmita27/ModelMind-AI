import { useId, type InputHTMLAttributes, type TextareaHTMLAttributes } from "react";

const BASE = "block w-full rounded border bg-surface-900 px-3.5 py-2.5 text-sm text-ivory-50 placeholder:text-surface-500 transition-colors focus:border-accent-400 focus:outline-none focus:ring-1 focus:ring-accent-400";

interface Common { label: string; error?: string | null; hint?: string }

function Wrapper({ id, label, error, hint, extra, children }: Common & { id: string; extra?: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between gap-2">
        <label htmlFor={id} className="text-sm font-medium text-ivory-100">{label}</label>
        {extra && <span className="text-xs text-surface-400">{extra}</span>}
      </div>
      {children}
      {hint && !error && <p id={`${id}-hint`} className="mt-1.5 text-xs text-surface-400">{hint}</p>}
      {error && <p id={`${id}-error`} role="alert" className="mt-1.5 text-xs text-red-300">{error}</p>}
    </div>
  );
}

export function TextField({ label, error, hint, className = "", ...rest }: Common & InputHTMLAttributes<HTMLInputElement>) {
  const id = useId();
  const describedBy = error ? `${id}-error` : hint ? `${id}-hint` : undefined;
  return (
    <Wrapper id={id} label={label} error={error} hint={hint}>
      <input id={id} aria-invalid={error ? true : undefined} aria-describedby={describedBy}
        className={`${BASE} ${error ? "border-danger-500" : "border-surface-600"} ${className}`} {...rest} />
    </Wrapper>
  );
}

export function TextArea({ label, error, hint, maxLength, value, className = "", ...rest }: Common & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const id = useId();
  const describedBy = error ? `${id}-error` : hint ? `${id}-hint` : undefined;
  const count = typeof value === "string" ? value.length : 0;
  return (
    <Wrapper id={id} label={label} error={error} hint={hint} extra={maxLength ? `${count}/${maxLength}` : undefined}>
      <textarea id={id} value={value} aria-invalid={error ? true : undefined} aria-describedby={describedBy}
        className={`${BASE} min-h-24 resize-y ${error ? "border-danger-500" : "border-surface-600"} ${className}`} {...rest} />
    </Wrapper>
  );
}
