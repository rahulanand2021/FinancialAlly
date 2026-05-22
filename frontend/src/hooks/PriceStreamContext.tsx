"use client";

import { createContext, ReactNode, useContext } from "react";
import { ConnectionStatus, PriceTick } from "@/types/api";
import { HistoryMap, PriceMap, usePriceStream } from "./usePriceStream";

interface PriceStreamContextValue {
  prices: PriceMap;
  history: HistoryMap;
  status: ConnectionStatus;
}

const PriceStreamContext = createContext<PriceStreamContextValue | null>(null);

interface PriceStreamProviderProps {
  children: ReactNode;
  /** Test/Storybook hook: skip the EventSource and use injected values. */
  override?: PriceStreamContextValue;
}

export function PriceStreamProvider({
  children,
  override,
}: PriceStreamProviderProps) {
  const live = usePriceStream();
  const value = override ?? live;
  return (
    <PriceStreamContext.Provider value={value}>
      {children}
    </PriceStreamContext.Provider>
  );
}

export function usePriceStreamContext(): PriceStreamContextValue {
  const ctx = useContext(PriceStreamContext);
  if (!ctx) {
    throw new Error(
      "usePriceStreamContext must be used inside a PriceStreamProvider",
    );
  }
  return ctx;
}

/** Convenience hook returning the latest tick for a single ticker, if any. */
export function useTickerPrice(ticker: string): PriceTick | undefined {
  const { prices } = usePriceStreamContext();
  return prices[ticker];
}
