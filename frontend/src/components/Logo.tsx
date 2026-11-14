import { Link } from "react-router-dom";
import { APP_NAME } from "../config";

export function Logo({ to = "/", compact = false }: { to?: string; compact?: boolean }) {
  return (
    <Link to={to} className="inline-flex items-center gap-2.5 rounded font-semibold tracking-tight text-ivory-50" aria-label={`${APP_NAME} home`}>
      <svg viewBox="0 0 32 32" className="h-8 w-8" aria-hidden="true">
        <defs>
          <linearGradient id="logo-g" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#a8d632" />
            <stop offset="1" stopColor="#8bb816" />
          </linearGradient>
        </defs>
        <rect width="32" height="32" rx="4" fill="#1f1f1d" />
        <path d="M6 22V10l10 8 10-8v12" fill="none" stroke="url(#logo-g)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="16" cy="18" r="2" fill="#a8d632" />
      </svg>
      {!compact && <span className="text-lg">Model<span className="text-accent-400">Mind</span> <span className="text-ivory-300 font-medium">AI</span></span>}
    </Link>
  );
}
