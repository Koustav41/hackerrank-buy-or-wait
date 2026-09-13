"use client";

import React, { useState, useRef, useEffect } from "react";
import { Send, Bot, User, Sparkles, HelpCircle } from "@/components/Icons";
import { safeFetch } from "@/lib/api";

interface Message {
  id: string;
  sender: "user" | "agent";
  text: string;
}

interface AskAgentProps {
  requestId: string | null;
}

export const AskAgent: React.FC<AskAgentProps> = ({ requestId }) => {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "1",
      sender: "agent",
      text: "Hello! I am your Buy or Wait AI Financial Advisor. Ask me anything about this request, why a decision was reached, or how safe amounts were calculated.",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async (textToSend?: string) => {
    const q = textToSend || input;
    if (!q.trim() || loading) return;

    const userMsg: Message = { id: Date.now().toString(), sender: "user", text: q };
    setMessages((prev) => [...prev, userMsg]);
    if (!textToSend) setInput("");
    setLoading(true);

    try {
      const data = await safeFetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          request_id: requestId,
          question: q,
        }),
      });

      if (data && data.answer) {
        const agentMsg: Message = {
          id: (Date.now() + 1).toString(),
          sender: "agent",
          text: data.answer,
        };
        setMessages((prev) => [...prev, agentMsg]);
      } else {
        throw new Error("Chat request failed");
      }
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        {
          id: (Date.now() + 1).toString(),
          sender: "agent",
          text: "I encountered an error connecting to the financial engine. Please ensure the backend is running.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const sampleQuestions = [
    "Why was this decision made?",
    "Can I afford this today?",
    "What is the recommended payment schedule?",
    "What spending changes are required?",
  ];

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-6 shadow-2xl flex flex-col h-[480px]">
      <div className="flex items-center justify-between pb-3 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <Bot className="w-5 h-5 text-indigo-400" />
          <h3 className="text-base font-bold text-white">Ask Financial Advisor</h3>
        </div>
        <span className="text-xs bg-indigo-950 text-indigo-400 border border-indigo-800/40 px-2 py-0.5 rounded-full flex items-center gap-1">
          <Sparkles className="w-3 h-3" /> Grounded Agent
        </span>
      </div>

      {/* Messages Scroll Area */}
      <div className="flex-1 overflow-y-auto py-4 space-y-3 pr-1 text-sm">
        {messages.map((m) => (
          <div
            key={m.id}
            className={`flex items-start gap-2.5 ${m.sender === "user" ? "flex-row-reverse" : "flex-row"}`}
          >
            <div
              className={`w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 text-xs ${
                m.sender === "user" ? "bg-indigo-600 text-white" : "bg-slate-800 text-indigo-400 border border-slate-700"
              }`}
            >
              {m.sender === "user" ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
            </div>
            <div
              className={`p-3 rounded-2xl max-w-[80%] whitespace-pre-wrap leading-relaxed ${
                m.sender === "user"
                  ? "bg-indigo-600 text-white rounded-br-none"
                  : "bg-slate-950 text-slate-200 border border-slate-800 rounded-bl-none shadow-sm"
              }`}
            >
              {m.text}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex items-center gap-2 text-xs text-slate-500 italic">
            <Bot className="w-4 h-4 animate-pulse text-indigo-400" /> Advisor is evaluating balance trajectory...
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Suggested chips */}
      <div className="flex gap-1.5 overflow-x-auto py-2 text-xs">
        {sampleQuestions.map((q, idx) => (
          <button
            key={idx}
            onClick={() => handleSend(q)}
            className="whitespace-nowrap px-2.5 py-1 rounded-full bg-slate-950 text-slate-300 border border-slate-800 hover:border-indigo-500/50 hover:text-indigo-300 transition-colors"
          >
            {q}
          </button>
        ))}
      </div>

      {/* Input bar */}
      <div className="pt-2 border-t border-slate-800 flex gap-2">
        <input
          type="text"
          placeholder="Ask a question about this financial decision..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSend()}
          className="flex-1 bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
        />
        <button
          onClick={() => handleSend()}
          disabled={loading || !input.trim()}
          className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white px-4 py-2 rounded-lg font-medium transition-all shadow-md shadow-indigo-600/20 flex items-center gap-1.5 text-sm"
        >
          <Send className="w-4 h-4" /> Send
        </button>
      </div>
    </div>
  );
};
