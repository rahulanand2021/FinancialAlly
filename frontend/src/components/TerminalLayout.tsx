"use client";

import { PortfolioProvider } from "@/hooks/PortfolioContext";
import { PriceStreamProvider } from "@/hooks/PriceStreamContext";
import { SelectionProvider } from "@/hooks/SelectionContext";
import Header from "./Header";
import WatchlistPanel from "./WatchlistPanel";
import MainChart from "./MainChart";
import PortfolioHeatmap from "./PortfolioHeatmap";
import PnlChart from "./PnlChart";
import PositionsTable from "./PositionsTable";
import TradeBar from "./TradeBar";
import ChatPanel from "./ChatPanel";

/**
 * Top-level terminal grid: header above, watchlist left, chat right,
 * and a 2x2 center grid for chart / heatmap / pnl / positions.
 * Trade bar sits above the positions table in the center column.
 */
export default function TerminalLayout() {
  return (
    <PriceStreamProvider>
      <PortfolioProvider>
        <SelectionProvider>
          <TerminalGrid />
        </SelectionProvider>
      </PortfolioProvider>
    </PriceStreamProvider>
  );
}

function TerminalGrid() {
  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden">
      <Header />

      <main className="flex-1 grid gap-2 p-2 overflow-hidden
                       grid-cols-[260px_1fr_320px]
                       grid-rows-[1fr]">
        <aside className="overflow-hidden">
          <WatchlistPanel />
        </aside>

        <section className="grid grid-cols-2 grid-rows-[1fr_1fr_auto_220px] gap-2 overflow-hidden">
          <div className="col-span-2 row-span-1 min-h-0">
            <MainChart />
          </div>
          <div className="min-h-0">
            <PortfolioHeatmap />
          </div>
          <div className="min-h-0">
            <PnlChart />
          </div>
          <div className="col-span-2">
            <TradeBar />
          </div>
          <div className="col-span-2 min-h-0">
            <PositionsTable />
          </div>
        </section>

        <aside className="overflow-hidden">
          <ChatPanel />
        </aside>
      </main>
    </div>
  );
}

