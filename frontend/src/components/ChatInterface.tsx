import { useMemo } from "react";
import { Menu, Bot } from "lucide-react";
import { MessageList } from "./MessageList";
import { MessageInput } from "./MessageInput";
import type { Message, AgentConfig } from "../types";

interface Props {
  messages: Message[];
  isStreaming: boolean;
  activeAgent: AgentConfig | null;
  activeAgentId?: string | null;
  agents?: { id: string; name: string }[];
  onSend: (message: string) => void;
  onStop: () => void;
  useRag: boolean;
  onToggleRag: () => void;
  onOpenSidebar: () => void;
  modelProvider: string | null;
  onModelProviderChange: (provider: string | null) => void;
  onOpenAdmin: () => void;
}

function estimateTokens(msgs: Message[]): number {
  let total = 0;
  for (const msg of msgs) {
    total += (msg.content || "").length;
  }
  return Math.max(1, Math.round(total / 2));
}

export function ChatInterface({
  messages,
  isStreaming,
  activeAgent,
  activeAgentId,
  agents,
  onSend,
  onStop,
  useRag,
  onToggleRag,
  onOpenSidebar,
  modelProvider,
  onModelProviderChange,
  onOpenAdmin,
}: Props) {
  const maxTokens = activeAgent?.max_tokens || 4096;
  const estimated = useMemo(() => estimateTokens(messages), [messages]);
  const pct = Math.min(100, Math.round((estimated / maxTokens) * 100));
  const isFull = pct >= 85;
  const isWarning = pct >= 65 && pct < 85;

  return (
    <div className="flex flex-col h-full bg-white">
      {/* Context window indicator bar */}
      {messages.length > 0 && (
        <div className="relative z-10 flex-shrink-0 px-4 pt-3 pb-0">
          <div className="max-w-4xl mx-auto flex items-center gap-2">
            <div className="flex-1 h-1 rounded-full bg-gray-100 overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-500 ${
                  isFull ? "bg-red-500" : isWarning ? "bg-amber-500" : "bg-ds-400/60"
                }`}
                style={{ width: `${pct}%` }}
              />
            </div>
            <span
              className={`text-[10px] font-mono tabular-nums whitespace-nowrap transition-colors ${
                isFull ? "text-red-500" : isWarning ? "text-amber-600" : "text-gray-400"
              }`}
            >
              {estimated.toLocaleString()} / {maxTokens.toLocaleString()}
              {pct > 10 && <span className="ml-0.5 opacity-70">{pct}%</span>}
            </span>
          </div>
        </div>
      )}

      {/* Mobile header */}
      <div className="lg:hidden flex items-center gap-3 p-3 bg-white border-b border-gray-200 relative z-10">
        <button
          onClick={onOpenSidebar}
          className="text-gray-500 hover:text-gray-800 transition-colors"
        >
          <Menu size={20} />
        </button>
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <Bot size={14} className="text-ds-500 flex-shrink-0" />
          <span className="font-medium text-sm text-gray-700 truncate">
            {activeAgent?.name || "AI Agent"}
          </span>
        </div>
      </div>

      {/* Messages */}
      <div className="relative z-10 flex-1 min-h-0">
        <MessageList messages={messages} isStreaming={isStreaming} activeAgentId={activeAgentId} agents={agents} />
      </div>

      {/* Input */}
      <div className="relative z-10 bg-gradient-to-t from-white via-white to-transparent pt-4">
        <MessageInput
          onSend={onSend}
          onStop={onStop}
          isStreaming={isStreaming}
          useRag={useRag}
          onToggleRag={onToggleRag}
          modelProvider={modelProvider}
          onModelProviderChange={onModelProviderChange}
          onOpenAdmin={onOpenAdmin}
        />
      </div>
    </div>
  );
}
