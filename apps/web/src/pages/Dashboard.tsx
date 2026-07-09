import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import type { Wallet } from "@/types/api";
import { formatDecimal, formatTimestamp, formatUsd, riskClass, shortenAddress } from "@/lib/format";
import WalletForm from "@/components/WalletForm";

export default function Dashboard() {
  const qc = useQueryClient();
  const [page] = useState(1);
  const [showForm, setShowForm] = useState(false);

  const walletsQuery = useQuery({
    queryKey: ["wallets", page],
    queryFn: () => api.listWallets(page, 50),
  });

  const createMutation = useMutation({
    mutationFn: ({ chain, address, label }: { chain: string; address: string; label: string | null }) =>
      api.createWallet(chain, address, label),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["wallets"] });
      setShowForm(false);
    },
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Wallets</h1>
          <p className="text-text-muted text-sm">
            Read-only monitoring · private keys are never requested
          </p>
        </div>
        <button className="btn" onClick={() => setShowForm((v) => !v)}>
          {showForm ? "Cancel" : "+ Add wallet"}
        </button>
      </div>

      {showForm && (
        <WalletForm
          onSubmit={(v) => createMutation.mutate(v)}
          loading={createMutation.isPending}
          error={createMutation.error as Error | null}
        />
      )}

      {walletsQuery.isLoading && <WalletCardSkeleton />}
      {walletsQuery.isError && (
        <div className="card text-red-400">
          Failed to load wallets: {(walletsQuery.error as Error).message}
        </div>
      )}
      {walletsQuery.data && walletsQuery.data.items.length === 0 && (
        <div className="card text-text-muted text-center py-8">
          No wallets yet. Click <span className="text-text font-medium">Add wallet</span> to start monitoring.
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        {walletsQuery.data?.items.map((w) => (
          <WalletCard key={w.id} wallet={w} />
        ))}
      </div>
    </div>
  );
}

function WalletCard({ wallet }: { wallet: Wallet }) {
  return (
    <Link
      to={`/wallets/${wallet.id}`}
      className="card block hover:border-accent transition-colors"
    >
      <div className="flex items-start justify-between mb-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs px-1.5 py-0.5 rounded bg-bg-elevated text-text-muted uppercase">
              {wallet.chain}
            </span>
            <span className="text-text-muted text-xs">{shortenAddress(wallet.address)}</span>
          </div>
          <div className="font-medium truncate">
            {wallet.label || shortenAddress(wallet.address, 8, 6)}
          </div>
        </div>
        <span className={`badge ${riskClass(wallet.last_risk_level)}`}>{wallet.last_risk_level}</span>
      </div>
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <div className="text-text-dim text-xs mb-0.5">Native balance</div>
          <div className="font-mono">
            {formatDecimal(wallet.last_native_amount)} {wallet.native_symbol}
          </div>
        </div>
        <div>
          <div className="text-text-dim text-xs mb-0.5">Est. value</div>
          <div className="font-mono">{formatUsd(wallet.last_total_usd)}</div>
        </div>
        <div>
          <div className="text-text-dim text-xs mb-0.5">Last sync</div>
          <div className="text-text-muted">{formatTimestamp(wallet.last_synced_at)}</div>
        </div>
        <div>
          <div className="text-text-dim text-xs mb-0.5">Status</div>
          <div className="text-text-muted">{wallet.is_active ? "Active" : "Paused"}</div>
        </div>
      </div>
    </Link>
  );
}

function WalletCardSkeleton() {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="card">
          <div className="skeleton h-4 w-1/3 mb-3" />
          <div className="skeleton h-3 w-2/3 mb-2" />
          <div className="skeleton h-3 w-1/2" />
        </div>
      ))}
    </div>
  );
}
