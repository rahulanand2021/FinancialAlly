"use client";

import { PricePoint } from "@/hooks/usePriceStream";

interface SparklineProps {
  points: PricePoint[];
  width?: number;
  height?: number;
  /** Stroke color override; defaults to up/down based on first vs last point. */
  color?: string;
}

/** Lightweight SVG sparkline — no charting library needed.
 *  Returns an empty placeholder while fewer than 2 points have arrived. */
export default function Sparkline({
  points,
  width = 80,
  height = 24,
  color,
}: SparklineProps) {
  if (points.length < 2) {
    return <svg width={width} height={height} aria-hidden="true" />;
  }

  const values = points.map((p) => p.price);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const step = width / (values.length - 1);

  const path = values
    .map((v, i) => {
      const x = i * step;
      const y = height - ((v - min) / range) * height;
      return `${i === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");

  const trendColor =
    color ?? (values[values.length - 1] >= values[0] ? "#16c784" : "#ea3943");

  return (
    <svg width={width} height={height} aria-hidden="true">
      <path
        d={path}
        fill="none"
        stroke={trendColor}
        strokeWidth={1.25}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}
