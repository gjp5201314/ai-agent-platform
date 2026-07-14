import { useRef, useEffect, useState, useCallback, memo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Bot, User, Wrench, FileText, Copy, Check, Sparkles, ArrowRightLeft } from "lucide-react";
import type { Message } from "../types";

interface Props {
  messages: Message[];
  isStreaming: boolean;
  activeAgentId?: string | null;
  agents?: { id: string; name: string }[];
}

export function MessageList({ messages, isStreaming, activeAgentId, agents }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const [lastSeenAgent, setLastSeenAgent] = useState<string | null>(null);

  // Show a notification entry when agent switches
  const agentName = agents?.find(a => a.id === activeAgentId)?.name || activeAgentId;
  const showSwitch = activeAgentId && activeAgentId !== lastSeenAgent;

  useEffect(() => {
    if (activeAgentId) setLastSeenAgent(activeAgentId);
  }, [activeAgentId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: isStreaming ? "auto" : "instant" as any });
  }, [messages, isStreaming]);

  if (messages.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center max-w-md px-6">
          {/* Simple icon */}
          <div className="mx-auto mb-6 w-16 h-16 rounded-2xl bg-ds-50 flex items-center justify-center">
            <Bot size={28} className="text-ds-500" />
          </div>

          <h2 className="text-2xl font-bold mb-2 text-gray-800">
            AI Agent Platform
          </h2>

          <p className="text-gray-400 text-sm leading-relaxed mb-6">
            支持知识库问答 (RAG)、工具调用和多轮对话
          </p>

          {/* Feature pills */}
          <div className="flex flex-wrap gap-2 justify-center">
            {["知识库 RAG", "多轮对话", "工具调用", "流式响应"].map((f) => (
              <span
                key={f}
                className="px-3 py-1.5 rounded-full text-xs
                           bg-gray-100 border border-gray-200
                           text-gray-500"
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
    <div className="h-full overflow-y-auto px-4 py-6 space-y-6">
      {showSwitch && agentName && (
        <div className="flex justify-center">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full
                          bg-ds-50 border border-ds-200 text-xs text-ds-600 font-medium
                          animate-slide-up">
            <ArrowRightLeft size={12} />
            已切换到 <span className="font-semibold">{agentName}</span>
          </div>
        </div>
      )}
      {messages.map((msg, idx) => (
        <MessageItem
          key={idx}
          message={msg}
          isStreaming={isStreaming && idx === messages.length - 1 && msg.role === "assistant"}
        />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}

const MessageItem = memo(function MessageItem({ message, isStreaming }: { message: Message; isStreaming: boolean }) {
  const isUser = message.role === "user";
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    if (!message.content) return;
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      const textarea = document.createElement("textarea");
      textarea.value = message.content;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }, [message.content]);

  return (
    <div className={`flex gap-3 ${isUser ? "flex-row-reverse" : ""} animate-slide-up`}>
      {/* Avatar */}
      <div className="flex-shrink-0 mt-0.5">
        <div
          className={`w-8 h-8 rounded-lg flex items-center justify-center ${
            isUser
              ? "bg-ds-500 text-white"
              : "bg-gray-100 text-gray-500"
          }`}
        >
          {isUser ? (
            <User size={15} />
          ) : (
            <Bot size={15} />
          )}
        </div>
      </div>

      {/* Message content */}
      <div className={`flex flex-col gap-1 max-w-[75%] ${isUser ? "items-end" : "items-start"}`}>
        {/* Role label */}
        <span className={`text-[10px] font-medium ${isUser ? "text-ds-400" : "text-gray-300"}`}>
          {isUser ? "You" : "AI"}
        </span>

        {/* Tool call indicator */}
        {typeof message.metadata?.toolCall === "string" && message.metadata.toolCall.length > 0 && (
          <div className="flex items-center gap-2 text-xs px-3 py-1.5 rounded-lg
                          bg-purple-50 border border-purple-200 text-purple-600">
            <Wrench size={12} />
            <span>调用工具: {String(message.metadata.toolCall)}</span>
          </div>
        )}

        {/* Message bubble */}
        <div
          className={`rounded-2xl px-4 py-3 overflow-hidden relative group ${
            isUser
              ? "bg-ds-50 border border-ds-100 text-gray-800"
              : "bg-white border border-gray-100 shadow-sm"
          }`}
        >
          {/* Attachments display */}
          {message.metadata?.attachments && message.metadata.attachments.length > 0 && (
            <div className="flex flex-wrap gap-2 mb-3">
              {message.metadata.attachments.map((att) => (
                <div
                  key={att.id}
                  className={`rounded-lg overflow-hidden border border-gray-200 ${
                    att.type.startsWith("image/") ? "w-24 h-24" : ""
                  }`}
                >
                  {att.type.startsWith("image/") ? (
                    <img
                      src={att.url}
                      alt={att.filename}
                      className="w-full h-full object-cover cursor-pointer hover:opacity-90 transition-opacity"
                      onClick={() => window.open(att.url, "_blank")}
                    />
                  ) : (
                    <a
                      href={att.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-2 px-3 py-2 text-xs
                                 bg-gray-50 hover:bg-gray-100
                                 transition-colors min-w-[120px]"
                    >
                      <FileText size={14} className="text-ds-400 flex-shrink-0" />
                      <span className="text-gray-500 truncate max-w-[100px]">
                        {att.filename}
                      </span>
                    </a>
                  )}
                </div>
              ))}
            </div>
          )}

          {message.content ? (
            <div className="markdown-body">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {message.content}
              </ReactMarkdown>
            </div>
          ) : isStreaming ? (
            <div className="flex items-center gap-1.5 py-1">
              <span
                className="w-1.5 h-1.5 bg-ds-400 rounded-full animate-bounce-dot"
                style={{ animationDelay: "0s" }}
              />
              <span
                className="w-1.5 h-1.5 bg-ds-400 rounded-full animate-bounce-dot"
                style={{ animationDelay: "0.15s" }}
              />
              <span
                className="w-1.5 h-1.5 bg-ds-400 rounded-full animate-bounce-dot"
                style={{ animationDelay: "0.3s" }}
              />
            </div>
          ) : null}
        </div>

        {/* Meta row */}
        <div
          className={`flex items-center gap-1.5 text-[10px] text-gray-300
            ${isUser ? "flex-row-reverse" : ""}`}
        >
          <span>
            {new Date().toLocaleTimeString("zh-CN", {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </span>
          {message.content && (
            <button
              onClick={handleCopy}
              className={`p-0.5 rounded transition-all
                ${copied
                  ? "text-emerald-500"
                  : "text-gray-300 hover:text-gray-500"
                }`}
              title={copied ? "已复制" : "复制"}
            >
              {copied ? <Check size={11} /> : <Copy size={11} />}
            </button>
          )}
        </div>

        {/* Sources (RAG) */}
        {message.metadata?.sources && message.metadata.sources.length > 0 && (
          <div className="mt-1.5 space-y-1 w-full">
            <div className="text-[10px] text-ds-400 flex items-center gap-1.5 font-medium">
              <Sparkles size={10} />
              知识库来源 ({message.metadata.sources.length})
            </div>
            <div className="space-y-1">
              {message.metadata.sources.map((src, i) => (
                <details
                  key={i}
                  className="text-xs bg-gray-50 border border-gray-100 rounded-lg
                             cursor-pointer group"
                >
                  <summary className="px-3 py-2 text-gray-500 flex items-center gap-2
                                       hover:text-gray-700 transition-colors">
                    <span className="font-medium text-gray-600">{src.filename}</span>
                    <span className="text-emerald-600 text-[10px]">
                      相似度: {(src.score * 100).toFixed(1)}%
                    </span>
                  </summary>
                  <div className="px-3 pb-2.5">
                    <p className="text-gray-400 whitespace-pre-wrap leading-relaxed border-t border-gray-100 pt-2">
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
