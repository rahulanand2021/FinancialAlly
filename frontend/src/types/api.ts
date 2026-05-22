/**
 * Shared API types matching backend response shapes defined in planning/PLAN.md §8.
 */

export type PriceDirection = "up" | "down" | "flat";

export interface PriceTick {
  ticker: string;
  price: number;
  prev_price: number;
  session_open: number;
  timestamp: string;
  direction: PriceDirection;
}

export interface WatchlistEntry {
  ticker: string;
  price: number;
  prev_price: number;
  session_open: number;
  session_change_pct: number;
}

export interface Position {
  ticker: string;
  quantity: number;
  avg_cost: number;
  current_price: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
}

export interface Portfolio {
  cash_balance: number;
  total_value: number;
  positions: Position[];
}

export interface PortfolioSnapshot {
  timestamp: string;
  total_value: number;
}

export type TradeSide = "buy" | "sell";

export interface TradeRequest {
  ticker: string;
  quantity: number;
  side: TradeSide;
}

/**
 * A single auto-executed action returned by POST /api/chat. The backend emits
 * a flat list of trade/watchlist results (see backend/routes/chat.py).
 */
export interface ChatAction {
  type: "trade" | "watchlist";
  status: "ok" | "error" | "noop";
  ticker: string;
  side?: TradeSide;
  quantity?: number;
  price?: number;
  action?: "add" | "remove";
  already_present?: boolean;
  error?: string;
}

export interface ChatMessage {
  id?: string;
  role: "user" | "assistant";
  content: string;
  actions?: ChatAction[] | null;
  created_at?: string;
}

export interface ChatResponse {
  message: string;
  actions: ChatAction[];
}

export type ConnectionStatus = "connected" | "reconnecting" | "disconnected";
