import { Link, createRootRoute, useNavigate, useLocation } from "@tanstack/react-router";
import { useEffect } from "react";
import { DashboardLayout } from "@/components/dashboard/DashboardLayout";
import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { applyStoredTheme } from "@/store/useTheme";
import { applyStoredLanguage } from "@/store/useParametres";
import { useAuth } from "@/store/useAuth";

applyStoredTheme();
applyStoredLanguage();

const PUBLIC_ROUTES = ["/login"];

function NotFoundComponent() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="max-w-md text-center">
        <h1 className="text-7xl font-bold text-foreground">404</h1>
        <h2 className="mt-4 text-xl font-semibold text-foreground">Page introuvable</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          La page que vous cherchez n'existe pas.
        </p>
        <div className="mt-6">
          <Link
            to="/"
            className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            Accueil
          </Link>
        </div>
      </div>
    </div>
  );
}

function RootComponent() {
  const { isAuthenticated } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const isPublic = PUBLIC_ROUTES.includes(location.pathname);

  useEffect(() => {
    if (isAuthenticated && location.pathname === "/login") {
      navigate({ to: "/" });
    }
  }, [isAuthenticated, location.pathname, navigate]);

  if (isPublic) {
    return <RootOutlet />;
  }

  return (
    <ProtectedRoute>
      <DashboardLayout />
    </ProtectedRoute>
  );
}

import { Outlet } from "@tanstack/react-router";

function RootOutlet() {
  return <Outlet />;
}

export const Route = createRootRoute({
  component: RootComponent,
  notFoundComponent: NotFoundComponent,
});
