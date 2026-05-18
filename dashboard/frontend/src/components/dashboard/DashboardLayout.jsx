import { Outlet, useLocation } from "@tanstack/react-router";
import { Sidebar } from "./Sidebar";
import { Header } from "./Header";
import { FiltersBar } from "./FiltersBar";
import { DataSourceStatus } from "./DataSourceStatus";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { useSyncFiltersWithUrl } from "@/store/useFilters";

const NO_FILTER_PAGES = ["/parametres", "/aide", "/profil", "/assistant"];

export function DashboardLayout() {
  const location = useLocation();
  const showFilters = !NO_FILTER_PAGES.includes(location.pathname);
  const statusDisabled = ["/parametres", "/aide", "/profil", "/assistant"].includes(
    location.pathname,
  );
  useSyncFiltersWithUrl();

  return (
    <div className="min-h-screen bg-gradient-to-br from-background via-background/98 to-background/95 relative overflow-hidden">
      <div className="absolute inset-0 bg-gradient-to-br from-primary/3 via-transparent to-primary/1 opacity-40 pointer-events-none" />
      <div className="absolute top-0 right-0 w-96 h-96 bg-gradient-to-br from-primary/8 to-transparent rounded-full blur-3xl opacity-25" />
      <div className="absolute bottom-0 left-0 w-96 h-96 bg-gradient-to-tr from-primary/6 to-transparent rounded-full blur-3xl opacity-20" />

      <Sidebar />
      <Header pathname={location.pathname} />

      <main className="ml-0 lg:ml-[264px] pt-20 px-4 md:px-6 lg:px-8 pb-8 min-h-[calc(100vh-3.5rem)] transition-all duration-500 relative z-10">
        <DataSourceStatus disabled={statusDisabled} />
        {showFilters && <FiltersBar />}
        <ErrorBoundary resetKey={location.pathname}>
          <Outlet />
        </ErrorBoundary>
      </main>
    </div>
  );
}
