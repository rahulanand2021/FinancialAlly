"use client";

import { useMemo } from "react";
import { ResponsiveContainer, Treemap } from "recharts";
import { usePortfolio } from "@/hooks/PortfolioContext";
import { usePriceStreamContext } from "@/hooks/PriceStreamContext";
import { useSelection } from "@/hooks/SelectionContext";
import { formatPct } from "@/lib/format";
import Panel from "./Panel";

interface HeatmapNode {
  name: string;
  size: number;
  pnlPct: number;
}

function pnlColor(pct: number): string {
  if (pct === 0) return "#30363d";
  const clamped = Math.max(-10, Math.min(10, pct));
  const intensity = Math.abs(clamped) / 10;
  const base = clamped >= 0 ? [22, 199, 132] : [234, 57, 67];
  const dark = [22, 27, 34];
  const mix = base.map((c, i) =>
    Math.round(dark[i] + (c - dark[i]) * (0.3 + intensity * 0.7)),
  );
  return `rgb(${mix[0]},${mix[1]},${mix[2]})`;
}

interface ContentProps {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  name?: string;
  payload?: HeatmapNode;
  onSelect?: (ticker: string) => void;
}

function HeatmapCell({ x = 0, y = 0, width = 0, height = 0, name = "", payload, onSelect }: ContentProps) {
  const pct = payload?.pnlPct ?? 0;
  const fill = pnlColor(pct);
  const showLabel = width > 40 && height > 28;
  return (
    <g
      data-testid={name ? `heatmap-cell-${name}` : undefined}
      style={{ cursor: "pointer" }}
      onClick={() => name && onSelect?.(name)}
    >
      <rect x={x} y={y} width={width} height={height} fill={fill} stroke="#0d1117" />
      {showLabel && (
        <>
          <text
            x={x + width / 2}
            y={y + height / 2 - 4}
            textAnchor="middle"
            fill="#e6edf3"
            fontSize={12}
            fontWeight={600}
          >
            {name}
          </text>
          <text
            x={x + width / 2}
            y={y + height / 2 + 10}
            textAnchor="middle"
            fill="#e6edf3"
            fontSize={10}
          >
            {formatPct(pct)}
          </text>
        </>
      )}
    </g>
  );
}

export default function PortfolioHeatmap() {
  const { portfolio } = usePortfolio();
  const { prices } = usePriceStreamContext();
  const { selectTicker } = useSelection();

  const data: HeatmapNode[] = useMemo(() => {
    if (!portfolio) return [];
    return portfolio.positions
      .map((p) => {
        const livePrice = prices[p.ticker]?.price ?? p.current_price;
        const value = p.quantity * livePrice;
        const pnlPct = p.avg_cost
          ? ((livePrice - p.avg_cost) / p.avg_cost) * 100
          : 0;
        return { name: p.ticker, size: Math.max(value, 0.01), pnlPct };
      })
      .filter((d) => d.size > 0);
  }, [portfolio, prices]);

  return (
    <Panel title="Portfolio Heatmap">
      {data.length === 0 ? (
        <div className="p-6 text-xs text-text-muted text-center">
          No open positions yet. Place a trade to populate the heatmap.
        </div>
      ) : (
        <div data-testid="portfolio-heatmap" className="w-full h-[180px]">
          <ResponsiveContainer width="100%" height={180}>
            <Treemap
              data={data}
              dataKey="size"
              stroke="#0d1117"
              isAnimationActive={false}
              content={
                <HeatmapCell onSelect={selectTicker} /> as unknown as React.ReactElement
              }
            />
          </ResponsiveContainer>
        </div>
      )}
    </Panel>
  );
}
