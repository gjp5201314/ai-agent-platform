import { useMemo } from "react";
import { Menu, Cpu } from "lucide-react";
import { MessageList } from "./MessageList";
import { MessageInput } from "./MessageInput";
import type { Message, AgentConfig } from "../types";

interface Props {
  messages: Message[];
  isStreaming: boolean;
  activeAgent: AgentConfig | null;
  onSend: (message: string) => void;
  onStop: () => void;
  useRag: boolean;
  onToggleRag: () => void;
  onOpenSidebar: () => void;
  modelProvider: string | null;
  onModelProviderChange: (provider: string | null) => void;
  onOpenAdmin: () => void;
}

/** Estimate token count from messages (rough: 2 chars ≈ 1 token for mixed CN/EN) */
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
    <div className="flex flex-col h-full bg-[#0b0b16] relative">
      {/* Animated grid background */}
      <div className="absolute inset-0 bg-cyber-grid-animated pointer-events-none" />

      {/* Ambient glow orbs */}
      <div className="absolute top-0 left-1/4 w-96 h-96 bg-cyber-400/8 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-neon-500/8 rounded-full blur-3xl pointer-events-none" />

      {/* Context window indicator bar */}
      {messages.length > 0 && (
        <div className="relative z-10 flex-shrink-0 px-4 pt-3 pb-0">
          <div className="max-w-4xl mx-auto flex items-center gap-2">
            <div className="flex-1 h-1 rounded-full bg-white/[0.06] overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-500 ${
                  isFull ? "bg-destructive" : isWarning ? "bg-amber-500" : "bg-primary/60"
                }`}
                style={{ width: `${pct}%` }}
              />
            </div>
            <span
              className={`text-[10px] font-mono tabular-nums whitespace-nowrap transition-colors ${
                isFull ? "text-destructive" : isWarning ? "text-amber-500" : "text-primary/60"
              }`}
            >
              {estimated.toLocaleString()} / {maxTokens.toLocaleString()}
              {pct > 10 && <span className="ml-0.5 opacity-70">{pct}%</span>}
            </span>
          </div>
        </div>
      )}

      {/* Mobile header */}
      <div className="lg:hidden flex items-center gap-3 p-3 glass-panel-strong border-b border-white/[0.06] relative z-10">
        <button
          onClick={onOpenSidebar}
          className="text-white/50 hover:text-white transition-colors"
        >
          <Menu size={20} />
        </button>
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <Cpu size={14} className="text-cyber-400 flex-shrink-0" />
          <span className="font-medium text-xs text-white/70 truncate">
            {activeAgent?.name || "AI Agent"}
          </span>
        </div>
      </div>

      {/* Messages */}
      <div className="relative z-10 flex-1 min-h-0">
        <MessageList messages={messages} isStreaming={isStreaming} />
      </div>

      {/* Input */}
      <div className="relative z-10">
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
