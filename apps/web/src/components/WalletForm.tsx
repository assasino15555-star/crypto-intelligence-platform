import { useState } from "react";

const CHAINS = [
  { value: "ethereum", label: "Ethereum" },
  { value: "base", label: "Base" },
];

interface Props {
  onSubmit: (v: { chain: string; address: string; label: string | null }) => void;
  loading: boolean;
  error: Error | null;
}

export default function WalletForm({ onSubmit, loading, error }: Props) {
  const [chain, setChain] = useState("ethereum");
  const [address, setAddress] = useState("");
  const [label, setLabel] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setValidationError(null);
    const trimmed = address.trim();
    if (!/^0x[0-9a-fA-F]{40}$/.test(trimmed)) {
      setValidationError("Address must be a 0x-prefixed 40-hex-char EVM address.");
      return;
    }
    onSubmit({ chain, address: trimmed, label: label.trim() || null });
  }

  return (
    <form onSubmit={handleSubmit} className="card-elevated space-y-4">
      <div>
        <label className="label" htmlFor="chain">
          Chain
        </label>
        <select
          id="chain"
          className="input"
          value={chain}
          onChange={(e) => setChain(e.target.value)}
          disabled={loading}
        >
          {CHAINS.map((c) => (
            <option key={c.value} value={c.value}>
              {c.label}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label className="label" htmlFor="address">
          Wallet address
        </label>
        <input
          id="address"
          className="input font-mono"
          value={address}
          onChange={(e) => setAddress(e.target.value)}
          placeholder="0x…"
          disabled={loading}
          autoComplete="off"
          spellCheck={false}
        />
        <p className="text-xs text-text-dim mt-1">
          Public address only. Never enter private keys or seed phrases.
        </p>
      </div>
      <div>
        <label className="label" htmlFor="label">
          Label (optional)
        </label>
        <input
          id="label"
          className="input"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder="e.g. Cold storage"
          maxLength={64}
          disabled={loading}
        />
      </div>
      {validationError && (
        <div className="text-sm text-red-400">{validationError}</div>
      )}
      {error && <div className="text-sm text-red-400">{error.message}</div>}
      <button type="submit" className="btn w-full" disabled={loading}>
        {loading ? "Adding…" : "Add wallet"}
      </button>
    </form>
  );
}
