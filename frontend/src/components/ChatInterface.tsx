/**
 * 聊天界面主组件
 * 
 * 功能说明：
 * 1. 显示消息列表和输入框
 * 2. 显示上下文窗口使用进度条
 * 3. 移动端顶部导航栏
 * 4. RAG开关和模型选择器
 */

import { useMemo } from "react";
import { Menu, Bot, FlaskConical } from "lucide-react";
import { MessageList } from "./MessageList";
import { MessageInput } from "./MessageInput";
import type { Message, AgentConfig } from "../types";

interface Props {
  messages: Message[];              // 消息列表
  isStreaming: boolean;             // 是否正在流式输出
  activeAgent: AgentConfig | null;  // 当前激活的Agent
  activeAgentId?: string | null;    // 当前Agent ID
  agents?: { id: string; name: string }[]; // Agent列表（简化版）
  onSend: (message: string) => void;       // 发送消息回调
  onStop: () => void;                      // 停止生成回调
  useRag: boolean;                         // 是否启用RAG
  onToggleRag: () => void;                 // 切换RAG回调
  onOpenSidebar: () => void;               // 打开侧边栏回调
  modelProvider: string | null;            // 当前模型提供商
  onModelProviderChange: (provider: string | null) => void; // 切换模型回调
  onOpenAdmin: () => void;                 // 打开管理后台回调
  mockMode: boolean;                       // Mock 模式状态
  onToggleMockMode: () => void;            // 切换 Mock 模式回调
}

/**
 * 估算消息的Token数量
 * 简单估算：每2个字符约等于1个Token
 */
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
  mockMode,
  onToggleMockMode,
}: Props) {
  // 计算上下文窗口使用情况
  const maxTokens = activeAgent?.max_tokens || 4096;
  const estimated = useMemo(() => estimateTokens(messages), [messages]);
  const pct = Math.min(100, Math.round((estimated / maxTokens) * 100));
  const isFull = pct >= 85;      // 红色警告
  const isWarning = pct >= 65 && pct < 85; // 黄色警告

  return (
    <div className="flex flex-col h-full bg-white">
      {/* ========== Mock 模式提示横幅 ========== */}
      {mockMode && (
        <div className="flex-shrink-0 px-4 py-1.5 bg-amber-50 border-b border-amber-200">
          <div className="max-w-4xl mx-auto flex items-center gap-2 text-xs text-amber-700">
            <FlaskConical size={14} className="text-amber-500 flex-shrink-0" />
            <span className="font-medium">Mock 模式已启用</span>
            <span className="text-amber-500 hidden sm:inline">— 所有回复均为模拟数据，不消耗 API Key</span>
          </div>
        </div>
      )}

      {/* ========== 上下文窗口进度条 ========== */}
      {messages.length > 0 && (
        <div className="relative z-10 flex-shrink-0 px-4 pt-3 pb-0">
          <div className="max-w-4xl mx-auto flex items-center gap-2">
            {/* 进度条 */}
            <div className="flex-1 h-1 rounded-full bg-gray-100 overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-500 ${
                  isFull ? "bg-red-500" : isWarning ? "bg-amber-500" : "bg-ds-400/60"
                }`}
                style={{ width: `${pct}%` }}
              />
            </div>
            {/* Token数量显示 */}
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

      {/* ========== 移动端顶部导航栏 ========== */}
      <div className="lg:hidden flex items-center gap-3 p-3 bg-white border-b border-gray-200 relative z-10">
        {/* 侧边栏按钮 */}
        <button
          onClick={onOpenSidebar}
          className="text-gray-500 hover:text-gray-800 transition-colors"
        >
          <Menu size={20} />
        </button>
        {/* 当前Agent名称 */}
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <Bot size={14} className="text-ds-500 flex-shrink-0" />
          <span className="font-medium text-sm text-gray-700 truncate">
            {activeAgent?.name || "AI Agent"}
          </span>
        </div>
      </div>

      {/* ========== 消息列表 ========== */}
      <div className="relative z-10 flex-1 min-h-0">
        <MessageList messages={messages} isStreaming={isStreaming} activeAgentId={activeAgentId} agents={agents} />
      </div>

      {/* ========== 输入框 ========== */}
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
          mockMode={mockMode}
          onToggleMockMode={onToggleMockMode}
        />
      </div>
    </div>
  );
}