import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { Project } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { useToast } from "../components/ui/Toast";
import { Badge, Button, Card, EmptyState, ErrorBanner, PageHeader, Spinner } from "../components/ui/primitives";
import { ProjectFormModal } from "../features/projects/ProjectFormModal";
import { useProjects } from "../features/projects/useProjects";
import { timeAgo } from "../lib/format";
import { ROADMAP } from "../lib/roadmap";

const PAGE = 200; // backend maximum page size

/** Real data only: projects created per calendar month for the last 6 months. */
function monthlyCounts(projects: Project[], now = new Date()) {
  const months = Array.from({ length: 6 }, (_, i) => {
    const d = new Date(now.getFullYear(), now.getMonth() - (5 - i), 1);
    return { key: `${d.getFullYear()}-${d.getMonth()}`, label: d.toLocaleDateString(undefined, { month: "short" }), count: 0 };
  });
  for (const p of projects) {
    const d = new Date(p.created_at);
    const m = months.find((x) => x.key === `${d.getFullYear()}-${d.getMonth()}`);
    if (m) m.count += 1;
  }
  return months;
}

function ProjectsPerMonth({ projects }: { projects: Project[] }) {
  const months = useMemo(() => monthlyCounts(projects), [projects]);
  const max = Math.max(...months.map((m) => m.count), 1);
  const summary = months.map((m) => `${m.label}: ${m.count}`).join(", ");
  return (
    <Card className="p-5">
      <h2 className="text-sm font-semibold text-ivory-100">Projects created per month</h2>
      <p className="mt-0.5 text-xs text-surface-400">Last 6 months, from your actual projects.</p>
      <div role="img" aria-label={`Projects created per month. ${summary}`} className="mt-5 flex h-36 items-end gap-3">
        {months.map((m) => (
          <div key={m.key} className="flex h-full flex-1 flex-col items-center justify-end gap-1.5">
            <span className="text-xs tabular-nums text-ivory-300">{m.count}</span>
            <div className="w-full rounded-t bg-gradient-to-t from-accent-600 to-accent-400" style={{ height: `${Math.max((m.count / max) * 100, m.count ? 6 : 2)}%`, opacity: m.count ? 1 : 0.25 }} />
            <span className="text-xs text-surface-400">{m.label}</span>
          </div>
        ))}
      </div>
    </Card>
  );
}

function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <Card className="p-5">
      <p className="text-xs font-medium uppercase tracking-wide text-surface-400">{label}</p>
      <p className="mt-2 truncate text-2xl font-semibold tabular-nums text-ivory-50">{value}</p>
      {note && <p className="mt-1 truncate text-xs text-surface-400">{note}</p>}
    </Card>
  );
}

function SoonStat({ label, milestone }: { label: string; milestone: string }) {
  return (
    <div className="rounded border border-dashed border-surface-600 bg-surface-900/60 p-5">
      <p className="text-xs font-medium uppercase tracking-wide text-surface-400">{label}</p>
      <div className="mt-3"><Badge>Coming soon</Badge></div>
      <p className="mt-2 text-xs text-surface-500">{milestone}</p>
    </div>
  );
}

export default function Dashboard() {
  const { user } = useAuth();
  const { items, status, error, hasMore, reload, create } = useProjects(PAGE);
  const { notify } = useToast();
  const [creating, setCreating] = useState(false);
  const recent = useMemo(() => [...items].sort((a, b) => b.updated_at.localeCompare(a.updated_at)).slice(0, 5), [items]);

  return (
    <>
      <PageHeader title="Dashboard" subtitle={<>Signed in as <span className="text-ivory-100">{user?.email}</span></>}
        actions={<Button icon="plus" onClick={() => setCreating(true)}>New project</Button>} />

      {status === "loading" && <div className="py-16 text-center"><Spinner className="h-6 w-6" label="Loading your workspace…" /></div>}
      {status === "error" && <ErrorBanner message={error ?? "Could not load your projects."} onRetry={reload} />}

      {status === "ready" && (
        <div className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Projects" value={`${items.length}${hasMore ? "+" : ""}`} note={items.length === 0 ? "None yet" : undefined} />
            <Stat label="Last activity" value={recent[0] ? timeAgo(recent[0].updated_at) : "No activity"} note={recent[0]?.name} />
            <SoonStat label="Datasets" milestone="Live" />
            <SoonStat label="Experiments" milestone="Live" />
          </div>

          {items.length === 0 ? (
            <EmptyState icon="folder" title="Welcome to ModelMind" action={<Button icon="plus" onClick={() => setCreating(true)}>Create your first project</Button>}>
              Projects are the home for your datasets and experiments. Dataset upload and model training are coming in upcoming milestones.
            </EmptyState>
          ) : (
            <div className="grid gap-6 lg:grid-cols-5">
              <div className="lg:col-span-3"><ProjectsPerMonth projects={items} /></div>
              <Card className="p-5 lg:col-span-2">
                <div className="flex items-center justify-between"><h2 className="text-sm font-semibold text-ivory-100">Recent projects</h2>
                  <Link to="/app/projects" className="text-xs font-medium text-accent-400 hover:text-accent-300">View all</Link></div>
                <ul className="mt-3 divide-y divide-surface-700">
                  {recent.map((p) => (
                    <li key={p.id}><Link to={`/app/projects/${p.id}`} className="flex items-center justify-between gap-3 rounded py-2.5 hover:text-accent-300">
                      <span className="truncate text-sm text-ivory-100">{p.name}</span><span className="shrink-0 text-xs text-surface-400">{timeAgo(p.updated_at)}</span></Link></li>
                  ))}
                </ul>
              </Card>
            </div>
          )}

          <Card className="p-5">
            <div className="flex items-center gap-2"><h2 className="text-sm font-semibold text-ivory-100">Platform roadmap</h2><Badge>Coming soon</Badge></div>
            <p className="mt-1 text-sm text-surface-400">These capabilities are planned but not built yet. They appear here so you can see where the platform is heading.</p>
            <ul className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {ROADMAP.filter((r) => !["datasets", "experiments"].includes(r.slug)).map((r) => (
                <li key={r.slug}><Link to={`/app/coming-soon/${r.slug}`} className="block rounded border border-surface-700 p-3 hover:border-surface-500">
                  <span className="text-sm font-medium text-ivory-100">{r.label}</span><span className="block text-xs text-surface-400">{r.milestone}</span></Link></li>
              ))}
            </ul>
          </Card>
        </div>
      )}

      <ProjectFormModal open={creating} onClose={() => setCreating(false)} onSubmit={async (input) => { await create(input); notify("success", "Project created."); }} />
    </>
  );
}
