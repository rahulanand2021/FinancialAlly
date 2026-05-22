"use client";

import { usePortfolio } from "@/hooks/PortfolioContext";
import { usePriceStreamContext } from "@/hooks/PriceStreamContext";
import { useSelection } from "@/hooks/SelectionContext";
import { useFlashOnChange } from "@/hooks/useFlashOnChange";
import {
  formatCurrency,
  formatPct,
  formatPrice,
  formatQuantity,
} from "@/lib/format";
import Panel from "./Panel";

function PositionRow({
  ticker,
  quantity,
  avgCost,
}: {
  ticker: string;
  quantity: number;
  avgCost: number;
}) {
  const { prices } = usePriceStreamContext();
  const { selectTicker, selectedTicker } = useSelection();
  const tick = prices[ticker];
  const livePrice = tick?.price ?? avgCost;
  const pnl = (livePrice - avgCost) * quantity;
  const pnlPct = avgCost ? ((livePrice - avgCost) / avgCost) * 100 : 0;
  const flashClass = useFlashOnChange(tick?.price);
  const pnlColor = pnl > 0 ? "text-up" : pnl < 0 ? "text-down" : "text-flat";
  const isSelected = selectedTicker === ticker;

  return (
    <tr
      data-testid={`position-row-${ticker}`}
      onClick={() => selectTicker(ticker)}
      className={`border-b border-border-muted cursor-pointer hover:bg-bg-panel-hover ${
        isSelected ? "bg-bg-panel-hover" : ""
      }`}
    >
      <td className="px-2 py-1.5 font-mono font-semibold">{ticker}</td>
      <td className="px-2 py-1.5 font-mono text-right">{formatQuantity(quantity)}</td>
      <td className="px-2 py-1.5 font-mono text-right">{formatPrice(avgCost)}</td>
      <td className={`px-2 py-1.5 font-mono text-right ${flashClass}`}>
        {formatPrice(livePrice)}
      </td>
      <td className={`px-2 py-1.5 font-mono text-right ${pnlColor}`}>
        {formatCurrency(pnl)}
      </td>
      <td className={`px-2 py-1.5 font-mono text-right text-xs ${pnlColor}`}>
        {formatPct(pnlPct)}
      </td>
    </tr>
  );
}

export default function PositionsTable() {
  const { portfolio } = usePortfolio();
  const positions = portfolio?.positions ?? [];

  return (
    <Panel title="Positions">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-text-muted text-xs uppercase tracking-wider">
            <th className="px-2 py-1 text-left font-normal">Sym</th>
            <th className="px-2 py-1 text-right font-normal">Qty</th>
            <th className="px-2 py-1 text-right font-normal">Avg</th>
            <th className="px-2 py-1 text-right font-normal">Last</th>
            <th className="px-2 py-1 text-right font-normal">P&L</th>
            <th className="px-2 py-1 text-right font-normal">P&L %</th>
          </tr>
        </thead>
        <tbody>
          {positions.length === 0 ? (
            <tr>
              <td colSpan={6} className="px-3 py-4 text-center text-text-muted text-xs">
                No open positions.
              </td>
            </tr>
          ) : (
            positions.map((p) => (
              <PositionRow
                key={p.ticker}
                ticker={p.ticker}
                quantity={p.quantity}
                avgCost={p.avg_cost}
              />
            ))
          )}
        </tbody>
      </table>
    </Panel>
  );
}
