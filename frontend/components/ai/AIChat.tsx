"use client";

/**
 * AIChat — Premium enterprise AI document assistant component (Phase 12).
 *
 * Features (Phase 12 additions over Phase 3):
 *   - 10 granular states: idle | typing | retrieving | generating | success |
 *     no-docs | timeout | 503 | 401 | error
 *   - Sub-state progress text: "Searching your documents…" / "Generating answer…"
 *   - Expandable source cards with full chunk content preview
 *   - Copy-to-clipboard for AI answers (with visual confirmation)
 *   - Retry last message button on recoverable errors
 *   - Ctrl/Cmd+Enter shortcut (in addition to Enter)
 *   - match_type badge on source cards (hybrid / semantic / lexical)
 *   - RRF score alongside similarity in source cards
 *   - Score sourced from AISource.score (fused RRF/reranker score)
 *   - Conversation continuity via conversation_id threading
 *
 * Security:
 *   - No owner_id or chunk IDs are sent from the client.
 *   - Authorization is enforced entirely server-side.
 *   - Conversation_id is echoed back to the server for ownership verification.
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import { chat } from "@/services/ai.service";
import type { AIChatResponseData, AISource } from "@/types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type ChatPhase =
  | "idle"
  | "typing"
  | "retrieving"
  | "generating"
  | "success"
  | "no-docs"
  | "timeout"
  | "service-unavailable"
  | "unauthorized"
  | "error";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: AISource[];
  retrievedChunks?: number;
  isError?: boolean;
  phase?: Extract<ChatPhase, "success" | "no-docs" | "error" | "timeout" | "service-unavailable" | "unauthorized">;
  timestamp: Date;
}

interface AIChatProps {
  /** Initial suggested questions shown in the empty state. */
  suggestions?: string[];
  /** Default top_k for retrieval (1–10). */
  defaultTopK?: number;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const DEFAULT_SUGGESTIONS = [
  "What is our employee leave policy?",
  "Summarize the engineering architecture.",
  "What are the employee onboarding requirements?",
  "What deployment strategy does the handbook recommend?",
];

function formatSimilarity(similarity: number | null | undefined): string {
  if (similarity == null) return "—";
  return `${Math.round(similarity * 100)}%`;
}

