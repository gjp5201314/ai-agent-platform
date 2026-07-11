import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Cpu, User, Wrench } from "lucide-react";
import type { Message } from "../types";

interface Props {
  messages: Message[];
  isStreaming: boolean;
}

export function MessageList({ messages, isStreaming }: Props) {
  if (messages.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center relative z-10">
        <div className="text-center max-w-lg px-6">
          {/* Central orb */}
          <div className="relative mx-auto mb-8 w-24 h-24">
            <div className="absolute inset-0 bg-cyber-400/10 rounded-full blur-2xl animate-glow-pulse" />
            <div className="absolute inset-2 bg-gradient-to-br from-cyber-400/20 to-neon-500/20 rounded-full blur-xl" />
            <div className="relative w-full h-full rounded-full glass-panel flex items-center justify-center">
              <Cpu size={36} className="text-cyber-400 animate-float" />
            </div>
          </div>

          <h2 className="text-3xl font-bold mb-3 tracking-tight">
            <span className="bg-gradient-to-r from-cyber-300 via-cyber-400 to-neon-400 bg-clip-text text-transparent">
              AI Agent Platform
            </span>
          </h2>

          <p className="text-white/30 text-sm leading-relaxed mb-6 max-w-sm mx-auto">
            支持知识库问答 (RAG)、工具调用和多轮对话
          </p>

          {/* Feature pills */}
          <div className="flex flex-wrap gap-2 justify-center">
            {["知识库 RAG", "多轮对话", "工具调用", "流式响应"].map((f) => (
              <span
                key={f}
                className="px-3 py-1.5 rounded-full text-xs
                           bg-surface-600/60 border border-white/[0.06]
                           text-white/40 backdrop-blur-sm"
              >
                {f}
              </span>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto px-4 py-6 space-y-5">
      {messages.map((msg, idx) => (
        <MessageItem
          key={idx}
          message={msg}
          isStreaming={isStreaming && idx === messages.length - 1 && msg.role === "assistant"}
        />
      ))}
    </div>
  );
}

function MessageItem({ message, isStreaming }: { message: Message; isStreaming: boolean }) {
  const isUser = message.role === "user";

  return (
    <div className={`flex gap-3 ${isUser ? "flex-row-reverse" : ""} animate-slide-up`}>
      {/* Avatar */}
      <div className="flex-shrink-0 mt-0.5">
        <div
          className={`w-9 h-9 rounded-lg flex items-center justify-center ${
            isUser
              ? "bg-gradient-to-br from-cyber-500 to-cyber-700 shadow-glow-cyan"
              : "bg-surface-700/80 border border-white/[0.08]"
          }`}
        >
          {isUser ? (
            <User size={16} className="text-white" />
          ) : (
            <Cpu size={16} className="text-cyber-400" />
          )}
        </div>
      </div>

      {/* Message content */}
      <div className={`flex flex-col gap-1.5 max-w-[75%] ${isUser ? "items-end" : "items-start"}`}>
        {/* Role label */}
        <span className={`text-[10px] tracking-widest uppercase ${isUser ? "text-cyber-400/60" : "text-white/20"}`}>
          {isUser ? "You" : "Agent"}
        </span>

        {/* Tool call indicator */}
        {typeof message.metadata?.toolCall === "string" && message.metadata.toolCall.length > 0 && (
          <div className="flex items-center gap-2 text-xs px-3 py-1.5 rounded-lg
                          bg-neon-500/10 border border-neon-500/20 text-neon-400/80">
            <Wrench size={12} className="animate-spin" />
            <span>调用工具: {String(message.metadata.toolCall)}</span>
          </div>
        )}

        {/* Message bubble */}
        <div
          className={`rounded-2xl px-4 py-3 ${
            isUser
              ? "bg-gradient-to-br from-cyber-600/60 to-cyber-800/60 border border-cyber-400/20 shadow-glow-cyan"
              : "glass-panel border-white/[0.06]"
          }`}
        >
          {message.content ? (
            <div className="markdown-body">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {message.content}
              </ReactMarkdown>
            </div>
          ) : isStreaming ? (
            <div className="flex items-center gap-1.5 py-1">
              <span
                className="w-1.5 h-1.5 bg-cyber-400 rounded-full animate-bounce-dot"
                style={{ animationDelay: "0s" }}
              />
              <span
                className="w-1.5 h-1.5 bg-cyber-400 rounded-full animate-bounce-dot"
                style={{ animationDelay: "0.15s" }}
              />
              <span
                className="w-1.5 h-1.5 bg-cyber-400 rounded-full animate-bounce-dot"
                style={{ animationDelay: "0.3s" }}
              />
            </div>
          ) : null}
        </div>

        {/* Sources (RAG) */}
        {message.metadata?.sources && message.metadata.sources.length > 0 && (
          <div className="mt-1.5 space-y-1 w-full">
            <div className="text-[10px] text-cyber-400/60 flex items-center gap-1.5 tracking-wider uppercase">
              <span className="w-1 h-1 rounded-full bg-cyber-400/60" />
              知识库来源 ({message.metadata.sources.length})
            </div>
            <div className="space-y-1">
              {message.metadata.sources.map((src, i) => (
                <details
                  key={i}
                  className="text-xs bg-surface-700/50 border border-white/[0.04] rounded-lg
                             cursor-pointer group"
                >
                  <summary className="px-3 py-2 text-white/40 flex items-center gap-2
                                       hover:text-white/60 transition-colors">
                    <span className="font-medium text-white/60">{src.filename}</span>
                    <span className="text-accent-green/70 text-[10px]">
                      相似度: {(src.score * 100).toFixed(1)}%
                    </span>
                  </summary>
                  <div className="px-3 pb-2.5">
                    <p className="text-white/30 whitespace-pre-wrap leading-relaxed border-t border-white/[0.04] pt-2">
                      {src.content.length > 300 ? src.content.slice(0, 300) + "..." : src.content}
                    </p>
                  </div>
                </details>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
