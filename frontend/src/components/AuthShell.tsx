import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { TAGLINE } from "../config";
import { Icon } from "./icons";
import { Logo } from "./Logo";

const POINTS = [
  "Real data processing and model training. No hardcoded metrics.",
  "Leakage-safe evaluation with an untouched final test set.",
  "Evidence-based diagnostics, never unsupported causal claims.",
];

export function AuthShell({ title, subtitle, children, footer }: { title: string; subtitle: string; children: ReactNode; footer: ReactNode }) {
  return (
    <div className="grid min-h-screen bg-surface-950 lg:grid-cols-2">
      <section className="relative hidden overflow-hidden border-r border-surface-700 bg-surface-900 p-12 lg:flex lg:flex-col lg:justify-between">
        <div className="bg-grid pointer-events-none absolute inset-0" aria-hidden="true" />
        <div className="relative"><Logo /></div>
        <div className="relative max-w-md">
          <p className="text-3xl font-semibold leading-tight tracking-tight text-ivory-50">{TAGLINE}</p>
          <ul className="mt-8 space-y-4">
            {POINTS.map((p) => (
              <li key={p} className="flex gap-3 text-sm text-ivory-200"><Icon name="shield" className="mt-0.5 h-5 w-5 shrink-0 text-accent-400" />{p}</li>
            ))}
          </ul>
        </div>
        <p className="relative text-xs text-surface-400">Early development build. Dataset upload, training and diagnostics are on the roadmap.</p>
      </section>

      <main className="flex flex-col justify-center px-6 py-10 sm:px-12">
        <div className="mx-auto w-full max-w-sm">
          <div className="mb-8 lg:hidden"><Logo /></div>
          <h1 className="text-2xl font-semibold tracking-tight text-ivory-50">{title}</h1>
          <p className="mt-1.5 text-sm text-ivory-300">{subtitle}</p>
          <div className="mt-7">{children}</div>
          <p className="mt-6 text-sm text-ivory-300">{footer}</p>
          <p className="mt-8 text-xs text-surface-500"><Link to="/" className="hover:text-ivory-300">&larr; Back to home</Link></p>
        </div>
      </main>
    </div>
  );
}
