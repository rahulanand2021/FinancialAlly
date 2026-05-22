"use client";

import { ConnectionStatus } from "@/types/api";
import { formatCurrency } from "@/lib/format";
import { usePriceStreamContext } from "@/hooks/PriceStreamContext";
import { usePortfolio } from "@/hooks/PortfolioContext";

const statusColor: Record<ConnectionStatus, string> = {
  connected: "bg-up",
  reconnecting: "bg-accent-yellow",
  disconnected: "bg-down",
};

const statusLabel: Record<ConnectionStatus, string> = {
  connected: "Live",
  reconnecting: "Reconnecting",
  disconnected: "Disconnected",
};

export default function Header() {
  const { status: connectionStatus } = usePriceStreamContext();
  const { portfolio, liveTotalValue } = usePortfolio();
  const cashBalance = portfolio?.cash_balance ?? 0;
  const totalValue = liveTotalValue;
  return (
    <header className="flex items-center justify-between px-4 py-2 border-b border-border-muted bg-bg-panel">
      <div className="flex items-center gap-3">
        <div className="text-accent-yellow font-bold text-lg tracking-tight">
          FinAlly
        </div>
        <span className="text-text-muted text-xs uppercase tracking-widest">
          AI Trading Workstation
        </span>
      </div>

      <div className="flex items-center gap-6 text-sm">
        <div className="flex items-center gap-2">
          <span className="text-text-muted text-xs uppercase">Cash</span>
          <span data-testid="cash-balance" className="font-mono text-text-primary">
            {formatCurrency(cashBalance)}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-text-muted text-xs uppercase">Total</span>
          <span
            data-testid="total-value"
            className="font-mono text-accent-blue font-semibold"
          >
            {formatCurrency(totalValue)}
          </span>
        </div>
        <div
          className="flex items-center gap-2"
          data-testid="connection-status"
          data-status={connectionStatus}
        >
          <span
            className={`w-2.5 h-2.5 rounded-full ${statusColor[connectionStatus]}`}
            aria-label={statusLabel[connectionStatus]}
          />
          <span className="text-xs text-text-muted">
            {statusLabel[connectionStatus]}
          </span>
        </div>
      </div>
    </header>
  );
}
