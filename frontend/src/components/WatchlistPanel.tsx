"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { WatchlistEntry } from "@/types/api";
import Panel from "./Panel";
import WatchlistRow from "./WatchlistRow";

export default function WatchlistPanel() {
  const [entries, setEntries] = useState<WatchlistEntry[]>([]);
  const [tickerInput, setTickerInput] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const list = await api.getWatchlist();
      setEntries(list);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    const symbol = tickerInput.trim().toUpperCase();
    if (!symbol) return;
    try {
      const entry = await api.addTicker(symbol);
      setEntries((prev) =>
        prev.some((p) => p.ticker === entry.ticker) ? prev : [...prev, entry],
      );
      setTickerInput("");
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const handleRemove = async (ticker: string) => {
    try {
      await api.removeTicker(ticker);
      setEntries((prev) => prev.filter((p) => p.ticker !== ticker));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <Panel
      title="Watchlist"
      actions={
        <form onSubmit={handleAdd} className="flex gap-1">
          <input
            value={tickerInput}
            onChange={(e) => setTickerInput(e.target.value)}
            placeholder="ADD"
            maxLength={8}
            data-testid="watchlist-add-input"
            className="w-16 px-2 py-0.5 text-xs font-mono uppercase bg-bg-base border border-border-muted rounded focus:outline-none focus:border-accent-blue"
          />
          <button
            type="submit"
            data-testid="watchlist-add-button"
            className="text-xs px-2 py-0.5 bg-accent-blue/20 text-accent-blue border border-accent-blue/40 rounded hover:bg-accent-blue/30"
          >
            +
          </button>
        </form>
      }
    >
      {error && (
        <div className="px-3 py-1 text-xs text-down border-b border-border-muted">
          {error}
        </div>
      )}
      <table data-testid="watchlist" className="w-full text-sm">
        <thead>
          <tr className="text-text-muted text-xs uppercase tracking-wider">
            <th className="px-2 py-1 text-left font-normal">Sym</th>
            <th className="px-2 py-1 text-right font-normal">Price</th>
            <th className="px-2 py-1 text-right font-normal">Chg %</th>
            <th className="px-2 py-1 text-left font-normal">Trend</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {entries.map((e) => (
            <WatchlistRow
              key={e.ticker}
              ticker={e.ticker}
              fallbackPrice={e.price}
              fallbackSessionOpen={e.session_open}
              fallbackChangePct={e.session_change_pct}
              onRemove={handleRemove}
            />
          ))}
          {entries.length === 0 && !error && (
            <tr>
              <td colSpan={5} className="px-3 py-4 text-center text-text-muted text-xs">
                Loading watchlist...
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </Panel>
  );
}
