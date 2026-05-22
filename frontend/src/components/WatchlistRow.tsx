"use client";

import { usePriceStreamContext } from "@/hooks/PriceStreamContext";
import { useFlashOnChange } from "@/hooks/useFlashOnChange";
import { useSelection } from "@/hooks/SelectionContext";
import { formatPct, formatPrice } from "@/lib/format";
import Sparkline from "./Sparkline";

interface WatchlistRowProps {
  ticker: string;
  fallbackPrice: number;
  fallbackSessionOpen: number;
  fallbackChangePct: number;
  onRemove: (ticker: string) => void;
}

export default function WatchlistRow({
  ticker,
  fallbackPrice,
  fallbackSessionOpen,
  fallbackChangePct,
  onRemove,
}: WatchlistRowProps) {
  const { prices, history } = usePriceStreamContext();
  const { selectedTicker, selectTicker } = useSelection();

  const tick = prices[ticker];
  const price = tick?.price ?? fallbackPrice;
  const sessionOpen = tick?.session_open ?? fallbackSessionOpen;
  const changePct = sessionOpen
    ? ((price - sessionOpen) / sessionOpen) * 100
    : fallbackChangePct;
  const points = history[ticker] ?? [];
  const flashClass = useFlashOnChange(tick?.price);
  const isSelected = selectedTicker === ticker;
  const changeColor =
    changePct > 0 ? "text-up" : changePct < 0 ? "text-down" : "text-flat";

  return (
    <tr
      data-testid={`watchlist-row-${ticker}`}
      className={`border-b border-border-muted cursor-pointer hover:bg-bg-panel-hover ${
        isSelected ? "bg-bg-panel-hover" : ""
      }`}
      onClick={() => selectTicker(ticker)}
    >
      <td className="px-2 py-1.5 font-mono font-semibold">{ticker}</td>
      <td
        data-testid={`watchlist-price-${ticker}`}
        className={`px-2 py-1.5 font-mono text-right ${flashClass}`}
      >
        {formatPrice(price)}
      </td>
      <td className={`px-2 py-1.5 font-mono text-right text-xs ${changeColor}`}>
        {formatPct(changePct)}
      </td>
      <td className="px-2 py-1.5">
        <Sparkline points={points} />
      </td>
      <td className="px-2 py-1.5 text-right">
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onRemove(ticker);
          }}
          data-testid={`watchlist-remove-${ticker}`}
          className="text-text-muted hover:text-down text-xs"
          aria-label={`Remove ${ticker}`}
        >
          x
        </button>
      </td>
    </tr>
  );
}
