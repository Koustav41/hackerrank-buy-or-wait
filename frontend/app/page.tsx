"use client";

import React, { useState } from "react";
import { Dashboard } from "@/components/Dashboard";
import { DecisionCard } from "@/components/DecisionCard";
import { FinancialTimeline } from "@/components/FinancialTimeline";
import { AskAgent } from "@/components/AskAgent";
import { Sparkles } from "@/components/Icons";

export default function Home() {
  const [selectedRequestId, setSelectedRequestId] = useState<string | null>("request_01");

  return (
    <main className="min-h-screen bg-slate-950 text-slate-100 p-4 md:p-8 space-y-8 font-sans">
      {/* Top Navigation Bar */}
      <header className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 pb-6 border-b border-slate-800">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-indigo-600 flex items-center justify-center shadow-lg shadow-indigo-600/30">
            <Sparkles className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="text-xl md:text-2xl font-black tracking-tight text-white flex items-center gap-2">
              Buy or Wait? <span className="text-xs px-2 py-0.5 rounded bg-indigo-900/60 text-indigo-300 border border-indigo-700/40">AI Decision Engine</span>
            </h1>
            <p className="text-xs text-slate-400 font-medium">Autonomous 90-Day Cash Flow Simulation & Solvency Advisory Engine</p>
          </div>
        </div>

        <div className="flex items-center gap-2.5 text-xs text-emerald-400 bg-emerald-950/60 border border-emerald-800/40 px-3.5 py-1.5 rounded-lg shadow-sm">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
          <span className="font-medium tracking-wide">System Online • 250 Requests Analyzed</span>
        </div>
      </header>

      {/* Main Dashboard: Metrics & Requests List */}
      <section>
        <Dashboard onSelectRequest={(id) => setSelectedRequestId(id)} selectedRequestId={selectedRequestId} />
      </section>

      {/* Lower Section: Decision Details & Timeline + Ask Agent */}
      <section className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <DecisionCard requestId={selectedRequestId} />
          <FinancialTimeline requestId={selectedRequestId} />
        </div>
        <div className="lg:col-span-1">
          <div className="sticky top-6">
            <AskAgent requestId={selectedRequestId} />
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="pt-8 border-t border-slate-900 text-center text-xs text-slate-600 space-y-1">
        <p>Built with FastAPI, Next.js 15, and SQLite.</p>
        <p>Deterministic cash flow bounds, reserve safety checks, and multi-tier payment optimization.</p>
      </footer>
    </main>
  );
}
