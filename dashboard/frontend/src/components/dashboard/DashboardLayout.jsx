import { Outlet } from "@tanstack/react-router";
import { Sidebar } from "./Sidebar";
import { Header } from "./Header";
import { FiltersBar } from "./FiltersBar";
import { useLocation } from "@tanstack/react-router";

// Pages sans barre de filtres
const NO_FILTER_PAGES = ["/parametres", "/predictions"];

export function DashboardLayout() {
  const location = useLocation();
  const showFilters = !NO_FILTER_PAGES.includes(location.pathname);

  return (
    <div className="min-h-screen bg-background">
      <Sidebar />
      <Header pathname={location.pathname} />

      <main className="ml-0 lg:ml-[264px] pt-16 px-4 md:px-6 lg:px-8 pb-8 min-h-screen">
        {showFilters && <FiltersBar />}
        <Outlet />
      </main>
    </div>
  );
}
