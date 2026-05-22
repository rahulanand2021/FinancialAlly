"use client";

import { useEffect, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "@/lib/api";
import { PortfolioSnapshot } from "@/types/api";
import { formatCurrency } from "@/lib/format";
import Panel from "./Panel";

const POLL_INTERVAL_MS = 30_000;

export default function PnlChart() {
  const [snapshots, setSnapshots] = useState<PortfolioSnapshot[]>([]);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const data = await api.getPortfolioHistory();
        if (!cancelled) setSnapshots(data);
      } catch {
        // Leave previous data on transient error.
      }
    };

    void load();
    const id = setInterval(load, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const data = snapshots.map((s, i) => ({
    i,
    value: s.total_value,
    timestamp: s.timestamp,
  }));

  return (
    <Panel title="P&L">
      {data.length < 2 ? (
        <div className="p-6 text-xs text-text-muted text-center">
          Collecting portfolio snapshots...
        </div>
      ) : (
        <div className="w-full h-full min-h-[160px]">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 10, right: 16, left: 8, bottom: 10 }}>
              <CartesianGrid stroke="#30363d" strokeDasharray="2 4" />
              <XAxis dataKey="i" hide />
              <YAxis
                domain={["auto", "auto"]}
                tick={{ fill: "#8b949e", fontSize: 10 }}
                stroke="#30363d"
                width={64}
                tickFormatter={(v) => formatCurrency(v as number)}
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
                formatter={(v: number) => formatCurrency(v)}
              />
              <Line
                type="monotone"
                dataKey="value"
                stroke="#209dd7"
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
