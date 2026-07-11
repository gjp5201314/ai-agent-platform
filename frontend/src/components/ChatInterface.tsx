import { Menu, Cpu } from "lucide-react";
import { MessageList } from "./MessageList";
import { MessageInput } from "./MessageInput";
import type { Message } from "../types";

interface Props {
  messages: Message[];
  isStreaming: boolean;
  onSend: (message: string) => void;
  onStop: () => void;
  useRag: boolean;
  onToggleRag: () => void;
  onOpenSidebar: () => void;
}

export function ChatInterface({
  messages,
  isStreaming,
  onSend,
  onStop,
  useRag,
  onToggleRag,
  onOpenSidebar,
}: Props) {
  return (
    <div className="flex flex-col h-full bg-cyber-gradient relative">
      {/* Animated grid background */}
      <div className="absolute inset-0 bg-cyber-grid-animated pointer-events-none" />

      {/* Ambient glow orbs */}
      <div className="absolute top-0 left-1/4 w-96 h-96 bg-cyber-400/5 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-neon-500/5 rounded-full blur-3xl pointer-events-none" />

      {/* Mobile header */}
      <div className="lg:hidden flex items-center gap-3 p-3 glass-panel-strong border-b border-white/[0.06] relative z-10">
        <button
          onClick={onOpenSidebar}
          className="text-white/50 hover:text-white transition-colors"
        >
          <Menu size={20} />
        </button>
        <div className="flex items-center gap-2">
          <Cpu size={16} className="text-cyber-400" />
          <span className="font-medium text-sm text-white/80">AI Agent</span>
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
        />
      </div>
    </div>
  );
}