function formatScore(score: number | null | undefined): string {
  if (score == null) return "—";
  return score.toFixed(4);
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function TypingIndicator({ phase }: { phase: ChatPhase }) {
  const label =
    phase === "retrieving"
      ? "Searching your documents…"
      : phase === "generating"
        ? "Generating answer…"
        : "Processing…";

  return (
    <div className="flex items-center gap-3 max-w-[85%]">
      <div className="w-8 h-8 rounded-full bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center shadow-md shrink-0">
        <span className="text-white text-xs font-bold">✦</span>
      </div>
      <div className="rounded-2xl rounded-tl-sm px-4 py-3 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 shadow-sm">
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5">
            {[0, 1, 2].map((i) => (
              <span
                key={i}
                className="w-2 h-2 rounded-full bg-indigo-400 dark:bg-indigo-500 animate-bounce"
                style={{ animationDelay: `${i * 150}ms` }}
              />
            ))}
          </div>
          <span className="text-xs text-gray-500 dark:text-gray-400 ml-1">{label}</span>
        </div>
      </div>
    </div>
  );
}

// Match type badge colours
const MATCH_TYPE_STYLES: Record<string, string> = {
  hybrid: "bg-violet-100 dark:bg-violet-900/40 text-violet-700 dark:text-violet-300",
  semantic: "bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300",
  lexical: "bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300",
};

function MatchTypeBadge({ matchType }: { matchType: string | null | undefined }) {
  if (!matchType) return null;
  const cls = MATCH_TYPE_STYLES[matchType] ?? "bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300";
  return (
    <span className={`text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded-full ${cls}`}>
      {matchType}
    </span>
  );
}

function SourceCard({ source }: { source: AISource }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="rounded-lg bg-gray-50 dark:bg-gray-800/60 border border-gray-200 dark:border-gray-700/60 px-3 py-2.5">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0 flex-1">
          <div className="w-5 h-5 rounded bg-indigo-100 dark:bg-indigo-900/50 flex items-center justify-center shrink-0">
            <svg className="w-3 h-3 text-indigo-600 dark:text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          </div>
          <span className="text-xs font-medium text-gray-800 dark:text-gray-200 truncate">
            {source.document_name}
          </span>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <MatchTypeBadge matchType={source.match_type} />
          <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-400">
            {formatSimilarity(source.similarity)}
          </span>
        </div>
      </div>

      {/* Metadata row */}
      <div className="flex items-center gap-3 mt-1 pl-7">
        <p className="text-[10px] text-gray-500 dark:text-gray-500">
          Chunk {source.chunk_number}
        </p>
        {source.score != null && (
          <p className="text-[10px] text-gray-400 dark:text-gray-600">
            RRF {formatScore(source.score)}
          </p>
        )}
        {source.distance != null && (
          <p className="text-[10px] text-gray-400 dark:text-gray-600">
            dist {source.distance.toFixed(3)}
          </p>
        )}
      </div>

      {/* Expandable content preview */}
      {source.content && (
        <>
          <button
            onClick={() => setExpanded((o) => !o)}
            className="mt-1.5 ml-7 flex items-center gap-1 text-[10px] text-indigo-500 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-200 transition-colors"
            id={`source-expand-${source.chunk_id}`}
          >
            <svg className={`w-3 h-3 transition-transform ${expanded ? "rotate-90" : ""}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
            {expanded ? "Hide" : "Preview"}
          </button>
          {expanded && (
            <div className="mt-1.5 ml-7 p-2 rounded bg-white dark:bg-gray-900/60 border border-gray-200 dark:border-gray-700/40 text-[10px] text-gray-600 dark:text-gray-400 leading-relaxed line-clamp-6 max-h-28 overflow-y-auto animate-in slide-in-from-top-1 duration-150">
              {source.content}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function SourcesAccordion({ sources }: { sources: AISource[] }) {
  const [open, setOpen] = useState(false);

  if (sources.length === 0) return null;

  return (
    <div className="mt-3">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 text-xs text-indigo-600 dark:text-indigo-400 hover:text-indigo-800 dark:hover:text-indigo-200 font-medium transition-colors"
        aria-expanded={open}
        id={`sources-toggle-${sources[0].chunk_id}`}
      >
        <svg
          className={`w-3.5 h-3.5 transition-transform ${open ? "rotate-90" : ""}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>
        {open ? "Hide" : "Show"} {sources.length} source{sources.length !== 1 ? "s" : ""}
      </button>

      {open && (
        <div className="mt-2 space-y-2 animate-in slide-in-from-top-1 duration-200">
          <div className="h-px bg-gray-200 dark:bg-gray-700" />
          <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500">
            Sources
          </p>
          {sources.map((source) => (
            <SourceCard key={source.chunk_id} source={source} />
          ))}
        </div>
      )}
    </div>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard API may not be available in all contexts */
    }
  };

  return (
    <button
      onClick={handleCopy}
      title={copied ? "Copied!" : "Copy answer"}
      className="p-1 rounded text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 transition-all"
      id="ai-chat-copy-btn"
    >
      {copied ? (
        <svg className="w-3.5 h-3.5 text-emerald-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
        </svg>
      ) : (
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
        </svg>
      )}
    </button>
  );
}

function UserMessage({ message }: { message: Message }) {
  return (
    <div className="flex justify-end gap-3 max-w-[85%] ml-auto">
      <div className="rounded-2xl rounded-tr-sm px-4 py-3 bg-gradient-to-br from-indigo-600 to-violet-600 text-white shadow-md">
        <p className="text-sm leading-relaxed whitespace-pre-wrap">{message.content}</p>
        <p className="text-[10px] text-indigo-200 mt-1.5 text-right">
          {message.timestamp.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
        </p>
      </div>
    </div>
  );
}

function AssistantMessage({
  message,
  onRetry,
}: {
  message: Message;
  onRetry?: () => void;
}) {
  const isNoContext = message.phase === "no-docs";
  const isError = message.isError;
  const isTimeout = message.phase === "timeout";
  const isServiceUnavailable = message.phase === "service-unavailable";

  const bgClass = isError || isTimeout || isServiceUnavailable
    ? "bg-rose-50 dark:bg-rose-950/30 border-rose-200 dark:border-rose-800"
    : isNoContext
      ? "bg-amber-50 dark:bg-amber-950/20 border-amber-200 dark:border-amber-800/50"
      : "bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700";

  const textClass = isError || isTimeout || isServiceUnavailable
    ? "text-rose-700 dark:text-rose-300"
    : isNoContext
      ? "text-amber-800 dark:text-amber-200"
      : "text-gray-800 dark:text-gray-100";

  return (
    <div className="flex items-start gap-3 max-w-[85%]">
      <div className="w-8 h-8 rounded-full bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center shadow-md shrink-0 mt-0.5">
        <span className="text-white text-xs font-bold">✦</span>
      </div>
      <div className={`rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm border ${bgClass} flex-1 min-w-0`}>
        <div className="flex items-start justify-between gap-2">
          <p className={`text-sm leading-relaxed whitespace-pre-wrap flex-1 ${textClass}`}>
            {message.content}
          </p>
          {!isError && !isTimeout && !isServiceUnavailable && message.content && (
            <CopyButton text={message.content} />
          )}
        </div>

        <div className="flex items-center gap-2 mt-1.5">
          <p className="text-[10px] text-gray-400 dark:text-gray-500">
            {message.timestamp.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
            {message.retrievedChunks !== undefined && message.retrievedChunks > 0 && (
              <span className="ml-2 text-indigo-500 dark:text-indigo-400">
                · {message.retrievedChunks} chunk{message.retrievedChunks !== 1 ? "s" : ""} retrieved
              </span>
            )}
          </p>
          {(isError || isTimeout || isServiceUnavailable) && onRetry && (
            <button
              onClick={onRetry}
              id="ai-chat-retry-btn"
              className="text-[10px] text-rose-600 dark:text-rose-400 hover:text-rose-800 dark:hover:text-rose-200 underline underline-offset-2 transition-colors"
            >
              Retry
            </button>
          )}
        </div>

        {message.sources && message.sources.length > 0 && (
          <SourcesAccordion sources={message.sources} />
        )}
      </div>
    </div>
  );
}

function EmptyState({
  suggestions,
  onSuggestion,
}: {
  suggestions: string[];
  onSuggestion: (q: string) => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-10 px-4 text-center">
      <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-violet-500/20 to-indigo-600/20 border border-indigo-200 dark:border-indigo-800/50 flex items-center justify-center mb-4">
        <span className="text-3xl">✦</span>
      </div>
      <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-1">
        Ask questions about your documents
      </h3>
      <p className="text-xs text-gray-500 dark:text-gray-400 mb-5 max-w-xs">
        I can only answer based on your authorized documents. I won&apos;t invent information.
      </p>

      <div className="flex flex-col gap-2 w-full max-w-sm">
        {suggestions.map((q) => (
          <button
            key={q}
            onClick={() => onSuggestion(q)}
            className="text-left text-xs px-3.5 py-2.5 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800/60 text-gray-700 dark:text-gray-300 hover:border-indigo-400 dark:hover:border-indigo-600 hover:bg-indigo-50 dark:hover:bg-indigo-950/30 hover:text-indigo-700 dark:hover:text-indigo-300 transition-all"
          >
            <span className="text-gray-400 dark:text-gray-500 mr-1.5">✦</span>
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function AIChat({ suggestions = DEFAULT_SUGGESTIONS, defaultTopK = 5 }: AIChatProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [chatPhase, setChatPhase] = useState<ChatPhase>("idle");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [lastUserMessage, setLastUserMessage] = useState<string>("");

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const isLoading = chatPhase === "retrieving" || chatPhase === "generating" || chatPhase === "typing";

  // Auto-scroll to latest message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, chatPhase]);

  // Auto-resize textarea
  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, 160)}px`;
  }, [input]);

  const appendMessage = useCallback((msg: Message) => {
    setMessages((prev) => [...prev, msg]);
  }, []);

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || isLoading) return;

      const userMessage: Message = {
        id: `user-${Date.now()}`,
        role: "user",
        content: trimmed,
        timestamp: new Date(),
      };
      appendMessage(userMessage);
      setInput("");
      setLastUserMessage(trimmed);

      // Phase: typing → retrieving → generating → done
      setChatPhase("typing");
      await new Promise((r) => setTimeout(r, 120)); // brief pause for animation
      setChatPhase("retrieving");

      try {
        // Simulate retrieving → generating transition after a short delay
        const generatingTimer = setTimeout(() => setChatPhase("generating"), 1500);

        const result = await chat({
          message: trimmed,
          top_k: defaultTopK,
          conversation_id: conversationId,
        });

        clearTimeout(generatingTimer);

        if (result.success && result.data) {
          const data: AIChatResponseData = result.data;
          setConversationId(data.conversation_id);

          const noContext =
            data.retrieved_chunks === 0 ||
            data.answer.toLowerCase().includes("couldn't find enough information");

          const assistantMessage: Message = {
            id: `asst-${Date.now()}`,
            role: "assistant",
            content: data.answer,
            sources: data.sources,
            retrievedChunks: data.retrieved_chunks,
            phase: noContext ? "no-docs" : "success",
            timestamp: new Date(),
          };
          appendMessage(assistantMessage);
          setChatPhase(noContext ? "no-docs" : "success");
        }
      } catch (err: unknown) {
        const axiosError = err as {
          response?: { status?: number; data?: { detail?: string; message?: string } };
          code?: string;
          message?: string;
        };
        const status = axiosError.response?.status;
        let errorText = "An unexpected error occurred. Please try again.";
        let errorPhase: Message["phase"] = "error";

        if (status === 503) {
          errorText = "The AI service is temporarily unavailable. Please try again in a moment.";
          errorPhase = "service-unavailable";
        } else if (status === 403) {
          errorText = "You do not have permission to access this conversation.";
          errorPhase = "unauthorized";
        } else if (status === 401) {
          errorText = "Your session has expired. Please sign in again.";
          errorPhase = "unauthorized";
        } else if (status === 422) {
          errorText = "Your message could not be processed. Please check and try again.";
        } else if (
          axiosError.code === "ECONNABORTED" ||
          axiosError.message?.toLowerCase().includes("timeout")
        ) {
          errorText = "AI generation timed out. Please try asking again.";
          errorPhase = "timeout";
        } else if (axiosError.response?.data?.detail) {
          errorText = axiosError.response.data.detail;
        }

        const errorMsg: Message = {
          id: `err-${Date.now()}`,
          role: "assistant",
          content: errorText,
          isError: true,
          phase: errorPhase,
          timestamp: new Date(),
        };
        appendMessage(errorMsg);
        setChatPhase(errorPhase ?? "error");
      } finally {
        if (chatPhase !== "no-docs") setChatPhase("idle");
        setTimeout(() => textareaRef.current?.focus(), 100);
      }
    },
    [isLoading, conversationId, defaultTopK, appendMessage, chatPhase],
  );

  const handleRetry = useCallback(() => {
    if (lastUserMessage) {
      void sendMessage(lastUserMessage);
    }
  }, [lastUserMessage, sendMessage]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    const isEnterShortcut =
      (e.key === "Enter" && !e.shiftKey) ||
      (e.key === "Enter" && (e.ctrlKey || e.metaKey));
    if (isEnterShortcut) {
      e.preventDefault();
      void sendMessage(input);
    }
  };

  const handleClear = () => {
    setMessages([]);
    setConversationId(null);
    setInput("");
    setChatPhase("idle");
    setLastUserMessage("");
  };

  const canSend = input.trim().length >= 2 && !isLoading;

  // Phase indicator label for the header
  const phaseLabel = isLoading
    ? chatPhase === "retrieving"
      ? "Retrieving…"
      : chatPhase === "generating"
        ? "Generating…"
        : "Processing…"
    : "RAG";

  return (
    <div className="flex flex-col h-full min-h-[480px] max-h-[720px] rounded-2xl overflow-hidden border border-indigo-200 dark:border-indigo-900/50 bg-gradient-to-b from-white via-white to-indigo-50/30 dark:from-gray-900 dark:via-gray-900 dark:to-indigo-950/10 shadow-sm">
      {/* Header */}
      <div className="flex items-center gap-3 px-5 py-3.5 border-b border-indigo-100 dark:border-indigo-900/40 bg-gradient-to-r from-indigo-50/80 via-white to-violet-50/60 dark:from-indigo-950/30 dark:via-gray-900 dark:to-violet-950/20 shrink-0">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center shadow-sm shrink-0">
          <span className="text-white text-sm font-bold">✦</span>
        </div>
        <div className="min-w-0">
          <h2 className="text-sm font-bold text-gray-900 dark:text-white leading-tight">
            IntelliFlow AI
          </h2>
          <p className="text-[10px] text-gray-500 dark:text-gray-400">
            Document Intelligence Assistant
          </p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <span
            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wider transition-colors ${
              isLoading
                ? "bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-400"
                : "bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-400"
            }`}
          >
            <span className={`w-1.5 h-1.5 rounded-full ${isLoading ? "bg-amber-500 animate-pulse" : "bg-emerald-500 animate-pulse"}`} />
            {phaseLabel}
          </span>
          {messages.length > 0 && (
            <button
              onClick={handleClear}
              title="Start new conversation"
              id="ai-chat-clear-btn"
              className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors p-1 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            </button>
          )}
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-5 space-y-4 scroll-smooth">
        {messages.length === 0 && !isLoading ? (
          <EmptyState
            suggestions={suggestions}
            onSuggestion={(q) => {
              setInput(q);
              void sendMessage(q);
            }}
          />
        ) : (
          <>
            {messages.map((msg) =>
              msg.role === "user" ? (
                <UserMessage key={msg.id} message={msg} />
              ) : (
                <AssistantMessage
                  key={msg.id}
                  message={msg}
                  onRetry={
                    (msg.isError || msg.phase === "timeout" || msg.phase === "service-unavailable")
                      ? handleRetry
                      : undefined
                  }
                />
              ),
            )}
            {isLoading && <TypingIndicator phase={chatPhase} />}
          </>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="shrink-0 border-t border-indigo-100 dark:border-indigo-900/40 px-4 py-3 bg-white/80 dark:bg-gray-900/80 backdrop-blur-sm">
        <div
          className={`flex items-end gap-2 rounded-xl border transition-all ${
            isLoading
              ? "border-gray-200 dark:border-gray-700"
              : "border-indigo-200 dark:border-indigo-800 focus-within:border-indigo-400 dark:focus-within:border-indigo-600 focus-within:shadow-[0_0_0_3px_rgba(99,102,241,0.1)]"
          } bg-white dark:bg-gray-800 px-3 py-2`}
        >
          <textarea
            ref={textareaRef}
            id="ai-chat-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a question about your documents…"
            rows={1}
            disabled={isLoading}
            className="flex-1 resize-none bg-transparent text-sm text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 outline-none min-h-[36px] max-h-[160px] py-1.5 disabled:opacity-50"
            style={{ lineHeight: "1.5" }}
          />
          <button
            id="ai-chat-send-btn"
            onClick={() => void sendMessage(input)}
            disabled={!canSend}
            className={`w-8 h-8 rounded-lg flex items-center justify-center transition-all shrink-0 ${
              canSend
                ? "bg-indigo-600 hover:bg-indigo-700 text-white shadow-sm hover:shadow-md active:scale-95"
                : "bg-gray-100 dark:bg-gray-700 text-gray-400 dark:text-gray-500 cursor-not-allowed"
            }`}
            aria-label="Send message"
          >
            {isLoading ? (
              <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
              </svg>
            ) : (
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
              </svg>
            )}
          </button>
        </div>
        <p className="text-[10px] text-gray-400 dark:text-gray-500 mt-1.5 text-center">
          Answers are grounded in your documents only. Press{" "}
          <kbd className="px-1 py-0.5 rounded border border-gray-200 dark:border-gray-700 text-[9px] font-mono">Enter</kbd>{" "}
          or{" "}
          <kbd className="px-1 py-0.5 rounded border border-gray-200 dark:border-gray-700 text-[9px] font-mono">⌘↵</kbd>{" "}
          to send,{" "}
          <kbd className="px-1 py-0.5 rounded border border-gray-200 dark:border-gray-700 text-[9px] font-mono">Shift+Enter</kbd>{" "}
          for new line.
        </p>
      </div>
    </div>
  );
}

export default AIChat;
