import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid, Legend } from "recharts";
import type { LaneStats } from "../lib/types";

export interface HistoryPoint {
  t: number;
  [laneId: string]: number;
}

interface Props {
  history: HistoryPoint[];
  lanes: LaneStats[];
}

const LINE_COLORS = ["#4ade80", "#38bdf8", "#f472b6", "#fbbf24"];

/** Rolling per-lane vehicle-count trend, last N samples. */
export function TrafficChart({ history, lanes }: Props) {
  return (
    <div className="chart-panel">
      <h3>Lane occupancy trend</h3>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={history}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
          <XAxis dataKey="t" tick={false} stroke="rgba(255,255,255,0.3)" />
          <YAxis allowDecimals={false} stroke="rgba(255,255,255,0.5)" width={28} />
          <Tooltip
            contentStyle={{ background: "#111827", border: "1px solid #374151", borderRadius: 8 }}
            labelFormatter={() => ""}
          />
          <Legend />
          {lanes.map((lane, i) => (
            <Line
              key={lane.id}
              type="monotone"
              dataKey={lane.id}
              name={lane.name}
              stroke={LINE_COLORS[i % LINE_COLORS.length]}
              dot={false}
              strokeWidth={2}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
