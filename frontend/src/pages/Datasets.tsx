import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { ConfirmDialog } from "../components/ui/Modal";
import { useToast } from "../components/ui/Toast";
import { Button, EmptyState, ErrorBanner, PageHeader, Spinner } from "../components/ui/primitives";
import { DatasetUploadModal } from "../features/datasets/DatasetUploadModal";
import { useDatasets } from "../features/datasets/useDatasets";
import { Icon, type IconName } from "../components/icons";

export default function Datasets() {
  const { projectId } = useParams<{ projectId: string }>();
  if (!projectId) return null;

  const { items, status, error, reload, create, remove } = useDatasets(projectId);
  const { notify } = useToast();
  const [uploadOpen, setUploadOpen] = useState(false);
  const [toDelete, setToDelete] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  async function confirmDelete() {
    if (!toDelete) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await remove(toDelete);
      notify("success", "Dataset deleted.");
      setToDelete(null);
      reload();
    } catch (e) {
      setDeleteError(e instanceof ApiError ? e.message : "Could not delete the dataset.");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <>
      <PageHeader title="Datasets" subtitle="Upload and manage your CSV datasets."
        actions={<Button icon="plus" onClick={() => setUploadOpen(true)}>Upload dataset</Button>} />

      {status === "loading" && <div className="py-16 text-center"><Spinner className="h-6 w-6" label="Loading datasets…" /></div>}
      {status === "error" && <ErrorBanner message={error ?? "Could not load datasets."} onRetry={reload} />}

      {status === "ready" && items.length === 0 && (
        <EmptyState icon="database" title="No datasets yet" action={<Button icon="plus" onClick={() => setUploadOpen(true)}>Upload your first dataset</Button>}>
          Datasets contain the data you'll use for training and evaluation. Upload a CSV file to get started.
        </EmptyState>
      )}

      {status === "ready" && items.length > 0 && (
        <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {items.map((d) => (
            <li key={d.id} className="flex flex-col rounded border border-surface-700 bg-surface-850 p-5 transition-colors hover:border-surface-500">
              <div className="flex items-start justify-between gap-2">
                <Link to={`/app/projects/${projectId}/datasets/${d.id}`} className="min-w-0 rounded text-base font-semibold text-ivory-50 hover:text-accent-300">
                  <span className="block truncate">{d.name}</span>
                </Link>
                <div className="-mr-2 -mt-1 flex shrink-0">
                  <IconButton icon="trash" label={`Delete ${d.name}`} onClick={() => { setDeleteError(null); setToDelete(d.id); }} className="hover:text-danger-400" />
                </div>
              </div>
              <p className={`mt-2 line-clamp-2 min-h-10 text-sm ${d.description ? "text-ivory-300" : "italic text-surface-500"}`}>
                {d.description ?? "No description"}
              </p>
              <p className="mt-4 text-xs text-surface-400">Created {new Date(d.created_at).toLocaleDateString()}</p>
            </li>
          ))}
        </ul>
      )}

      <DatasetUploadModal open={uploadOpen} onClose={() => setUploadOpen(false)}
        onSubmit={async (name, description, file) => { await create(name, description, file); notify("success", "Dataset uploaded."); reload(); }} />

      <ConfirmDialog open={toDelete !== null} title="Delete dataset?" confirmLabel="Delete dataset" busy={deleting} error={deleteError}
        message={<>The dataset will be permanently deleted along with all its versions. This cannot be undone.</>}
        onConfirm={confirmDelete} onCancel={() => setToDelete(null)} />
    </>
  );
}

function IconButton({ icon, label, onClick, className }: { icon: IconName; label: string; onClick: () => void; className?: string }) {
  return (
    <button type="button" aria-label={label} title={label}
      className={`inline-flex h-9 w-9 items-center justify-center rounded text-ivory-300 transition-colors hover:bg-surface-700 hover:text-ivory-50 ${className}`} onClick={onClick}>
      <Icon name={icon} className="h-4.5 w-4.5" />
    </button>
  );
}
