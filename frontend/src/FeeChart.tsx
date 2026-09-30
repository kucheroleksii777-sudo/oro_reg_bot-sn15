import { memo } from "react";
import {
  CartesianGrid,
  Line,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  XAxis,
  YAxis,
  ComposedChart,
} from "recharts";

import type { FeePoint } from "./api";

const mono =
  'ui-monospace, "SFMono-Regular", "Cascadia Mono", "Roboto Mono", Menlo, Consolas, monospace';

function AxisValueLabel({
  viewBox,
  value,
  fill = "#c5c8ce",
  stroke,
}: {
  viewBox?: { x?: number; y?: number; width?: number };
  value?: string;
  fill?: string;
  stroke?: string;
}) {
  if (value == null || viewBox?.y == null) {
    return null;
  }
  const x = (viewBox.x ?? 0) + (viewBox.width ?? 0) + 8;
  const y = viewBox.y;
  return (
    <g>
      <rect
        x={x - 4}
        y={y - 8}
        width={66}
        height={16}
        rx={3}
        fill="#0b0e12"
        stroke={stroke}
        strokeWidth={stroke ? 1 : 0}
      />
      <text x={x} y={y} fill={fill} fontSize={11} fontFamily={mono} dominantBaseline="middle">
        {value}
      </text>
    </g>
  );
}

function formatTime(timestamp: number): string {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Tokyo",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(timestamp));
}

type Props = {
  data: FeePoint[];
  xDomain: [number, number];
  xTicks: number[];
  yDomain: [number, number];
  feeTao: number | null;
  standardTao: number | null;
  feeDot: { t: number; tao: number } | null;
};

function FeeChartInner({ data, xDomain, xTicks, yDomain, feeTao, standardTao, feeDot }: Props) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={data} margin={{ top: 18, right: 12, left: 16, bottom: 28 }}>
        <CartesianGrid stroke="#222830" vertical={false} />
        <XAxis
          dataKey="t"
          type="number"
          domain={xDomain}
          ticks={xTicks}
          allowDataOverflow
          tickFormatter={formatTime}
          tick={{ fill: "#8a8f98", fontSize: 11 }}
          axisLine={{ stroke: "#2e343c" }}
          tickLine={false}
        />
        <YAxis
          orientation="right"
          domain={yDomain}
          allowDataOverflow
          tickFormatter={(v: number) => `τ${Number(v).toFixed(3)}`}
          tick={{ fill: "#8a8f98", fontSize: 11, fontFamily: mono }}
          axisLine={{ stroke: "#2e343c" }}
          tickLine={false}
          width={70}
        />
        {standardTao != null ? (
          <ReferenceLine
            y={standardTao}
            stroke="#e89b25"
            strokeDasharray="6 4"
            ifOverflow="extendDomain"
            label={
              <AxisValueLabel value={`τ${standardTao.toFixed(3)}`} fill="#e89b25" stroke="#e89b25" />
            }
          />
        ) : null}
        {feeTao != null ? (
          <ReferenceLine
            y={feeTao}
            stroke="#4ea1ff"
            strokeOpacity={0.35}
            strokeDasharray="4 4"
            ifOverflow="extendDomain"
            label={<AxisValueLabel value={`τ${feeTao.toFixed(3)}`} fill="#4ea1ff" stroke="#4ea1ff" />}
          />
        ) : null}
        <Line
          type="linear"
          dataKey="tao"
          stroke="#4ea1ff"
          strokeWidth={2}
          dot={false}
          isAnimationActive={false}
          name="fee"
        />
        {feeDot ? (
          <ReferenceDot
            x={feeDot.t}
            y={feeDot.tao}
            r={9}
            fill="none"
            stroke="#4ea1ff"
            strokeWidth={2}
            ifOverflow="visible"
            className="fee-dot-ring"
          />
        ) : null}
        {feeDot ? (
          <ReferenceDot
            x={feeDot.t}
            y={feeDot.tao}
            r={6}
            fill="#4ea1ff"
            stroke="#d6e8ff"
            strokeWidth={2}
            ifOverflow="visible"
          />
        ) : null}
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export const FeeChart = memo(FeeChartInner);
