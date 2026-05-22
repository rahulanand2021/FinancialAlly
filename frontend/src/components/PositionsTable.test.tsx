import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { PriceStreamProvider } from "@/hooks/PriceStreamContext";
import { PortfolioProvider } from "@/hooks/PortfolioContext";
import { SelectionProvider } from "@/hooks/SelectionContext";
import PositionsTable from "./PositionsTable";

function renderTable() {
  return render(
    <PriceStreamProvider
      override={{
        prices: {
          AAPL: {
            ticker: "AAPL",
            price: 200,
            prev_price: 198,
            session_open: 190,
            timestamp: "t",
            direction: "up",
          },
        },
        history: {},
        status: "connected",
      }}
    >
      <PortfolioProvider>
        <SelectionProvider>
          <PositionsTable />
        </SelectionProvider>
      </PortfolioProvider>
    </PriceStreamProvider>,
  );
}

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      new Response(
        JSON.stringify({
          cash_balance: 5000,
          total_value: 7000,
          positions: [
            {
              ticker: "AAPL",
              quantity: 10,
              avg_cost: 180,
              current_price: 200,
              unrealized_pnl: 200,
              unrealized_pnl_pct: 11.11,
            },
          ],
        }),
        { status: 200 },
      ),
    ),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("PositionsTable", () => {
  it("computes live P&L from SSE prices, not the stale current_price", async () => {
    renderTable();
    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });
    // (200 - 180) * 10 = $200.00
    expect(screen.getByText("$200.00")).toBeInTheDocument();
    // +11.11%
    expect(screen.getByText("+11.11%")).toBeInTheDocument();
  });
});
