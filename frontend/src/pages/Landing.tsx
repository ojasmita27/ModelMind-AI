import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { Icon, type IconName } from "../components/icons";
import { Logo } from "../components/Logo";
import { Badge } from "../components/ui/primitives";
import { APP_NAME, TAGLINE } from "../config";
import { ROADMAP } from "../lib/roadmap";

const AVAILABLE = ["Account registration and sign-in (Argon2id password hashing, JWT)", "Projects: create, view, edit and delete, scoped to your account", "A typed API, health checks and structured logging foundation"];
const PRINCIPLES: { icon: IconName; title: string; text: string }[] = [
  { icon: "database", title: "Real computation only", text: "Every number will come from actual data processing, training and evaluation. Nothing is hardcoded, randomised or invented." },
  { icon: "shield", title: "Leakage-safe by design", text: "Split first, fit preprocessing on training data only, and keep the final test set untouched until one final evaluation." },
  { icon: "search", title: "Evidence, not claims", text: "Diagnostics separate observed evidence from hypotheses and never present unsupported causal conclusions as fact." },
];

export default function Landing() {
  const { status } = useAuth();
  const signedIn = status === "authenticated";
  return (
    <div className="min-h-screen bg-surface-950">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-4 py-5 sm:px-6">
        <Logo />
        <nav aria-label="Account" className="flex items-center gap-2">
          {signedIn ? (
            <Link to="/app" className="rounded bg-accent-500 px-4 py-2 text-sm font-medium text-surface-950 hover:bg-accent-600">Open dashboard</Link>
          ) : (
            <>
              <Link to="/login" className="rounded px-4 py-2 text-sm font-medium text-ivory-200 hover:bg-surface-800">Sign in</Link>
              <Link to="/register" className="rounded bg-accent-500 px-4 py-2 text-sm font-medium text-surface-950 hover:bg-accent-600">Get started</Link>
            </>
          )}
        </nav>
      </header>

      <main>
        <section className="relative overflow-hidden">
          <div className="bg-grid pointer-events-none absolute inset-0" aria-hidden="true" />
          <div className="relative mx-auto max-w-4xl px-4 pb-20 pt-16 text-center sm:px-6 sm:pt-24">
            <p className="mx-auto mb-5 inline-flex items-center gap-2 rounded-full border border-surface-600 bg-surface-850 px-3 py-1 text-xs font-medium text-ivory-200">
              <span className="h-1.5 w-1.5 rounded-full bg-warn-400" /> Early development build
            </p>
            <h1 className="text-4xl font-semibold tracking-tight text-ivory-50 sm:text-6xl">
              A high score is not <span className="bg-gradient-to-r from-accent-400 to-accent-300 bg-clip-text text-transparent">proof of reliability</span>
            </h1>
            <p className="mx-auto mt-6 max-w-2xl text-lg text-ivory-300">
              {APP_NAME} is an ML experimentation platform for training models, stress-testing them under controlled data changes, and investigating where and why they fail.
            </p>
            <p className="mt-3 text-sm font-medium tracking-wide text-surface-400">{TAGLINE}</p>
            <div className="mt-9 flex flex-wrap justify-center gap-3">
              <Link to={signedIn ? "/app" : "/register"} className="inline-flex items-center gap-2 rounded bg-accent-500 px-6 py-3 text-sm font-medium text-surface-950 hover:bg-accent-600">
                {signedIn ? "Open dashboard" : "Create a free account"} <Icon name="arrow" className="h-4 w-4" />
              </Link>
              {!signedIn && <Link to="/login" className="rounded border border-surface-600 bg-surface-850 px-6 py-3 text-sm font-medium text-ivory-100 hover:bg-surface-800">Sign in</Link>}
            </div>
          </div>
        </section>

        <section className="mx-auto grid max-w-6xl gap-6 px-4 pb-16 sm:px-6 md:grid-cols-3" aria-label="Principles">
          {PRINCIPLES.map((p) => (
            <div key={p.title} className="rounded border border-surface-700 bg-surface-850 p-6">
              <span className="mb-4 flex h-10 w-10 items-center justify-center rounded bg-surface-800 text-accent-400"><Icon name={p.icon} /></span>
              <h2 className="text-base font-semibold text-ivory-50">{p.title}</h2>
              <p className="mt-2 text-sm text-ivory-300">{p.text}</p>
            </div>
          ))}
        </section>

        <section className="mx-auto max-w-6xl px-4 pb-24 sm:px-6" aria-label="Status">
          <div className="grid gap-6 md:grid-cols-2">
            <div className="rounded border border-ok-400/25 bg-surface-850 p-6">
              <div className="mb-4 flex items-center gap-2"><h2 className="text-base font-semibold text-ivory-50">Available today</h2><Badge tone="live">Live</Badge></div>
              <ul className="space-y-3">
                {AVAILABLE.map((a) => <li key={a} className="flex gap-3 text-sm text-ivory-200"><Icon name="check" className="mt-0.5 h-4 w-4 shrink-0 text-ok-400" />{a}</li>)}
              </ul>
            </div>
            <div className="rounded border border-dashed border-surface-600 bg-surface-900/60 p-6">
              <div className="mb-4 flex items-center gap-2"><h2 className="text-base font-semibold text-ivory-50">On the roadmap</h2><Badge>Coming soon</Badge></div>
              <ul className="space-y-3">
                {ROADMAP.map((r) => <li key={r.slug} className="text-sm text-ivory-300"><span className="font-medium text-ivory-100">{r.label}</span> <span className="text-surface-500">({r.milestone})</span></li>)}
              </ul>
            </div>
          </div>
        </section>
      </main>
      <footer className="border-t border-surface-800 py-6 text-center text-xs text-surface-500">{APP_NAME} &middot; early development build</footer>
    </div>
  );
}
