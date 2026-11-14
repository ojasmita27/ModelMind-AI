import { Link } from "react-router-dom";
import { EmptyState } from "../components/ui/primitives";

export default function NotFound() {
  return (
    <div className="mx-auto max-w-lg py-16">
      <EmptyState icon="search" title="Page not found" action={<Link to="/" className="text-sm font-medium text-accent-400 hover:text-accent-300">Go to the home page</Link>}>
        The page you are looking for does not exist.
      </EmptyState>
    </div>
  );
}
