/**
 * Estimated survival over time: one series, hand-written SVG (no chart library).
 * Hover, touch or arrow keys move a crosshair that reads out the year and the share alive.
 */

import { useId, useState, type KeyboardEvent, type PointerEvent } from "react";
import { chartEndYears, formatPercent } from "./format";

const W = 640;
const H = 260;
const M = { top: 12, right: 16, bottom: 34, left: 48 };
const PLOT_W = W - M.left - M.right;
const PLOT_H = H - M.top - M.bottom;

interface Props {
  curve: [number, number][];
  medianYears: number | null;
}

export function SurvivalChart({ curve, medianYears }: Props) {
  const end = chartEndYears(curve);
  const points = curve.filter(([t]) => t <= end);
  const x = (t: number) => M.left + (t / end) * PLOT_W;
  const y = (s: number) => M.top + (1 - s) * PLOT_H;
  const [active, setActive] = useState<number | null>(null);
  const titleId = useId();

  const line = points.map(([t, s], k) => `${k ? "L" : "M"}${x(t).toFixed(1)},${y(s).toFixed(1)}`).join("");
  const area = `${line}L${x(points.at(-1)![0]).toFixed(1)},${y(0)}L${x(0)},${y(0)}Z`;
  const xTicks = Array.from({ length: 6 }, (_, k) => (end / 5) * k);

  const fromPointer = (e: PointerEvent<SVGSVGElement>) => {
    const box = e.currentTarget.getBoundingClientRect();
    const t = (((e.clientX - box.left) / box.width) * W - M.left) / PLOT_W * end;
    const k = Math.round((Math.min(Math.max(t, 0), end) / end) * (points.length - 1));
    setActive(k);
  };
  const onKey = (e: KeyboardEvent<SVGSVGElement>) => {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    e.preventDefault();
    const step = e.key === "ArrowRight" ? 1 : -1;
    setActive((k) => Math.min(Math.max((k ?? 0) + step, 0), points.length - 1));
  };

  const hover = active === null ? undefined : points[active];
  const label = hover && `Year ${hover[0] % 1 ? hover[0].toFixed(2) : hover[0]}: ${formatPercent(hover[1])} alive`;
  const labelLeft = hover !== undefined && x(hover[0]) > W - 170;

  return (
    <svg
      className="chart"
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-labelledby={titleId}
      tabIndex={0}
      onPointerMove={fromPointer}
      onPointerDown={fromPointer}
      onPointerLeave={() => setActive(null)}
      onKeyDown={onKey}
      onBlur={() => setActive(null)}
    >
      <title id={titleId}>
        Estimated share of people alive over the next {end} years. Use the left and right arrow keys to read values.
      </title>
      {[0, 0.25, 0.5, 0.75, 1].map((s) => (
        <g key={s}>
          <line className="grid" x1={M.left} x2={W - M.right} y1={y(s)} y2={y(s)} />
          <text className="tick" x={M.left - 8} y={y(s)} textAnchor="end" dominantBaseline="middle">
            {s * 100}%
          </text>
        </g>
      ))}
      {xTicks.map((t) => (
        <text key={t} className="tick" x={x(t)} y={H - M.bottom + 18} textAnchor="middle">
          {t}
        </text>
      ))}
      <text className="tick" x={W - M.right} y={H - 2} textAnchor="end">
        years from now
      </text>
      <path className="area" d={area} />
      <path className="line" d={line} />
      {medianYears !== null && medianYears <= end && (
        <g className="median">
          <line x1={x(medianYears)} x2={x(medianYears)} y1={y(0.5)} y2={y(0)} />
          <text x={x(medianYears) + 6} y={y(0.5) - 8}>
            median
          </text>
        </g>
      )}
      {hover && (
        <g className="crosshair" aria-hidden="true">
          <line x1={x(hover[0])} x2={x(hover[0])} y1={M.top} y2={y(0)} />
          <circle cx={x(hover[0])} cy={y(hover[1])} r={5} />
          <text x={x(hover[0]) + (labelLeft ? -10 : 10)} y={M.top + 14} textAnchor={labelLeft ? "end" : "start"}>
            {label}
          </text>
        </g>
      )}
    </svg>
  );
}
