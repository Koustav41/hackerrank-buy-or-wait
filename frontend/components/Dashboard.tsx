"use client";

import React, { useEffect, useState } from "react";
import { CheckCircle2, AlertTriangle, Clock, XCircle, DollarSign, Search, Sparkles } from "@/components/Icons";
import { safeFetch } from "@/lib/api";

export interface RequestSummary {
  request_id: string;
  user_id: string;
  request_date: string;
  requested_amount: number;
  currency: string;
  request_type: string;
  purpose: string;
  amount_safe_to_pay: number;
  affordability_status: string;
  recommended_payment_method: string;
  earliest_date_for_full_payment?: string;
}

export interface StatsSummary {
  total_requests: number;
  affordable_now: number;
  affordable_with_plan: number;
  affordable_later: number;
  not_affordable: number;
  total_safe_amount: number;
  total_requested_amount: number;
}

interface DashboardProps {
  onSelectRequest: (id: string) => void;
  selectedRequestId: string | null;
}

export const Dashboard: React.FC<DashboardProps> = ({ onSelectRequest, selectedRequestId }) => {
  const [stats, setStats] = useState<StatsSummary | null>(null);
  const [requests, setRequests] = useState<RequestSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  useEffect(() => {
    fetchStats();
    fetchRequests();
  }, []);

  const fetchStats = async () => {
    try {
      const data = await safeFetch("/api/stats");
      if (data) {
        setStats(data);
      }
    } catch {
      // Graceful fallback
    }
  };

  const fetchRequests = async () => {
    setLoading(true);
    try {
      const data = await safeFetch("/api/requests?limit=250");
      if (data) {
        setRequests(data);
        if (data.length > 0 && !selectedRequestId) {
          onSelectRequest(data[0].request_id);
        }
      }
    } catch {
      // Graceful fallback
    } finally {
      setLoading(false);
    }
  };

  const filteredRequests = requests.filter((r) => {
    const matchesStatus =
      statusFilter === "all" || r.affordability_status === statusFilter;
    const matchesSearch =
      r.request_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      r.purpose.toLowerCase().includes(searchQuery.toLowerCase()) ||
      r.user_id.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesStatus && matchesSearch;
  });

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "affordable_now":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-950/60 text-emerald-400 border border-emerald-500/30">
            <CheckCircle2 className="w-3.5 h-3.5" /> Affordable Now
          </span>
        );
      case "affordable_with_plan":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-blue-950/60 text-blue-400 border border-blue-500/30">
            <Sparkles className="w-3.5 h-3.5" /> With Plan
          </span>
        );
      case "affordable_later":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-950/60 text-amber-400 border border-amber-500/30">
            <Clock className="w-3.5 h-3.5" /> Affordable Later
          </span>
        );
      case "not_affordable":
      default:
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-950/60 text-rose-400 border border-rose-500/30">
            <XCircle className="w-3.5 h-3.5" /> Not Affordable
          </span>
        );
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Metric Cards */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4 shadow-lg">
            <div className="text-xs text-slate-400 uppercase tracking-wider font-semibold">Total Requests</div>
            <div className="text-2xl font-bold text-white mt-1">{stats.total_requests}</div>
            <div className="text-xs text-slate-500 mt-1">Processed Evaluation Dataset</div>
          </div>
          <div className="bg-emerald-950/30 border border-emerald-800/40 rounded-xl p-4 shadow-lg">
            <div className="text-xs text-emerald-400 uppercase tracking-wider font-semibold">Affordable Now</div>
            <div className="text-2xl font-bold text-emerald-300 mt-1">{stats.affordable_now}</div>
            <div className="text-xs text-emerald-500/80 mt-1">Immediate full pay</div>
          </div>
          <div className="bg-blue-950/30 border border-blue-800/40 rounded-xl p-4 shadow-lg">
            <div className="text-xs text-blue-400 uppercase tracking-wider font-semibold">With Plan</div>
            <div className="text-2xl font-bold text-blue-300 mt-1">{stats.affordable_with_plan}</div>
            <div className="text-xs text-blue-500/80 mt-1">Installment / Partial</div>
          </div>
          <div className="bg-amber-950/30 border border-amber-800/40 rounded-xl p-4 shadow-lg">
            <div className="text-xs text-amber-400 uppercase tracking-wider font-semibold">Affordable Later</div>
            <div className="text-2xl font-bold text-amber-300 mt-1">{stats.affordable_later}</div>
            <div className="text-xs text-amber-500/80 mt-1">Deferred safe date</div>
          </div>
          <div className="bg-rose-950/30 border border-rose-800/40 rounded-xl p-4 shadow-lg">
            <div className="text-xs text-rose-400 uppercase tracking-wider font-semibold">Not Affordable</div>
            <div className="text-2xl font-bold text-rose-300 mt-1">{stats.not_affordable}</div>
            <div className="text-xs text-rose-500/80 mt-1">Breaches reserve buffer</div>
          </div>
        </div>
      )}

      {/* Filter and Search Bar */}
      <div className="flex flex-col md:flex-row gap-3 items-center justify-between bg-slate-900/60 p-3 rounded-xl border border-slate-800">
        <div className="relative w-full md:w-80">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
          <input
            type="text"
            placeholder="Search request, user, purpose..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-slate-950 border border-slate-700/80 text-white rounded-lg pl-9 pr-3 py-1.5 text-sm focus:outline-none focus:border-indigo-500"
          />
        </div>
        <div className="flex gap-2 w-full md:w-auto overflow-x-auto pb-1 md:pb-0">
          {["all", "affordable_now", "affordable_with_plan", "affordable_later", "not_affordable"].map((st) => (
            <button
              key={st}
              onClick={() => setStatusFilter(st)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                statusFilter === st
                  ? "bg-indigo-600 text-white shadow-md shadow-indigo-600/30"
                  : "bg-slate-800/80 text-slate-300 hover:bg-slate-700 hover:text-white"
              }`}
            >
              {st === "all" ? "All Requests" : st.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
            </button>
          ))}
        </div>
      </div>

      {/* Request Table / List */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-xl overflow-hidden shadow-xl">
        <div className="max-h-[380px] overflow-y-auto">
          <table className="w-full text-left border-collapse text-sm">
            <thead className="sticky top-0 bg-slate-950/95 border-b border-slate-800 text-xs uppercase text-slate-400 tracking-wider">
              <tr>
                <th className="p-3">Request ID</th>
                <th className="p-3">Date</th>
                <th className="p-3">User</th>
                <th className="p-3">Purpose & Details</th>
                <th className="p-3 text-right">Requested</th>
                <th className="p-3 text-right">Safe Today</th>
                <th className="p-3 text-center">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/50">
              {loading ? (
                <tr>
                  <td colSpan={7} className="text-center py-8 text-slate-400">
                    Loading requests...
                  </td>
                </tr>
              ) : filteredRequests.length === 0 ? (
                <tr>
                  <td colSpan={7} className="text-center py-8 text-slate-400">
                    No requests found matching criteria.
                  </td>
                </tr>
              ) : (
                filteredRequests.map((req) => (
                  <tr
                    key={req.request_id}
                    onClick={() => onSelectRequest(req.request_id)}
                    className={`cursor-pointer transition-colors ${
                      selectedRequestId === req.request_id
                        ? "bg-indigo-950/40 border-l-4 border-indigo-500 text-white"
                        : "hover:bg-slate-800/40 text-slate-300"
                    }`}
                  >
                    <td className="p-3 font-mono font-semibold text-indigo-300">{req.request_id}</td>
                    <td className="p-3 text-xs text-slate-400">{req.request_date}</td>
                    <td className="p-3 text-xs font-mono text-slate-400">{req.user_id}</td>
                    <td className="p-3 max-w-xs truncate" title={req.purpose}>
                      {req.purpose}
                    </td>
                    <td className="p-3 text-right font-medium">
                      {req.currency} {req.requested_amount.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </td>
                    <td className="p-3 text-right font-mono font-semibold text-emerald-400">
                      {req.currency} {req.amount_safe_to_pay.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </td>
                    <td className="p-3 text-center">{getStatusBadge(req.affordability_status)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
