import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, setToken } from "@/lib/api";
import { getTelegramInitData, isInsideTelegram } from "@/lib/telegram";

export default function Login() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const insideTg = isInsideTelegram();

  async function handleLogin() {
    setError(null);
    const initData = getTelegramInitData();
    if (!initData) {
      setError("Telegram initData not available. Open this app via the Telegram bot.");
      return;
    }
    setLoading(true);
    try {
      const session = await api.login(initData);
      setToken(session.access_token);
      navigate("/", { replace: true });
    } catch (err) {
      const e = err as Error & { code?: string };
      setError(e.message || "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-md mx-auto py-12">
      <div className="card-elevated">
        <h1 className="text-2xl font-semibold mb-2">Sign in</h1>
        <p className="text-text-muted text-sm mb-6">
          Authentication is established via cryptographically verified Telegram
          initData. We never trust user-supplied identity fields.
        </p>
        {insideTg ? (
          <button className="btn w-full" disabled={loading} onClick={handleLogin}>
            {loading ? "Verifying…" : "Continue with Telegram"}
          </button>
        ) : (
          <div className="rounded-lg bg-yellow-500/10 border border-yellow-500/30 px-3 py-2 text-sm text-yellow-400">
            Open this app inside Telegram to sign in.
          </div>
        )}
        {error && (
          <div className="mt-3 rounded-lg bg-red-500/10 border border-red-500/30 px-3 py-2 text-sm text-red-400">
            {error}
          </div>
        )}
      </div>
    </div>
  );
}
