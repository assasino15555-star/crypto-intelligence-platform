import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { formatTimestamp, shortenAddress } from "@/lib/format";
import type { Alert } from "@/types/api";

const KIND_LABELS: Record<string, string> = {
  incoming_above: "Incoming ≥ threshold",
  outgoing_above: "Outgoing ≥ threshold",
  activity: "Any activity",
  balance_above: "Balance ≥ threshold",
  token_transfer: "Token transfer",
};

export default function Alerts() {
  const qc = useQueryClient();
  const [walletId, setWalletId] = useState("");
  const [kind, setKind] = useState("incoming_above");
  const [threshold, setThreshold] = useState("");
  const [note, setNote] = useState("");

  const alertsQuery = useQuery({
    queryKey: ["alerts"],
    queryFn: () => api.listAlerts(1, 50),
  });
  const walletsQuery = useQuery({
    queryKey: ["wallets"],
    queryFn: () => api.listWallets(1, 100),
  });
  const kindsQuery = useQuery({
    queryKey: ["alert-kinds"],
    queryFn: () => api.listAlertKinds(),
  });

  const createMutation = useMutation({
    mutationFn: () =>
      api.createAlert(
        walletId,
        kind,
        threshold ? Number(threshold) : null,
        note.trim() || null
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["alerts"] });
      setThreshold("");
      setNote("");
    },
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      api.updateAlert(id, { is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alerts"] }),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.deleteAlert(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alerts"] }),
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Alerts</h1>
        <p className="text-text-muted text-sm">
          Receive Telegram notifications when configured conditions fire.
        </p>
      </div>

      <form
        className="card-elevated space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (!walletId) return;
          createMutation.mutate();
        }}
      >
        <div className="grid sm:grid-cols-2 gap-4">
          <div>
            <label className="label" htmlFor="wallet">Wallet</label>
            <select
              id="wallet"
              className="input"
              value={walletId}
              onChange={(e) => setWalletId(e.target.value)}
              required
            >
              <option value="">Select wallet…</option>
              {walletsQuery.data?.items.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.label || shortenAddress(w.address, 6, 4)} · {w.chain}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="kind">Condition</label>
            <select
              id="kind"
              className="input"
              value={kind}
              onChange={(e) => setKind(e.target.value)}
            >
              {kindsQuery.data?.map((k) => (
                <option key={k} value={k}>
                  {KIND_LABELS[k] ?? k}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="threshold">Threshold (optional)</label>
            <input
              id="threshold"
              type="number"
              min="0"
              step="any"
              className="input"
              value={threshold}
              onChange={(e) => setThreshold(e.target.value)}
              placeholder="e.g. 0.5"
            />
          </div>
          <div>
            <label className="label" htmlFor="note">Note (optional)</label>
            <input
              id="note"
              className="input"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              maxLength={512}
            />
          </div>
        </div>
        {createMutation.isError && (
          <div className="text-sm text-red-400">
            {(createMutation.error as Error).message}
          </div>
        )}
        <button type="submit" className="btn" disabled={createMutation.isPending || !walletId}>
          {createMutation.isPending ? "Creating…" : "Create alert"}
        </button>
      </form>

      <div className="space-y-2">
        {alertsQuery.isLoading && <div className="skeleton h-20 w-full" />}
        {alertsQuery.data && alertsQuery.data.items.length === 0 && (
          <div className="card text-text-muted text-center py-6">No alerts configured.</div>
        )}
        {alertsQuery.data?.items.map((a) => (
          <AlertRow
            key={a.id}
            alert={a}
            onToggle={(v) => toggleMutation.mutate({ id: a.id, is_active: v })}
            onDelete={() => deleteMutation.mutate(a.id)}
          />
        ))}
      </div>
    </div>
  );
}

function AlertRow({
  alert,
  onToggle,
  onDelete,
}: {
  alert: Alert;
  onToggle: (v: boolean) => void;
  onDelete: () => void;
}) {
  return (
    <div className="card flex items-center justify-between gap-3">
      <div className="min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className="text-sm font-medium">{KIND_LABELS[alert.kind] ?? alert.kind}</span>
          {alert.threshold_amount !== null && (
            <span className="text-xs font-mono text-text-muted">≥ {alert.threshold_amount}</span>
          )}
          <span
            className={`badge ${alert.is_active ? "badge-risk-low" : "bg-bg-elevated text-text-muted"}`}
          >
            {alert.is_active ? "active" : "paused"}
          </span>
        </div>
        <div className="text-xs text-text-dim">
          {shortenAddress(alert.wallet_id, 6, 4)} · created {formatTimestamp(alert.created_at)}
        </div>
        {alert.note && <div className="text-xs text-text-muted mt-1">{alert.note}</div>}
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <button
          className="btn btn-secondary"
          onClick={() => onToggle(!alert.is_active)}
          title={alert.is_active ? "Pause" : "Activate"}
        >
          {alert.is_active ? "Pause" : "Activate"}
        </button>
        <button className="btn btn-danger" onClick={onDelete} title="Delete">
          Delete
        </button>
      </div>
    </div>
  );
}
