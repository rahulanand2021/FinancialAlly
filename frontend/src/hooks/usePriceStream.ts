"use client";

import { useEffect, useRef, useState } from "react";
import { ConnectionStatus, PriceTick } from "@/types/api";

export type PriceMap = Record<string, PriceTick>;
export type HistoryMap = Record<string, PricePoint[]>;

export interface PricePoint {
  price: number;
  timestamp: string;
}

interface UsePriceStreamResult {
  prices: PriceMap;
  history: HistoryMap;
  status: ConnectionStatus;
}

/** Max history points retained per ticker — caps memory while leaving plenty
 *  of room for sparklines and the main chart accumulated since page load. */
const HISTORY_LIMIT = 600;

const SSE_URL = "/api/stream/prices";

/**
 * Opens a single EventSource to the SSE price stream and exposes the latest
 * tick per ticker. Connection state transitions:
 *   open → "connected"
 *   error while OPEN/CONNECTING → "reconnecting" (EventSource auto-retries)
 *   close() → "disconnected"
 */
export function usePriceStream(): UsePriceStreamResult {
  const [prices, setPrices] = useState<PriceMap>({});
  const [history, setHistory] = useState<HistoryMap>({});
  const [status, setStatus] = useState<ConnectionStatus>("reconnecting");
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const es = new EventSource(SSE_URL);
    esRef.current = es;

    es.onopen = () => setStatus("connected");

    es.onmessage = (event) => {
      try {
        const tick = JSON.parse(event.data) as PriceTick;
        if (!tick?.ticker) return;
        setPrices((prev) => ({ ...prev, [tick.ticker]: tick }));
        setHistory((prev) => {
          const existing = prev[tick.ticker] ?? [];
          const next = [
            ...existing,
            { price: tick.price, timestamp: tick.timestamp },
          ];
          if (next.length > HISTORY_LIMIT) {
            next.splice(0, next.length - HISTORY_LIMIT);
          }
          return { ...prev, [tick.ticker]: next };
        });
      } catch {
        // Malformed event — ignore, next event will recover.
      }
    };

    es.onerror = () => {
      // EventSource transitions to CLOSED if the server is unreachable for too
      // long; otherwise it retries automatically.
      if (es.readyState === EventSource.CLOSED) {
        setStatus("disconnected");
      } else {
        setStatus("reconnecting");
      }
    };

    return () => {
      es.close();
      esRef.current = null;
    };
  }, []);

  return { prices, history, status };
}
