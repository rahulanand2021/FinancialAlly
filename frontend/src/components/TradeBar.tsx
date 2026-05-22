"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { usePortfolio } from "@/hooks/PortfolioContext";
import { useSelection } from "@/hooks/SelectionContext";
import { TradeSide } from "@/types/api";
import Panel from "./Panel";

export default function TradeBar() {
  const { selectedTicker } = useSelection();
  const { refresh } = usePortfolio();
  const [ticker, setTicker] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [status, setStatus] = useState<{ message: string; ok: boolean } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (selectedTicker) setTicker(selectedTicker);
  }, [selectedTicker]);

  const submit = async (side: TradeSide) => {
    const sym = ticker.trim().toUpperCase();
    const qty = parseFloat(quantity);
    if (!sym || !Number.isFinite(qty) || qty < 0.001) {
      setStatus({ message: "Enter a ticker and quantity >= 0.001", ok: false });
      return;
    }
    setBusy(true);
    try {
      await api.trade({ ticker: sym, quantity: qty, side });
      setStatus({ message: `${side.toUpperCase()} ${qty} ${sym} filled`, ok: true });
      await refresh();
    } catch (e) {
      setStatus({ message: (e as Error).message, ok: false });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel title="Trade">
      <div className="p-3 flex items-center gap-2 flex-wrap">
        <input
          value={ticker}
          onChange={(e) => setTicker(e.target.value.toUpperCase())}
          placeholder="TICKER"
          maxLength={8}
          data-testid="trade-ticker-input"
          className="w-24 px-2 py-1 text-sm font-mono uppercase bg-bg-base border border-border-muted rounded focus:outline-none focus:border-accent-blue"
        />
        <input
          type="number"
          step="0.001"
          min="0.001"
          value={quantity}
          onChange={(e) => setQuantity(e.target.value)}
          data-testid="trade-quantity-input"
          className="w-24 px-2 py-1 text-sm font-mono bg-bg-base border border-border-muted rounded focus:outline-none focus:border-accent-blue"
        />
        <button
          type="button"
          disabled={busy}
          onClick={() => submit("buy")}
          data-testid="trade-buy-button"
          className="px-3 py-1 text-sm font-semibold bg-accent-purple text-white rounded hover:bg-accent-purple/80 disabled:opacity-50"
        >
          Buy
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => submit("sell")}
          data-testid="trade-sell-button"
          className="px-3 py-1 text-sm font-semibold bg-down text-white rounded hover:bg-down/80 disabled:opacity-50"
        >
          Sell
        </button>
        {status && (
          <span
            data-testid="trade-status"
            className={`text-xs font-mono ${
              status.ok ? "text-up" : "text-down"
            }`}
          >
            {status.message}
          </span>
        )}
      </div>
    </Panel>
  );
}
