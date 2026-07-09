export function shortenAddress(address: string, prefix = 6, suffix = 4): string {
  if (!address) return "";
  if (address.length <= prefix + suffix) return address;
  return `${address.slice(0, prefix)}…${address.slice(-suffix)}`;
}

export function formatDecimal(value: string | number | null | undefined, maxDigits = 6): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = typeof value === "string" ? Number.parseFloat(value) : value;
  if (!Number.isFinite(n)) return "—";
  return n.toLocaleString("en-US", { maximumFractionDigits: maxDigits });
}

export function formatUsd(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = typeof value === "string" ? Number.parseFloat(value) : value;
  if (!Number.isFinite(n)) return "—";
  return n.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  });
}

export function formatTimestamp(ts: string | null | undefined): string {
  if (!ts) return "—";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("en-US", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function riskClass(level: string): string {
  switch (level) {
    case "low":
      return "badge-risk-low";
    case "medium":
      return "badge-risk-medium";
    case "high":
      return "badge-risk-high";
    default:
      return "badge-risk-low";
  }
}
