import { useState } from "react";

import Header from "./components/Header";
import Sidebar, { type Page } from "./components/Sidebar";
import Toasts from "./components/Toasts";
import DashboardPage from "./pages/DashboardPage";
import SettingsPage from "./pages/SettingsPage";
import { AppDataProvider, useAppData } from "./state/AppData";

function Shell() {
  const [page, setPage] = useState<Page>("dashboard");
  const { inTauri } = useAppData();

  return (
    <div className="flex h-full">
      <Sidebar page={page} onNavigate={setPage} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Header page={page} />
        {!inTauri ? (
          <div className="border-b border-amberx/30 bg-amberx/10 px-5 py-1.5 text-[11px] text-amberx">
            Running outside the desktop shell — live data and controls need the Tauri app
            (`make desktop`).
          </div>
        ) : null}
        <main className="min-h-0 flex-1 overflow-y-auto">
          {page === "dashboard" ? <DashboardPage /> : <SettingsPage />}
        </main>
      </div>
      <Toasts />
    </div>
  );
}

export default function App() {
  return (
    <AppDataProvider>
      <Shell />
    </AppDataProvider>
  );
}
