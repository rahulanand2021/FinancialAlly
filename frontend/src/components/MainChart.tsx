"use client";

import { useMemo } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { usePriceStreamContext } from "@/hooks/PriceStreamContext";
import { useSelection } from "@/hooks/SelectionContext";
import { formatPct, formatPrice } from "@/lib/format";
import Panel from "./Panel";

export default function MainChart() {
  const { selectedTicker } = useSelection();
  const { prices, history } = usePriceStreamContext();

  if (!selectedTicker) {
    return (
      <Panel title="Chart">
        <div className="p-6 text-xs text-text-muted text-center">
          Select a ticker in the watchlist to view its chart.
        </div>
      </Panel>
    );
  }

  const tick = prices[selectedTicker];
  const points = history[selectedTicker] ?? [];
  const price = tick?.price ?? 0;
  const sessionOpen = tick?.session_open ?? price;
  const changePct = sessionOpen ? ((price - sessionOpen) / sessionOpen) * 100 : 0;
  const changeColor =
    changePct > 0 ? "text-up" : changePct < 0 ? "text-down" : "text-flat";

  const data = useMemo(
    () =>
      points.map((p, i) => ({
        i,
        price: p.price,
        timestamp: p.timestamp,
      })),
    [points],
  );

  const lineColor = changePct >= 0 ? "#16c784" : "#ea3943";

  return (
    <Panel
      title={selectedTicker}
      actions={
        <div className="flex items-center gap-3 text-sm">
          <span className="font-mono">{formatPrice(price)}</span>
          <span className={`font-mono text-xs ${changeColor}`}>
            {formatPct(changePct)}
          </span>
        </div>
      }
    >
      {data.length < 2 ? (
        <div className="p-6 text-xs text-text-muted text-center">
          Accumulating price history...
        </div>
      ) : (
        <div className="w-full h-full min-h-[180px]">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 10, right: 16, left: 8, bottom: 10 }}>
              <CartesianGrid stroke="#30363d" strokeDasharray="2 4" />
              <XAxis
                dataKey="i"
                tick={{ fill: "#8b949e", fontSize: 10 }}
                stroke="#30363d"
                hide
              />
              <YAxis
                domain={["auto", "auto"]}
                tick={{ fill: "#8b949e", fontSize: 10 }}
                stroke="#30363d"
                width={50}
                tickFormatter={(v) => formatPrice(v as number)}
              />
              <Tooltip
                contentStyle={{
                  background: "#161b22",
                  border: "1px solid #30363d",
                  fontSize: 12,
                }}
                labelFormatter={(_l, payload) =>
                  payload?.[0]?.payload?.timestamp ?? ""
                }
                formatter={(v: number) => formatPrice(v)}
              />
              <Line
                type="monotone"
                dataKey="price"
                stroke={lineColor}
                strokeWidth={1.75}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </Panel>
  );
}
