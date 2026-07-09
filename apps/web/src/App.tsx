import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { api, getToken, setToken } from "@/lib/api";
import { getTelegramInitData, initTelegramWebApp } from "@/lib/telegram";
import Dashboard from "@/pages/Dashboard";
import WalletDetail from "@/pages/WalletDetail";
import Alerts from "@/pages/Alerts";
import Login from "@/pages/Login";

function useBootstrapAuth() {
  const navigate = useNavigate();
  useEffect(() => {
    initTelegramWebApp();
    const initData = getTelegramInitData();
    if (initData && !getToken()) {
      api
        .login(initData)
        .then((session) => {
          setToken(session.access_token);
          navigate("/", { replace: true });
        })
        .catch((err) => {
          // eslint-disable-next-line no-console
          console.warn("Telegram login failed", err);
        });
    }
  }, [navigate]);
}

function RequireAuth({ children }: { children: JSX.Element }): JSX.Element {
  const token = getToken();
  if (!token) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

export default function App() {
  useBootstrapAuth();
  const meQuery = useQuery({
    queryKey: ["me"],
    queryFn: () => api.me(),
    enabled: Boolean(getToken()),
    retry: false,
  });

  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-border-subtle bg-bg-panel/80 backdrop-blur sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-4 py-3 flex items-center justify-between">
          <a href="/" className="flex items-center gap-2">
            <span className="inline-block w-7 h-7 rounded-md bg-accent text-white grid place-items-center text-xs font-bold">
              CI
            </span>
            <span className="font-semibold tracking-tight">Crypto Intelligence</span>
          </a>
          <nav className="flex items-center gap-1 text-sm">
            <a href="/" className="px-2 py-1 text-text-muted hover:text-text">
              Dashboard
            </a>
            <a href="/alerts" className="px-2 py-1 text-text-muted hover:text-text">
              Alerts
            </a>
            {meQuery.data && (
              <span className="px-2 py-1 text-text-dim hidden sm:inline">
                @{meQuery.data.telegram_username ?? meQuery.data.telegram_id}
              </span>
            )}
          </nav>
        </div>
      </header>

      <main className="flex-1 max-w-5xl w-full mx-auto px-4 py-6">
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            path="/"
            element={
              <RequireAuth>
                <Dashboard />
              </RequireAuth>
            }
          />
          <Route
            path="/wallets/:id"
            element={
              <RequireAuth>
                <WalletDetail />
              </RequireAuth>
            }
          />
          <Route
            path="/alerts"
            element={
              <RequireAuth>
                <Alerts />
              </RequireAuth>
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>

      <footer className="border-t border-border-subtle py-4 text-center text-xs text-text-dim">
        Read-only intelligence · No private keys ever requested
      </footer>
    </div>
  );
}
