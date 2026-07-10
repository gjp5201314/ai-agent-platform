import { Menu } from "lucide-react";
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
    <div className="flex flex-col h-full bg-slate-50">
      {/* Mobile header */}
      <div className="lg:hidden flex items-center gap-3 p-3 bg-white border-b border-slate-200">
        <button onClick={onOpenSidebar} className="text-slate-500 hover:text-slate-700">
          <Menu size={22} />
        </button>
        <span className="font-medium text-slate-700">AI Agent</span>
      </div>

      <MessageList messages={messages} isStreaming={isStreaming} />

      <MessageInput
        onSend={onSend}
        onStop={onStop}
        isStreaming={isStreaming}
        useRag={useRag}
        onToggleRag={onToggleRag}
      />
    </div>
  );
}
