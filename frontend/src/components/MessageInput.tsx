import { useState, useRef, useEffect } from "react";
import { Send, Square } from "lucide-react";

interface Props {
  onSend: (message: string) => void;
  onStop: () => void;
  isStreaming: boolean;
  useRag: boolean;
  onToggleRag: () => void;
}

export function MessageInput({ onSend, onStop, isStreaming, useRag, onToggleRag }: Props) {
  const [input, setInput] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 200) + "px";
    }
  }, [input]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isStreaming) return;
    onSend(input.trim());
    setInput("");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  return (
    <div className="border-t border-slate-200 bg-white px-4 py-4">
      <form onSubmit={handleSubmit} className="max-w-4xl mx-auto">
        <div className="relative flex items-end gap-2">
          <div className="flex-1 relative">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="输入消息... (Enter 发送, Shift+Enter 换行)"
              rows={1}
              className="w-full resize-none rounded-2xl border border-slate-300 px-4 py-3 pr-12 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400 focus:border-transparent transition-all"
              disabled={isStreaming}
            />
          </div>

          {/* RAG toggle */}
          <button
            type="button"
            onClick={onToggleRag}
            title={useRag ? "知识库检索已开启" : "知识库检索已关闭"}
            className={`flex-shrink-0 rounded-xl px-3 py-3 text-sm font-medium transition-colors ${
              useRag
                ? "bg-green-100 text-green-700 hover:bg-green-200"
                : "bg-slate-100 text-slate-400 hover:bg-slate-200"
            }`}
          >
            📚 RAG
          </button>

          {/* Send / Stop button */}
          {isStreaming ? (
            <button
              type="button"
              onClick={onStop}
              className="flex-shrink-0 rounded-xl bg-red-500 hover:bg-red-600 text-white p-3 transition-colors"
              title="停止生成"
            >
              <Square size={20} />
            </button>
          ) : (
            <button
              type="submit"
              disabled={!input.trim()}
              className="flex-shrink-0 rounded-xl bg-brand-600 hover:bg-brand-700 disabled:bg-slate-300 text-white p-3 transition-colors"
              title="发送"
            >
              <Send size={20} />
            </button>
          )}
        </div>
      </form>
    </div>
  );
}
