import { Link } from "react-router-dom";
import type { Project } from "../../api/types";
import { IconButton } from "../../components/ui/primitives";
import { timeAgo } from "../../lib/format";

export function ProjectCard({
  project,
  onEdit,
  onDelete,
  actionLabel,
  actionHref,
}: {
  project: Project;
  onEdit: (p: Project) => void;
  onDelete: (p: Project) => void;
  actionLabel?: string;
  actionHref?: string;
}) {
  return (
    <li className="flex flex-col rounded border border-surface-700 bg-surface-850 p-5 transition-colors hover:border-surface-500">
      <div className="flex items-start justify-between gap-2">
        <Link to={`/app/projects/${project.id}`} className="min-w-0 rounded text-base font-semibold text-ivory-50 hover:text-accent-300">
          <span className="block truncate">{project.name}</span>
        </Link>
        <div className="-mr-2 -mt-1 flex shrink-0">
          <IconButton icon="edit" label={`Edit ${project.name}`} onClick={() => onEdit(project)} />
          <IconButton icon="trash" label={`Delete ${project.name}`} onClick={() => onDelete(project)} className="hover:text-danger-400" />
        </div>
      </div>
      <p className={`mt-2 line-clamp-2 min-h-10 text-sm ${project.description ? "text-ivory-300" : "italic text-surface-500"}`}>
        {project.description ?? "No description"}
      </p>
      <p className="mt-4 text-xs text-surface-400">Updated {timeAgo(project.updated_at)}</p>
      {actionLabel && actionHref && (
        <Link to={actionHref} className="mt-4 inline-flex text-sm font-medium text-accent-400 hover:text-accent-300">
          {actionLabel} →
        </Link>
      )}
    </li>
  );
}
