import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid, Legend } from "recharts";
import type { LaneStats } from "../lib/types";

export interface HistoryPoint {
  time: number; // Date.now() in ms — real elapsed time, not a sample index
  [laneId: string]: number;
}

interface Props {
  history: HistoryPoint[];
  lanes: LaneStats[];
}

// Validated categorical set (dataviz skill, dark-surface steps): blue, orange,
// aqua, violet. Yellow/green/red are deliberately excluded here even though
// they're earlier in the standard order — this app reserves them for
// congestion/signal state, and reusing them for lane *identity* in this chart
// would read as a second, conflicting congestion signal.
const LANE_COLORS = ["#3987e5", "#d95926", "#199e70", "#9085e9"];

function secondsAgo(t: number, latest: number): string {
  const delta = Math.round((t - latest) / 1000);
  return delta === 0 ? "now" : `${delta}s`;
}

/** Rolling per-lane vehicle-count trend over the last ~60 samples. */
export function TrafficChart({ history, lanes }: Props) {
  const latest = history.length ? history[history.length - 1].time : Date.now();

  return (
    <div className="chart-panel">
      <h3>Lane occupancy trend</h3>
      <ResponsiveContainer width="100%" height={220}>
        <AreaChart data={history} margin={{ left: 0, right: 8, top: 8, bottom: 0 }}>
          <defs>
            {lanes.map((lane, i) => (
              <linearGradient key={lane.id} id={`fill-${lane.id}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={LANE_COLORS[i % LANE_COLORS.length]} stopOpacity={0.28} />
                <stop offset="100%" stopColor={LANE_COLORS[i % LANE_COLORS.length]} stopOpacity={0.02} />
              </linearGradient>
            ))}
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" vertical={false} />
          <XAxis
            dataKey="time"
            type="number"
            domain={["dataMin", "dataMax"]}
            tickFormatter={(t: number) => secondsAgo(t, latest)}
            stroke="rgba(255,255,255,0.35)"
            tick={{ fontSize: 11 }}
            minTickGap={40}
          />
          <YAxis
            allowDecimals={false}
            domain={[0, (max: number) => Math.max(4, max + 2)]}
            stroke="rgba(255,255,255,0.35)"
            tick={{ fontSize: 11 }}
            width={26}
          />
          <Tooltip
            contentStyle={{ background: "#111827", border: "1px solid #374151", borderRadius: 8, fontSize: 12 }}
            labelFormatter={(t) => secondsAgo(Number(t), latest)}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          {lanes.map((lane, i) => {
            const color = LANE_COLORS[i % LANE_COLORS.length];
            return (
              <Area
                key={lane.id}
                type="monotone"
                dataKey={lane.id}
                name={lane.name}
                stroke={color}
                strokeWidth={2}
                fill={`url(#fill-${lane.id})`}
                dot={false}
                activeDot={{ r: 4 }}
                isAnimationActive={false}
              />
            );
          })}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
