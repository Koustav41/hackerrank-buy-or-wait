"use client";

import React, { useEffect, useState, useRef } from "react";
import { TrendingUp, AlertTriangle } from "@/components/Icons";
import { safeFetch } from "@/lib/api";

export interface TimelinePoint {
  date: string;
  balance: number;
  min_balance: number;
  net_flow: number;
  notes?: string;
}

interface FinancialTimelineProps {
  requestId: string | null;
}

export const FinancialTimeline: React.FC<FinancialTimelineProps> = ({ requestId }) => {
  const [data, setData] = useState<TimelinePoint[]>([]);
  const [loading, setLoading] = useState(false);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!requestId) return;
    fetchTimeline(requestId);
  }, [requestId]);

  const fetchTimeline = async (id: string) => {
    setLoading(true);
    try {
      const points = await safeFetch(`/api/timeline/${id}`);
      if (points) {
        setData(points);
      }
    } catch {
      // Graceful fallback
    } finally {
      setLoading(false);
    }
  };

  if (!requestId || loading) {
    return (
      <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-8 text-center text-slate-400">
        {loading ? "Simulating 90-day cash flow..." : "Select a request to display financial trajectory"}
      </div>
    );
  }

  if (data.length === 0) {
    return null;
  }

  const minBalance = data[0].min_balance;
  const balances = data.map((d) => d.balance);
  const lowestBalance = Math.min(...balances);
  const highestBalance = Math.max(...balances, minBalance);
  const bufferBreached = lowestBalance < minBalance;

  // SVG Chart Geometry
  const width = 800;
  const height = 240;
  const padding = { top: 20, right: 30, bottom: 30, left: 60 };
  const chartW = width - padding.left - padding.right;
  const chartH = height - padding.top - padding.bottom;

  // Min and max for Y-axis with some margin
  const yMin = Math.min(lowestBalance, minBalance) * 0.95;
  const yMax = Math.max(highestBalance, minBalance) * 1.05;
  const yRange = yMax - yMin || 1;

  const getX = (index: number) => padding.left + (index / (data.length - 1)) * chartW;
  const getY = (val: number) => padding.top + chartH - ((val - yMin) / yRange) * chartH;

  // Build SVG Path
  const pointsString = data
    .map((d, i) => `${getX(i)},${getY(d.balance)}`)
    .join(" ");

  const areaD = `M ${getX(0)},${getY(data[0].balance)} ` +
    data.slice(1).map((d, i) => `L ${getX(i + 1)},${getY(d.balance)}`).join(" ") +
    ` L ${getX(data.length - 1)},${padding.top + chartH} L ${getX(0)},${padding.top + chartH} Z`;

  const minLineY = getY(minBalance);

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!svgRef.current) return;
    const rect = svgRef.current.getBoundingClientRect();
    const clientX = e.clientX - rect.left;
    const ratio = (clientX - (padding.left * rect.width) / width) / ((chartW * rect.width) / width);
    const index = Math.round(ratio * (data.length - 1));
    if (index >= 0 && index < data.length) {
      setHoverIndex(index);
    }
  };

  const activePoint = hoverIndex !== null ? data[hoverIndex] : null;

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-6 shadow-2xl space-y-4">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2">
        <div className="flex items-center gap-2">
          <TrendingUp className="w-5 h-5 text-indigo-400" />
          <h3 className="text-base font-bold text-white">90-Day Projected Cash Flow Trajectory</h3>
        </div>
        <div className="flex items-center gap-4 text-xs font-mono">
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-full bg-indigo-500 inline-block"></span>
            <span className="text-slate-300">Projected Balance</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-1 bg-rose-500 inline-block"></span>
            <span className="text-rose-400">Min Reserve Buffer ({minBalance.toLocaleString()})</span>
          </div>
        </div>
      </div>

      {bufferBreached && (
        <div className="bg-rose-950/40 border border-rose-800/60 p-2.5 rounded-lg flex items-center gap-2 text-xs text-rose-300">
          <AlertTriangle className="w-4 h-4 text-rose-400 flex-shrink-0" />
          <span>Warning: Minimum balance reserve is projected to breach without recommended plan or deferral.</span>
        </div>
      )}

      {/* SVG Chart */}
      <div className="relative w-full overflow-hidden">
        <svg
          ref={svgRef}
          viewBox={`0 0 ${width} ${height}`}
          className="w-full h-64 select-none cursor-crosshair"
          onMouseMove={handleMouseMove}
          onMouseLeave={() => setHoverIndex(null)}
        >
          <defs>
            <linearGradient id="areaGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#6366f1" stopOpacity="0.35" />
              <stop offset="100%" stopColor="#6366f1" stopOpacity="0.0" />
            </linearGradient>
          </defs>

          {/* Grid lines */}
          {[0, 0.25, 0.5, 0.75, 1].map((pct, i) => {
            const y = padding.top + chartH * pct;
            const val = yMax - pct * yRange;
            return (
              <g key={i}>
                <line
                  x1={padding.left}
                  y1={y}
                  x2={padding.left + chartW}
                  y2={y}
                  stroke="#1e293b"
                  strokeDasharray="4 4"
                />
                <text
                  x={padding.left - 8}
                  y={y + 4}
                  textAnchor="end"
                  fontSize="10"
                  fill="#64748b"
                  fontFamily="monospace"
                >
                  {val >= 1000 ? `${(val / 1000).toFixed(0)}k` : val.toFixed(0)}
                </text>
              </g>
            );
          })}

          {/* Area Fill */}
          <path d={areaD} fill="url(#areaGradient)" />

          {/* Balance Curve */}
          <polyline
            fill="none"
            stroke="#818cf8"
            strokeWidth="2.5"
            points={pointsString}
          />

          {/* Minimum Balance Line */}
          <line
            x1={padding.left}
            y1={minLineY}
            x2={padding.left + chartW}
            y2={minLineY}
            stroke="#f43f5e"
            strokeWidth="1.5"
            strokeDasharray="5 5"
          />

          {/* X Axis Ticks (Every 15 days) */}
          {data.map((d, i) => {
            if (i % 18 === 0 || i === data.length - 1) {
              const x = getX(i);
              return (
                <text
                  key={i}
                  x={x}
                  y={height - 8}
                  textAnchor="middle"
                  fontSize="10"
                  fill="#64748b"
                  fontFamily="monospace"
                >
                  {d.date.slice(5)}
                </text>
              );
            }
            return null;
          })}

          {/* Hover Crosshair & Tooltip Indicator */}
          {hoverIndex !== null && activePoint && (
            <g>
              <line
                x1={getX(hoverIndex)}
                y1={padding.top}
                x2={getX(hoverIndex)}
                y2={padding.top + chartH}
                stroke="#94a3b8"
                strokeWidth="1"
                strokeDasharray="2 2"
              />
              <circle
                cx={getX(hoverIndex)}
                cy={getY(activePoint.balance)}
                r="4.5"
                fill="#6366f1"
                stroke="#ffffff"
                strokeWidth="2"
              />
            </g>
          )}
        </svg>

        {/* Hover Tooltip Card */}
        {activePoint && hoverIndex !== null && (
          <div
            className="absolute top-2 right-4 bg-slate-950 border border-slate-700/80 p-3 rounded-xl shadow-2xl text-xs font-mono space-y-1 pointer-events-none"
          >
            <div className="text-indigo-300 font-bold">{activePoint.date}</div>
            <div className="text-white">
              Balance: <span className="text-emerald-400 font-bold">{activePoint.balance.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
            </div>
            <div className="text-rose-400">
              Min Reserve: {activePoint.min_balance.toLocaleString(undefined, { minimumFractionDigits: 2 })}
            </div>
            {activePoint.net_flow !== 0 && (
              <div className={activePoint.net_flow > 0 ? "text-emerald-400" : "text-amber-400"}>
                Net Cash Flow: {activePoint.net_flow > 0 ? `+${activePoint.net_flow.toLocaleString()}` : activePoint.net_flow.toLocaleString()}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
