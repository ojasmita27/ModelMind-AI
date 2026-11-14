import { Link, Navigate, useParams } from "react-router-dom";
import { Badge, Card, PageHeader } from "../components/ui/primitives";
import { ROADMAP } from "../lib/roadmap";
import NotFound from "./NotFound";

export default function ComingSoon() {
  const { slug } = useParams();

  if (slug === "datasets") return <Navigate to="/app/projects?view=datasets" replace />;
  if (slug === "experiments") return <Navigate to="/app/projects?view=experiments" replace />;

  const item = ROADMAP.find((r) => r.slug === slug);
  if (!item) return <NotFound />;
  return (
    <>
      <PageHeader title={item.label} subtitle={item.milestone} actions={<Badge>Coming soon</Badge>} />
      <Card className="max-w-2xl space-y-4 p-6">
        <p className="text-sm text-ivory-200">{item.summary}</p>
        <div className="rounded bg-surface-900 p-4 text-sm text-ivory-300"><span className="font-medium text-ivory-100">Planned integration: </span>{item.willUse}</div>
        <p className="text-sm text-surface-400">This feature is <strong className="text-ivory-200">not implemented yet</strong>. No data or results are shown here.</p>
        <Link to="/app" className="inline-block text-sm font-medium text-accent-400 hover:text-accent-300">&larr; Back to dashboard</Link>
      </Card>
    </>
  );
}
