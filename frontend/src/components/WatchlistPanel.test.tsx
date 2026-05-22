import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { PriceStreamProvider } from "@/hooks/PriceStreamContext";
import { SelectionProvider } from "@/hooks/SelectionContext";
import WatchlistPanel from "./WatchlistPanel";

const watchlistRef: { entries: { ticker: string; price: number; prev_price: number; session_open: number; session_change_pct: number }[] } = {
  entries: [
    {
      ticker: "AAPL",
      price: 192.34,
      prev_price: 191.8,
      session_open: 189.5,
      session_change_pct: 1.5,
    },
  ],
};

function renderPanel() {
  return render(
    <PriceStreamProvider override={{ prices: {}, history: {}, status: "connected" }}>
      <SelectionProvider>
        <WatchlistPanel />
      </SelectionProvider>
    </PriceStreamProvider>,
  );
}

beforeEach(() => {
  watchlistRef.entries = [
    {
      ticker: "AAPL",
      price: 192.34,
      prev_price: 191.8,
      session_open: 189.5,
      session_change_pct: 1.5,
    },
  ];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      const method = init?.method ?? "GET";
      if (url.endsWith("/api/watchlist") && method === "GET") {
        return new Response(JSON.stringify(watchlistRef.entries), { status: 200 });
      }
      if (url.endsWith("/api/watchlist") && method === "POST") {
        const body = JSON.parse(init?.body as string);
        const entry = {
          ticker: body.ticker,
          price: 100,
          prev_price: 100,
          session_open: 100,
          session_change_pct: 0,
        };
        watchlistRef.entries.push(entry);
        return new Response(JSON.stringify(entry), { status: 200 });
      }
      if (url.match(/\/api\/watchlist\/[^/]+$/) && method === "DELETE") {
        const ticker = decodeURIComponent(url.split("/").pop() ?? "");
        watchlistRef.entries = watchlistRef.entries.filter((e) => e.ticker !== ticker);
        return new Response(null, { status: 204 });
      }
      return new Response("{}", { status: 200 });
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("WatchlistPanel", () => {
  it("loads and renders the initial watchlist", async () => {
    renderPanel();
    expect(await screen.findByText("AAPL")).toBeInTheDocument();
  });

  it("adds a new ticker on form submit", async () => {
    renderPanel();
    await screen.findByText("AAPL");
    const input = screen.getByPlaceholderText("ADD");
    fireEvent.change(input, { target: { value: "nvda" } });
    fireEvent.click(screen.getByRole("button", { name: "+" }));
    await waitFor(() => {
      expect(screen.getByText("NVDA")).toBeInTheDocument();
    });
  });

  it("removes a ticker when the remove button is clicked", async () => {
    renderPanel();
    await screen.findByText("AAPL");
    fireEvent.click(screen.getByRole("button", { name: /Remove AAPL/i }));
    await waitFor(() => {
      expect(screen.queryByText("AAPL")).not.toBeInTheDocument();
    });
  });
});
