import { Navigate, Outlet, useLocation } from "react-router-dom";
import { FullPageSpinner } from "../components/ui/primitives";
import { useAuth } from "./AuthContext";

/** Renders child routes only for signed-in users; everyone else is sent to /login. */
export function ProtectedRoute() {
  const { status } = useAuth();
  const location = useLocation();
  if (status === "loading") return <FullPageSpinner />;
  if (status === "anonymous") return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <Outlet />;
}

/** Login/register pages: signed-in users go straight to the app. */
export function PublicOnlyRoute() {
  const { status } = useAuth();
  if (status === "loading") return <FullPageSpinner />;
  if (status === "authenticated") return <Navigate to="/app" replace />;
  return <Outlet />;
}
