import { useState, useRef, useEffect } from "react";
import { Send, Square, Database, Sparkles } from "lucide-react";

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
    <div className="px-4 pb-4 pt-2">
      <form onSubmit={handleSubmit} className="max-w-4xl mx-auto">
        <div className="relative">
          {/* Input container - terminal style */}
          <div className="relative rounded-2xl bg-surface-700/50 backdrop-blur-xl
                          border border-white/[0.06] focus-within:border-cyber-400/30
                          focus-within:shadow-glow-cyan transition-all duration-300
                          overflow-hidden">
            {/* Top glow line */}
            <div className="absolute top-0 left-4 right-4 h-px bg-gradient-to-r from-transparent via-cyber-400/20 to-transparent" />

            <div className="flex items-end gap-2 p-2">
              <div className="flex-1 relative">
                <textarea
                  ref={textareaRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="输入消息... (Enter 发送, Shift+Enter 换行)"
                  rows={1}
                  className="w-full resize-none bg-transparent px-3 py-2 text-sm text-white/80
                             placeholder-white/20 focus:outline-none"
                  disabled={isStreaming}
                />
              </div>

              <div className="flex items-center gap-1.5 pr-1">
                {/* RAG toggle */}
                <button
                  type="button"
                  onClick={onToggleRag}
                  title={useRag ? "知识库检索已开启" : "知识库检索已关闭"}
                  className={`flex items-center gap-1.5 rounded-lg px-2.5 py-2 text-xs
                             transition-all duration-300 ${
                    useRag
                      ? "bg-accent-green/10 border border-accent-green/30 text-accent-green shadow-[0_0_10px_rgba(0,230,118,0.15)]"
                      : "bg-transparent border border-white/[0.06] text-white/20 hover:text-white/40"
                  }`}
                >
                  <Database size={14} />
                  <span className="hidden sm:inline">RAG</span>
                </button>

                {/* Send / Stop button */}
                {isStreaming ? (
                  <button
                    type="button"
                    onClick={onStop}
                    className="rounded-lg bg-accent-pink/20 border border-accent-pink/30
                               text-accent-pink hover:bg-accent-pink/30
                               p-2.5 transition-all duration-300
                               hover:shadow-[0_0_12px_rgba(255,64,129,0.25)]"
                    title="停止生成"
                  >
                    <Square size={16} />
                  </button>
                ) : (
                  <button
                    type="submit"
                    disabled={!input.trim()}
                    className={`rounded-lg p-2.5 transition-all duration-300 ${
                      input.trim()
                        ? "bg-gradient-to-r from-cyber-500 to-cyber-600 text-white shadow-glow-cyan hover:shadow-glow-strong"
                        : "bg-white/[0.04] text-white/15 cursor-not-allowed"
                    }`}
                    title="发送"
                  >
                    <Send size={16} />
                  </button>
                )}
              </div>
            </div>
          </div>

          {/* Hint text */}
          <div className="flex items-center justify-center gap-2 mt-2">
            <Sparkles size={10} className="text-white/10" />
            <span className="text-[10px] text-white/15 tracking-wider">
              Enter 发送 · Shift+Enter 换行
            </span>
          </div>
        </div>
      </form>
    </div>
  );
}
