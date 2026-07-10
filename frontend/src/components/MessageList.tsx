import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Message } from "../types";

interface Props {
  messages: Message[];
  isStreaming: boolean;
}

export function MessageList({ messages, isStreaming }: Props) {
  if (messages.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center max-w-md">
          <div className="text-6xl mb-4">🤖</div>
          <h2 className="text-2xl font-semibold text-slate-700 mb-2">
            AI Agent Platform
          </h2>
          <p className="text-slate-500">
            支持知识库问答 (RAG)、工具调用和多轮对话。
            <br />
            发送消息开始对话吧！
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6 space-y-6">
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
    <div className={`flex gap-4 ${isUser ? "flex-row-reverse" : ""} animate-slide-up`}>
      {/* Avatar */}
      <div
        className={`flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center text-lg ${
          isUser ? "bg-brand-600 text-white" : "bg-slate-100 text-slate-600"
        }`}
      >
        {isUser ? "👤" : "🤖"}
      </div>

      {/* Message bubble */}
      <div className={`flex flex-col gap-1 max-w-[75%] ${isUser ? "items-end" : "items-start"}`}>
        {/* Tool call indicator */}
        {typeof message.metadata?.toolCall === "string" && message.metadata.toolCall.length > 0 && (
          <div className="flex items-center gap-2 text-xs text-slate-400 px-3 py-1 bg-slate-50 rounded-lg">
            <span className="animate-spin">⚙️</span>
            正在调用工具: {String(message.metadata.toolCall)}
          </div>
        )}

        <div
          className={`rounded-2xl px-4 py-3 ${
            isUser
              ? "bg-brand-600 text-white"
              : "bg-white border border-slate-200 text-slate-800"
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
              <span className="w-2 h-2 bg-slate-300 rounded-full animate-bounce-dot" style={{ animationDelay: "0s" }} />
              <span className="w-2 h-2 bg-slate-300 rounded-full animate-bounce-dot" style={{ animationDelay: "0.16s" }} />
              <span className="w-2 h-2 bg-slate-300 rounded-full animate-bounce-dot" style={{ animationDelay: "0.32s" }} />
            </div>
          ) : null}
        </div>

        {/* Sources (RAG) */}
        {message.metadata?.sources && message.metadata.sources.length > 0 && (
          <div className="mt-1 space-y-1 w-full">
            <div className="text-xs text-slate-400 flex items-center gap-1">
              📎 知识库来源 ({message.metadata.sources.length})
            </div>
            <div className="space-y-1">
              {message.metadata.sources.map((src, i) => (
                <details key={i} className="text-xs bg-slate-50 rounded-lg p-2 cursor-pointer">
                  <summary className="text-slate-500 flex items-center gap-2">
                    <span className="font-medium">{src.filename}</span>
                    <span className="text-green-600">相似度: {(src.score * 100).toFixed(1)}%</span>
                  </summary>
                  <p className="mt-1 text-slate-600 whitespace-pre-wrap">
                    {src.content.length > 300 ? src.content.slice(0, 300) + "..." : src.content}
                  </p>
                </details>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
