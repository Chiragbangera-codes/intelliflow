"use client";

import React, { useRef, useState, useEffect } from "react";
import { Modal } from "@/components/ui/Modal";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { askDocumentAIChat } from "@/services/document.service";
import type { DocumentChunkSource, EnterpriseDocument } from "@/types";

interface Message {
  role: "user" | "assistant";
  content: string;
  sources?: DocumentChunkSource[];
  timestamp: Date;
}

interface DocumentAIChatModalProps {
  isOpen: boolean;
  onClose: () => void;
  document: EnterpriseDocument | null;
}

export function DocumentAIChatModal({
  isOpen,
  onClose,
  document: doc,
}: DocumentAIChatModalProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [conversationId, setConversationId] = useState<string | undefined>(undefined);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (isOpen && doc) {
      setMessages([
        {
          role: "assistant",
          content: `Hello! I'm ready to answer any questions about "${doc.title || doc.file_name}". All my answers are grounded strictly within this document.`,
          timestamp: new Date(),
        },
      ]);
    }
  }, [isOpen, doc]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!doc || !input.trim() || loading) return;

    const userQuery = input.trim();
    setInput("");

    setMessages((prev) => [
      ...prev,
      { role: "user", content: userQuery, timestamp: new Date() },
    ]);

    try {
      setLoading(true);
      const res = await askDocumentAIChat(doc.id, {
        message: userQuery,
        conversation_id: conversationId,
      });

      setConversationId(res.data.conversation_id);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: res.data.answer,
          sources: res.data.sources,
          timestamp: new Date(),
        },
      ]);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "AI chat request failed.";
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `Error: ${msg}`,
          timestamp: new Date(),
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  if (!doc) return null;

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={`AI Q&A — ${doc.title || doc.file_name}`}
    >
      <div className="flex flex-col h-[520px]">
        {/* Messages */}
        <div className="flex-1 overflow-y-auto space-y-4 p-2 pr-3">
          {messages.map((m, idx) => (
            <div
              key={idx}
              className={`flex flex-col ${
                m.role === "user" ? "items-end" : "items-start"
              }`}
            >
              <div
                className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                  m.role === "user"
                    ? "bg-blue-600 text-white rounded-br-none"
                    : "bg-slate-800 text-slate-100 border border-slate-700 rounded-bl-none"
                }`}
              >
                <div className="whitespace-pre-wrap">{m.content}</div>

                {/* Cited Sources */}
                {m.sources && m.sources.length > 0 && (
                  <div className="mt-3 pt-2 border-t border-slate-700/60 text-xs space-y-1.5">
                    <span className="font-semibold text-slate-400">Sources:</span>
                    <div className="space-y-1">
                      {m.sources.slice(0, 3).map((src) => (
                        <div
                          key={src.chunk_id}
                          className="bg-slate-900/60 p-2 rounded border border-slate-800 text-slate-300 italic text-[11px]"
                        >
                          <span className="text-blue-400 font-medium">Chunk #{src.chunk_number}:</span>{" "}
                          &ldquo;{src.content.slice(0, 140)}...&rdquo;
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
              <span className="text-[10px] text-slate-500 mt-1 px-1">
                {m.timestamp.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
              </span>
            </div>
          ))}

          {loading && (
            <div className="flex items-center gap-2 text-slate-400 text-xs p-2">
              <LoadingSpinner size="sm" />
              <span>Synthesizing answer from document chunks...</span>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <form onSubmit={handleSend} className="pt-3 border-t border-slate-800 flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask a question about this document..."
            disabled={loading}
            className="flex-1 bg-slate-800 border border-slate-700 rounded-xl px-4 py-2.5 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium transition"
          >
            Send
          </button>
        </form>
      </div>
    </Modal>
  );
}
