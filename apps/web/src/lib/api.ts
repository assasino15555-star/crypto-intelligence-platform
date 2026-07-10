import type {
  AiExplanation,
  Alert,
  PageResponse,
  SessionOut,
  TokenHolding,
  Transaction,
  User,
  Wallet,
  WalletSnapshot,
} from "@/types/api";

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "/api/v1";

function getToken(): string | null {
  return sessionStorage.getItem("cip_token");
}

function setToken(token: string | null): void {
  if (token) {
    sessionStorage.setItem("cip_token", token);
  } else {
    sessionStorage.removeItem("cip_token");
  }
}

export { getToken, setToken };

function isApiPath(path: string): boolean {
  return path.startsWith("/") || path.startsWith(API_BASE);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (!isApiPath(path)) {
    throw new Error("blocked cross-origin request");
  }
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const token = getToken();
  if (token && path.startsWith(API_BASE)) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const url = path.startsWith("/") ? `${API_BASE}${path}` : path;
  const resp = await fetch(url, { ...init, headers });
  if (resp.status === 401 || resp.status === 403) {
    setToken(null);
  }
  if (!resp.ok) {
    let code = "http_error";
    let message = `HTTP ${resp.status}`;
    try {
      const body = await resp.json();
      code = body?.error?.code ?? code;
      message = body?.error?.message ?? message;
    } catch {
      // ignore
    }
    const err = new Error(message) as Error & { code: string; status: number };
    err.code = code;
    err.status = resp.status;
    throw err;
  }
  if (resp.status === 204) {
    return undefined as T;
  }
  return (await resp.json()) as T;
}

export const api = {
  login: (initData: string) =>
    request<SessionOut>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ init_data: initData }),
    }),
  me: () => request<User>("/auth/me"),
  logout: () => request<void>("/auth/logout", { method: "POST" }),
  revokeAll: () => request<void>("/auth/revoke-all", { method: "POST" }),

  listWallets: (page = 1, pageSize = 20, activeOnly = false) =>
    request<PageResponse<Wallet>>(
      `/wallets?page=${page}&page_size=${pageSize}${activeOnly ? "&active_only=true" : ""}`,
    ),
  createWallet: (chain: string, address: string, label: string | null) =>
    request<Wallet>("/wallets", {
      method: "POST",
      body: JSON.stringify({ chain, address, label }),
    }),
  getWallet: (id: string) => request<Wallet>(`/wallets/${id}`),
  updateWallet: (id: string, patch: { label?: string | null; is_active?: boolean }) =>
    request<Wallet>(`/wallets/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
  deleteWallet: (id: string) => request<void>(`/wallets/${id}`, { method: "DELETE" }),
  listTransactions: (walletId: string, page = 1, pageSize = 20, direction?: string) => {
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (direction) params.set("direction", direction);
    return request<PageResponse<Transaction>>(`/wallets/${walletId}/transactions?${params}`);
  },
  listHoldings: (walletId: string) =>
    request<TokenHolding[]>(`/wallets/${walletId}/holdings`),
  listSnapshots: (walletId: string, limit = 50) =>
    request<WalletSnapshot[]>(`/wallets/${walletId}/snapshots?limit=${limit}`),
  takeSnapshot: (walletId: string) =>
    request<WalletSnapshot>(`/wallets/${walletId}/snapshot`, { method: "POST" }),

  listAlerts: (page = 1, pageSize = 20) =>
    request<PageResponse<Alert>>(`/alerts?page=${page}&page_size=${pageSize}`),
  createAlert: (walletId: string, kind: string, threshold: number | null, note: string | null) =>
    request<Alert>("/alerts", {
      method: "POST",
      body: JSON.stringify({
        wallet_id: walletId,
        kind,
        threshold_amount: threshold,
        note,
      }),
    }),
  updateAlert: (
    id: string,
    patch: { is_active?: boolean; threshold_amount?: number | null; note?: string | null },
  ) => request<Alert>(`/alerts/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
  deleteAlert: (id: string) => request<void>(`/alerts/${id}`, { method: "DELETE" }),
  listAlertKinds: () => request<string[]>("/alerts/kinds"),

  explain: (walletId: string | null, txId: string | null) =>
    request<AiExplanation>("/ai/explain", {
      method: "POST",
      body: JSON.stringify({ wallet_id: walletId, tx_id: txId }),
    }),
};
