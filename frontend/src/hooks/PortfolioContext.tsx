"use client";

import {
  createContext,
  ReactNode,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { api } from "@/lib/api";
import { Portfolio } from "@/types/api";
import { usePriceStreamContext } from "./PriceStreamContext";

interface PortfolioContextValue {
  portfolio: Portfolio | null;
  /** Total value recomputed live from positions + latest SSE prices. */
  liveTotalValue: number;
  refresh: () => Promise<void>;
}

const PortfolioContext = createContext<PortfolioContextValue | null>(null);

export function PortfolioProvider({ children }: { children: ReactNode }) {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const { prices } = usePriceStreamContext();

  const refresh = useCallback(async () => {
    try {
      const p = await api.getPortfolio();
      setPortfolio(p);
    } catch {
      // Surface upstream; individual components decide how to display.
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const liveTotalValue = (() => {
    if (!portfolio) return 0;
    const positionsValue = portfolio.positions.reduce((sum, pos) => {
      const livePrice = prices[pos.ticker]?.price ?? pos.current_price;
      return sum + pos.quantity * livePrice;
    }, 0);
    return portfolio.cash_balance + positionsValue;
  })();

  return (
    <PortfolioContext.Provider value={{ portfolio, liveTotalValue, refresh }}>
      {children}
    </PortfolioContext.Provider>
  );
}

export function usePortfolio(): PortfolioContextValue {
  const ctx = useContext(PortfolioContext);
  if (!ctx) {
    throw new Error("usePortfolio must be used inside a PortfolioProvider");
  }
  return ctx;
}
