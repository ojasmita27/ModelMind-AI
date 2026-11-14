import { useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import { ApiError } from "../api/client";
import type { Project } from "../api/types";
import { ConfirmDialog } from "../components/ui/Modal";
import { useToast } from "../components/ui/Toast";
import { Button, EmptyState, ErrorBanner, PageHeader, Spinner } from "../components/ui/primitives";
import { ProjectCard } from "../features/projects/ProjectCard";
import { ProjectFormModal } from "../features/projects/ProjectFormModal";
import { useProjects } from "../features/projects/useProjects";

export default function Projects() {
  const location = useLocation();
  const feature = new URLSearchParams(location.search).get("view") === "experiments" ? "experiments" : "datasets";
  const { items, status, error, hasMore, loadingMore, reload, loadMore, create, update, remove } = useProjects(50);
  const { notify } = useToast();
  const [form, setForm] = useState<"new" | Project | null>(null);
  const [toDelete, setToDelete] = useState<Project | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? items.filter((p) => p.name.toLowerCase().includes(q) || (p.description ?? "").toLowerCase().includes(q)) : items;
  }, [items, query]);

  async function confirmDelete() {
    if (!toDelete) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await remove(toDelete.id);
      notify("success", `Deleted “${toDelete.name}”.`);
      setToDelete(null);
    } catch (e) {
      setDeleteError(e instanceof ApiError ? e.message : "Could not delete the project.");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <>
      <PageHeader title={feature === "experiments" ? "Select a project for experiments" : "Select a project for datasets"}
        subtitle={feature === "experiments" ? "Choose a project to open its experiment studio." : "Choose a project to open its dataset workspace."}
        actions={<Button icon="plus" onClick={() => setForm("new")}>New project</Button>} />

      {status === "loading" && <div className="py-16 text-center"><Spinner className="h-6 w-6" label="Loading projects…" /></div>}
      {status === "error" && <ErrorBanner message={error ?? "Could not load projects."} onRetry={reload} />}

      {status === "ready" && items.length === 0 && (
        <EmptyState icon="folder" title="No projects yet" action={<Button icon="plus" onClick={() => setForm("new")}>Create your first project</Button>}>
          Projects group related datasets and experiments. Create one to get started.
        </EmptyState>
      )}

      {status === "ready" && items.length > 0 && (
        <>
          <div className="mb-5 max-w-sm">
            <label htmlFor="project-search" className="sr-only">Search projects</label>
            <input id="project-search" type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search projects…"
              className="block w-full rounded border border-surface-600 bg-surface-900 px-3.5 py-2 text-sm text-ivory-50 placeholder:text-surface-500 focus:border-accent-400 focus:outline-none" />
          </div>
          {error && <div className="mb-4"><ErrorBanner message={error} /></div>}
          {visible.length === 0 ? (
            <p className="py-10 text-center text-sm text-ivory-300">No projects match "{query}".</p>
          ) : (
            <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {visible.map((p) => (
                <ProjectCard
                  key={p.id}
                  project={p}
                  onEdit={setForm}
                  onDelete={(proj) => { setDeleteError(null); setToDelete(proj); }}
                  actionLabel={feature === "experiments" ? "Open experiments" : "Open datasets"}
                  actionHref={feature === "experiments" ? `/app/projects/${p.id}/experiments` : `/app/projects/${p.id}/datasets`}
                />
              ))}
            </ul>
          )}
          {hasMore && <div className="mt-6 text-center"><Button variant="secondary" loading={loadingMore} onClick={loadMore}>Load more</Button></div>}
        </>
      )}

      <ProjectFormModal open={form !== null} project={form === "new" ? null : form} onClose={() => setForm(null)}
        onSubmit={async (input) => {
          if (form && form !== "new") { await update(form.id, input); notify("success", "Project updated."); }
          else { await create(input); notify("success", "Project created."); }
        }} />

      <ConfirmDialog open={toDelete !== null} title="Delete project?" confirmLabel="Delete project" busy={deleting} error={deleteError}
        message={<>“{toDelete?.name}” will be permanently deleted. This cannot be undone.</>}
        onConfirm={confirmDelete} onCancel={() => setToDelete(null)} />
    </>
  );
}
