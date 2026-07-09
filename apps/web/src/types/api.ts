export type Chain = "ethereum" | "base";

export interface User {
  id: string;
  telegram_id: number;
  telegram_username: string | null;
  telegram_first_name: string | null;
  telegram_last_name: string | null;
  is_active: boolean;
}

export interface SessionOut {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface Wallet {
  id: string;
  chain: string;
  address: string;
  label: string | null;
  native_symbol: string;
  is_active: boolean;
  last_synced_at: string | null;
  last_native_amount: string | null;
  last_total_usd: string | null;
  last_risk_level: string;
  created_at: string;
  updated_at: string;
}

export interface Transaction {
  id: string;
  tx_hash: string;
  block: number | null;
  timestamp: string;
  direction: "in" | "out" | "self";
  counterparty: string;
  native_amount: string;
  native_symbol: string;
  token_symbol: string | null;
  token_contract: string | null;
  token_amount: string | null;
  status: string;
  risk_level: "low" | "medium" | "high";
  risk_reasons: string[];
}

export interface TokenHolding {
  contract: string;
  symbol: string;
  name: string;
  decimals: number;
  amount: string;
  usd_price: string | null;
  estimated_usd_value: string | null;
  updated_at: string;
}

export interface WalletSnapshot {
  id: string;
  taken_at: string;
  native_amount: string;
  native_usd: string | null;
  tokens_usd: string | null;
  total_usd: string | null;
  tokens_count: number;
}

export interface Alert {
  id: string;
  wallet_id: string;
  kind: string;
  threshold_amount: number | null;
  is_active: boolean;
  note: string | null;
  created_at: string;
  updated_at: string;
}

export interface AiExplanation {
  explanation: string;
  model: string;
  is_cached: boolean;
  input_summary: string;
}

export interface PageMeta {
  page: number;
  page_size: number;
  total: number;
}

export interface PageResponse<T> {
  items: T[];
  meta: PageMeta;
}

export interface ApiError {
  error: { code: string; message: string };
}
