import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { APP_NAME } from "../config";
import { ROADMAP } from "../lib/roadmap";
import { Icon, type IconName } from "./icons";
import { Logo } from "./Logo";
import { Badge, IconButton } from "./ui/primitives";

const ROADMAP_ICONS: Record<string, IconName> = {
  datasets: "database", experiments: "flask", "what-if": "sliders", datatwin: "layers", "failure-intelligence": "zap",
};

const linkBase = "group flex items-center gap-3 rounded px-3 py-2 text-sm font-medium transition-colors";
const linkClass = ({ isActive }: { isActive: boolean }) =>
  `${linkBase} ${isActive ? "bg-accent-500/15 text-accent-300" : "text-ivory-300 hover:bg-surface-800 hover:text-ivory-50"}`;

function SidebarContent({ onNavigate }: { onNavigate: () => void }) {
  const location = useLocation();
  const projectMatch = location.pathname.match(/^\/app\/projects\/([^/]+)(?:\/|$)/);
  const projectId = projectMatch?.[1];
  const datasetsLink = projectId ? `/app/projects/${projectId}/datasets` : "/app/projects?view=datasets";
  const experimentsLink = projectId ? `/app/projects/${projectId}/experiments` : "/app/projects?view=experiments";

  return (
    <nav aria-label="Main" className="flex h-full flex-col gap-6 overflow-y-auto p-4">
      <div className="px-1 pt-1"><Logo to="/app" /></div>
      <div className="space-y-1">
        <NavLink to="/app" end className={linkClass} onClick={onNavigate}><Icon name="grid" /> Dashboard</NavLink>
        <NavLink to="/app/projects" className={linkClass} onClick={onNavigate}><Icon name="folder" /> Projects</NavLink>
        <NavLink to={datasetsLink} className={linkClass} onClick={onNavigate}><Icon name="database" /> Datasets</NavLink>
        <NavLink to={experimentsLink} className={linkClass} onClick={onNavigate}><Icon name="flask" /> Experiments</NavLink>
        {projectId && (
          <>
            <NavLink to={`/app/projects/${projectId}/what-if`} className={linkClass} onClick={onNavigate}><Icon name="sliders" /> What-If Lab</NavLink>
            <NavLink to={`/app/projects/${projectId}/models`} className={linkClass} onClick={onNavigate}><Icon name="layers" /> Model Registry</NavLink>
            <NavLink to={`/app/projects/${projectId}/deployments`} className={linkClass} onClick={onNavigate}><Icon name="zap" /> Deployments</NavLink>
            <NavLink to={`/app/projects/${projectId}/monitoring`} className={linkClass} onClick={onNavigate}><Icon name="grid" /> Monitoring</NavLink>
            <NavLink to={`/app/projects/${projectId}/copilot`} className={linkClass} onClick={onNavigate}><Icon name="flask" /> Research Copilot</NavLink>
            <NavLink to={`/app/projects/${projectId}/trust`} className={linkClass} onClick={onNavigate}><Icon name="database" /> Trust Receipts</NavLink>
          </>
        )}
        <NavLink to="/app/benchmarks" className={linkClass} onClick={onNavigate}><Icon name="zap" /> Benchmark Lab</NavLink>
      </div>
      <div>
        <p className="mb-2 px-3 text-xs font-semibold uppercase tracking-wider text-surface-400">Roadmap</p>
        <div className="space-y-1">
          {ROADMAP.filter((item) => !["datasets", "experiments", "what-if"].includes(item.slug)).map((item) => (
            <NavLink key={item.slug} to={`/app/coming-soon/${item.slug}`} className={linkClass} onClick={onNavigate}>
              <Icon name={ROADMAP_ICONS[item.slug] ?? "layers"} />
              <span className="flex-1">{item.label}</span>
              <Badge>Soon</Badge>
            </NavLink>
          ))}
        </div>
      </div>
    </nav>
  );
}

export function AppLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => setMenuOpen(false), [location.pathname]);
  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setMenuOpen(false); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [menuOpen]);

  function handleLogout() {
    logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className="min-h-screen bg-surface-950 lg:grid lg:grid-cols-[17rem_1fr]">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-[70] focus:rounded focus:bg-accent-500 focus:px-3 focus:py-2 focus:text-surface-950">Skip to content</a>

      <aside className="hidden border-r border-surface-700 bg-surface-900 lg:sticky lg:top-0 lg:block lg:h-screen">
        <SidebarContent onNavigate={() => {}} />
      </aside>

      {menuOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-surface-950/80" onClick={() => setMenuOpen(false)} aria-hidden="true" />
          <aside id="mobile-nav" className="absolute inset-y-0 left-0 w-72 max-w-[85vw] border-r border-surface-700 bg-surface-900 shadow-2xl">
            <SidebarContent onNavigate={() => setMenuOpen(false)} />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-surface-700 bg-surface-950/90 px-4 backdrop-blur sm:px-6">
          <button type="button" className="rounded p-2 text-ivory-200 hover:bg-surface-800 lg:hidden" aria-label="Open navigation menu"
            aria-expanded={menuOpen} aria-controls="mobile-nav" onClick={() => setMenuOpen(true)}>
            <Icon name="menu" />
          </button>
          <span className="text-sm font-medium text-ivory-300 lg:hidden">{APP_NAME}</span>
          <div className="ml-auto flex items-center gap-3">
            <span className="hidden max-w-[16rem] truncate text-sm text-ivory-300 sm:block" title={user?.email}>{user?.email}</span>
            <IconButton icon="logout" label="Sign out" onClick={handleLogout} />
          </div>
        </header>
        <main id="main" tabIndex={-1} className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6"><Outlet /></main>
      </div>
    </div>
  );
}
