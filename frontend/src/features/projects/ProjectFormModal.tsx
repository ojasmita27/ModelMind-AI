import { useState, type FormEvent } from "react";
import { ApiError } from "../../api/client";
import type { Project, ProjectInput } from "../../api/types";
import { Modal } from "../../components/ui/Modal";
import { TextArea, TextField } from "../../components/ui/Field";
import { Button } from "../../components/ui/primitives";
import { LIMITS, validateDescription, validateProjectName } from "../../lib/validation";

interface Props {
  open: boolean;
  /** Provide a project to edit it; omit to create a new one. */
  project?: Project | null;
  onClose: () => void;
  onSubmit: (input: ProjectInput) => Promise<void>;
}

export function ProjectFormModal({ open, project, onClose, onSubmit }: Props) {
  // Remount the inner form whenever the dialog opens or the target project changes: fresh state, no stale errors.
  return (
    <Modal open={open} onClose={onClose} title={project ? "Edit project" : "New project"}>
      <ProjectForm key={project?.id ?? "new"} project={project ?? null} onClose={onClose} onSubmit={onSubmit} />
    </Modal>
  );
}

function ProjectForm({ project, onClose, onSubmit }: Omit<Props, "open">) {
  const [name, setName] = useState(project?.name ?? "");
  const [description, setDescription] = useState(project?.description ?? "");
  const [errors, setErrors] = useState<{ name?: string | null; description?: string | null; form?: string }>({});
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const found = { name: validateProjectName(name), description: validateDescription(description) };
    if (found.name || found.description) { setErrors(found); return; }
    setErrors({});
    setBusy(true);
    try {
      await onSubmit({ name: name.trim(), description: description.trim() ? description.trim() : null });
      onClose();
    } catch (err) {
      if (err instanceof ApiError && Object.keys(err.fieldErrors).length > 0) {
        setErrors({ name: err.fieldErrors.name, description: err.fieldErrors.description });
      } else {
        setErrors({ form: err instanceof ApiError ? err.message : "Could not save the project. Please try again." });
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-4">
      {errors.form && <p role="alert" className="rounded border border-danger-500/40 bg-danger-500/10 p-3 text-sm text-red-200">{errors.form}</p>}
      <TextField label="Project name" value={name} onChange={(e) => setName(e.target.value)} error={errors.name}
        maxLength={LIMITS.nameMax + 20} placeholder="e.g. Customer churn study" autoComplete="off" required />
      <TextArea label="Description (optional)" value={description} onChange={(e) => setDescription(e.target.value)} error={errors.description}
        maxLength={LIMITS.descriptionMax} placeholder="What question are you trying to answer with this data?" />
      <div className="flex justify-end gap-2 pt-2">
        <Button variant="secondary" onClick={onClose} disabled={busy}>Cancel</Button>
        <Button type="submit" loading={busy}>{project ? "Save changes" : "Create project"}</Button>
      </div>
    </form>
  );
}
