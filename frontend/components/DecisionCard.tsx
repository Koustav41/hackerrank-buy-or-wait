"use client";

import React, { useEffect, useState } from "react";
import { ShieldCheck, Calendar, CreditCard, AlertCircle, ArrowRight, Wallet, CheckCircle } from "@/components/Icons";

import { safeFetch } from "@/lib/api";

export interface DecisionDetail {
  request_id: string;
  user_id: string;
  request_date: string;
  requested_amount: number;
  currency: string;
  request_type: string;
  request_text: string;
  desired_completion_date?: string;
  allows_partial_payment: boolean;
  amount_safe_to_pay: number;
  affordability_status: string;
  recommended_payment_method: string;
  payment_plan: string;
  earliest_date_for_full_payment?: string;
  spending_changes_needed: string;
  decision_explanation: string;
  current_balance: number;
  min_balance_to_keep: number;
  financial_priorities: string;
  payment_options: any[];
}

interface DecisionCardProps {
  requestId: string | null;
}

export const DecisionCard: React.FC<DecisionCardProps> = ({ requestId }) => {
  const [detail, setDetail] = useState<DecisionDetail | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!requestId) return;
    fetchDetail(requestId);
  }, [requestId]);

  const fetchDetail = async (id: string) => {
    setLoading(true);
    try {
      const data = await safeFetch(`/api/requests/${id}`);
      if (data) {
        setDetail(data);
      }
    } catch {
      // Graceful fallback without triggering overlay
    } finally {
      setLoading(false);
    }
  };

  if (!requestId || loading || !detail) {
    return (
      <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-8 text-center text-slate-400">
        {loading
          ? "Loading decision details..."
          : "Select a request from above to view the AI decision (Ensure backend is running on http://127.0.0.1:8000)"}
      </div>
    );
  }

  // Parse payment plan
  const planItems =
    detail.payment_plan && detail.payment_plan.toLowerCase() !== "none"
      ? detail.payment_plan.split("|").map((p) => {
          const [d, a] = p.split(":");
          return { date: d?.trim(), amount: parseFloat(a?.trim() || "0") };
        })
      : [];

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-6 shadow-2xl space-y-6">
      {/* Header Info */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 pb-4 border-b border-slate-800">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xl font-bold text-white font-mono">{detail.request_id}</span>
            <span className="px-2.5 py-0.5 rounded text-xs font-semibold uppercase bg-slate-800 text-slate-300">
              {detail.request_type}
            </span>
          </div>
          <p className="text-sm text-slate-400 mt-1 max-w-2xl">{detail.request_text}</p>
        </div>
        <div className="text-right">
          <div className="text-xs uppercase tracking-wider text-slate-400 font-medium">Requested Amount</div>
          <div className="text-2xl font-bold text-white font-mono">
            {detail.currency} {detail.requested_amount.toLocaleString(undefined, { minimumFractionDigits: 2 })}
          </div>
          <div className="text-xs text-slate-400 mt-0.5">Date: {detail.request_date}</div>
        </div>
      </div>

      {/* Hero Decision Section */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Safe Amount Hero */}
        <div className="bg-gradient-to-br from-emerald-950/60 to-slate-900 border border-emerald-500/40 rounded-xl p-5 shadow-lg relative overflow-hidden">
          <div className="flex items-center justify-between">
            <span className="text-xs uppercase tracking-wider font-semibold text-emerald-400">Amount Safe Today</span>
            <ShieldCheck className="w-5 h-5 text-emerald-400" />
          </div>
          <div className="text-3xl font-extrabold text-white font-mono mt-2">
            {detail.currency} {detail.amount_safe_to_pay.toLocaleString(undefined, { minimumFractionDigits: 2 })}
          </div>
          <div className="text-xs text-emerald-300/80 mt-2">
            {detail.amount_safe_to_pay >= detail.requested_amount
              ? "100% safe to commit immediately"
              : detail.amount_safe_to_pay > 0
              ? "Partial disbursement safe on request date"
              : "Unsafe today — reserve buffer required"}
          </div>
        </div>

        {/* Status & Method */}
        <div className="bg-slate-950/80 border border-slate-800 rounded-xl p-5 flex flex-col justify-between">
          <div>
            <div className="text-xs uppercase tracking-wider font-semibold text-slate-400">Affordability Status</div>
            <div className="text-lg font-bold text-indigo-300 capitalize mt-1">
              {detail.affordability_status.replace(/_/g, " ")}
            </div>
          </div>
          <div className="mt-3 pt-3 border-t border-slate-800/80">
            <div className="text-xs uppercase tracking-wider font-semibold text-slate-400">Recommended Method</div>
            <div className="text-base font-semibold text-emerald-300 capitalize mt-0.5">
              {detail.recommended_payment_method.replace(/_/g, " ")}
            </div>
          </div>
        </div>

        {/* User Balance & Reserve */}
        <div className="bg-slate-950/80 border border-slate-800 rounded-xl p-5 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs uppercase tracking-wider font-semibold text-slate-400">Current Balance</span>
            <Wallet className="w-4 h-4 text-slate-400" />
          </div>
          <div className="text-xl font-bold text-white font-mono mt-1">
            {detail.currency} {detail.current_balance.toLocaleString(undefined, { minimumFractionDigits: 2 })}
          </div>
          <div className="mt-2 pt-2 border-t border-slate-800 text-xs text-slate-400">
            Min Reserve Buffer:{" "}
            <span className="text-rose-400 font-semibold font-mono">
              {detail.currency} {detail.min_balance_to_keep.toLocaleString(undefined, { minimumFractionDigits: 2 })}
            </span>
          </div>
        </div>
      </div>

      {/* Decision Rationale */}
      <div className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-4">
        <div className="flex items-center gap-2 text-indigo-400 text-xs uppercase font-semibold tracking-wider">
          <AlertCircle className="w-4 h-4" /> AI Grounded Rationale
        </div>
        <p className="text-sm text-slate-200 mt-2 leading-relaxed">{detail.decision_explanation}</p>
        {detail.earliest_date_for_full_payment && (
          <div className="mt-3 text-xs text-amber-300 flex items-center gap-1.5">
            <Calendar className="w-4 h-4" /> Earliest Conservative Date for Full Payment:{" "}
            <span className="font-semibold font-mono">{detail.earliest_date_for_full_payment}</span>
          </div>
        )}
      </div>

      {/* Payment Plan & Spending Changes */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Payment Plan */}
        <div className="bg-slate-950/80 border border-slate-800 rounded-xl p-4">
          <div className="text-xs uppercase tracking-wider font-semibold text-slate-400 flex items-center gap-1.5">
            <CreditCard className="w-4 h-4 text-blue-400" /> Payment Schedule
          </div>
          {planItems.length > 0 ? (
            <div className="mt-3 space-y-2">
              {planItems.map((item, idx) => (
                <div
                  key={idx}
                  className="flex items-center justify-between text-xs bg-slate-900 px-3 py-2 rounded-lg border border-slate-800"
                >
                  <span className="text-slate-300 font-mono flex items-center gap-1">
                    <ArrowRight className="w-3 h-3 text-blue-400" /> Milestone {idx + 1} ({item.date})
                  </span>
                  <span className="font-semibold text-emerald-400 font-mono">
                    {detail.currency} {item.amount.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-slate-500 mt-3">No staged payment plan required (one-time settlement or wait).</p>
          )}
        </div>

        {/* Spending Changes */}
        <div className="bg-slate-950/80 border border-slate-800 rounded-xl p-4">
          <div className="text-xs uppercase tracking-wider font-semibold text-slate-400 flex items-center gap-1.5">
            <ShieldCheck className="w-4 h-4 text-amber-400" /> Budget Adjustments
          </div>
          {detail.spending_changes_needed && detail.spending_changes_needed.toLowerCase() !== "none" ? (
            <div className="mt-3 space-y-1.5">
              {detail.spending_changes_needed.split(";").map((action, idx) => (
                <div
                  key={idx}
                  className="text-xs bg-amber-950/30 text-amber-300 border border-amber-800/40 px-3 py-2 rounded-lg font-mono"
                >
                  {action.trim()}
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-slate-500 mt-3">No flexible spending reductions or cancellations required.</p>
          )}
        </div>
      </div>
    </div>
  );
};
