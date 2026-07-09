import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import {
  formatDecimal,
  formatTimestamp,
  formatUsd,
  riskClass,
  shortenAddress,
} from "@/lib/format";
import AiExplanationPanel from "@/components/AiExplanationPanel";

type Tab = "transactions" | "holdings" | "snapshots" | "ai";

export default function WalletDetail() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("transactions");

  const walletQuery = useQuery({
    queryKey: ["wallet", id],
    queryFn: () => api.getWallet(id!),
    enabled: Boolean(id),
  });

  const snapshotMutation = useMutation({
    mutationFn: () => api.takeSnapshot(id!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["wallet", id] });
      qc.invalidateQueries({ queryKey: ["snapshots", id] });
    },
  });

  if (walletQuery.isLoading) {
    return <div className="skeleton h-32 w-full" />;
  }
  if (walletQuery.isError || !walletQuery.data) {
    return (
      <div className="card text-red-400">
        Failed to load wallet: {(walletQuery.error as Error)?.message ?? "not found"}
        <div className="mt-3">
          <Link to="/" className="btn btn-secondary">
            Back
          </Link>
        </div>
      </div>
    );
  }

  const w = walletQuery.data;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link to="/" className="btn btn-secondary">
          ← Back
        </Link>
        <button
          className="btn btn-secondary"
          onClick={() => snapshotMutation.mutate()}
          disabled={snapshotMutation.isPending}
        >
          {snapshotMutation.isPending ? "Snapshotting…" : "Take snapshot"}
        </button>
      </div>

      <div className="card">
        <div className="flex items-start justify-between mb-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xs px-1.5 py-0.5 rounded bg-bg-elevated text-text-muted uppercase">
                {w.chain}
              </span>
              <span className={`badge ${riskClass(w.last_risk_level)}`}>{w.last_risk_level}</span>
            </div>
            <div className="text-lg font-medium">
              {w.label || shortenAddress(w.address, 10, 8)}
            </div>
            <div className="font-mono text-sm text-text-muted">{w.address}</div>
          </div>
          <div className="text-right">
            <div className="text-2xl font-mono">{formatUsd(w.last_total_usd)}</div>
            <div className="text-xs text-text-muted">
              {formatDecimal(w.last_native_amount)} {w.native_symbol}
            </div>
          </div>
        </div>
      </div>

      <div className="flex gap-1 border-b border-border-subtle">
        {(["transactions", "holdings", "snapshots", "ai"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-3 py-2 text-sm capitalize border-b-2 transition-colors ${
              tab === t
                ? "border-accent text-text"
                : "border-transparent text-text-muted hover:text-text"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "transactions" && <TransactionsTab walletId={w.id} />}
      {tab === "holdings" && <HoldingsTab walletId={w.id} />}
      {tab === "snapshots" && <SnapshotsTab walletId={w.id} />}
      {tab === "ai" && <AiExplanationPanel walletId={w.id} />}
    </div>
  );
}

function TransactionsTab({ walletId }: { walletId: string }) {
  const q = useQuery({
    queryKey: ["txs", walletId],
    queryFn: () => api.listTransactions(walletId, 1, 50),
  });
  if (q.isLoading) return <div className="skeleton h-40 w-full" />;
  if (q.isError) return <div className="card text-red-400">Failed to load transactions</div>;
  if (!q.data || q.data.items.length === 0)
    return <div className="card text-text-muted text-center py-6">No transactions yet.</div>;
  return (
    <div className="space-y-2">
      {q.data.items.map((tx) => (
        <div key={tx.id} className="card flex items-center justify-between">
          <div className="min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <span
                className={`text-xs px-1.5 py-0.5 rounded ${
                  tx.direction === "in"
                    ? "bg-green-500/15 text-green-400"
                    : tx.direction === "out"
                      ? "bg-red-500/15 text-red-400"
                      : "bg-bg-elevated text-text-muted"
                }`}
              >
                {tx.direction}
              </span>
              <span className="font-mono text-xs text-text-muted">
                {shortenAddress(tx.tx_hash, 8, 6)}
              </span>
              <span className={`badge ${riskClass(tx.risk_level)}`}>{tx.risk_level}</span>
            </div>
            <div className="text-sm">
              {formatDecimal(tx.native_amount)} {tx.native_symbol}
              {tx.token_symbol && (
                <span className="text-text-muted">
                  {" "}· {formatDecimal(tx.token_amount)} {tx.token_symbol}
                </span>
              )}
            </div>
            <div className="text-xs text-text-dim font-mono mt-1">
              {shortenAddress(tx.counterparty, 6, 4)} · {formatTimestamp(tx.timestamp)}
            </div>
          </div>
          <div className="text-xs text-text-muted">{tx.status}</div>
        </div>
      ))}
    </div>
  );
}

function HoldingsTab({ walletId }: { walletId: string }) {
  const q = useQuery({
    queryKey: ["holdings", walletId],
    queryFn: () => api.listHoldings(walletId),
  });
  if (q.isLoading) return <div className="skeleton h-40 w-full" />;
  if (q.isError) return <div className="card text-red-400">Failed to load holdings</div>;
  if (!q.data || q.data.length === 0)
    return <div className="card text-text-muted text-center py-6">No token holdings detected.</div>;
  return (
    <div className="space-y-2">
      {q.data.map((h) => (
        <div key={h.contract} className="card flex items-center justify-between">
          <div>
            <div className="font-medium">{h.symbol}</div>
            <div className="text-xs text-text-muted">{h.name}</div>
          </div>
          <div className="text-right">
            <div className="font-mono">{formatDecimal(h.amount)}</div>
            <div className="text-xs text-text-muted">{formatUsd(h.estimated_usd_value)}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

function SnapshotsTab({ walletId }: { walletId: string }) {
  const q = useQuery({
    queryKey: ["snapshots", walletId],
    queryFn: () => api.listSnapshots(walletId, 30),
  });
  if (q.isLoading) return <div className="skeleton h-40 w-full" />;
  if (q.isError) return <div className="card text-red-400">Failed to load snapshots</div>;
  if (!q.data || q.data.length === 0)
    return <div className="card text-text-muted text-center py-6">No snapshots yet.</div>;
  return (
    <div className="space-y-2">
      {q.data.map((s) => (
        <div key={s.id} className="card grid grid-cols-4 gap-2 text-sm">
          <div>
            <div className="text-xs text-text-dim">Taken</div>
            <div>{formatTimestamp(s.taken_at)}</div>
          </div>
          <div>
            <div className="text-xs text-text-dim">Native</div>
            <div className="font-mono">{formatDecimal(s.native_amount)}</div>
          </div>
          <div>
            <div className="text-xs text-text-dim">Tokens</div>
            <div>{s.tokens_count}</div>
          </div>
          <div>
            <div className="text-xs text-text-dim">Total USD</div>
            <div className="font-mono">{formatUsd(s.total_usd)}</div>
          </div>
        </div>
      ))}
    </div>
  );
}
