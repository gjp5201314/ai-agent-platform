import { useState } from "react";
import {
  Plus, MessageSquare, Trash2, FileText, Settings as SettingsIcon, X, Search, Zap, Cpu, ChevronDown
} from "lucide-react";
import type { Conversation, AgentConfig } from "../types";

interface Props {
  conversations: Conversation[];
  agents: AgentConfig[];
  activeAgent: AgentConfig | null;
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
  onSwitchAgent: (agent: AgentConfig) => void;
  onOpenDocuments: () => void;
  onOpenSettings: () => void;
  onClose?: () => void;
}

export function Sidebar({
  conversations,
  agents,
  activeAgent,
  activeId,
  onSelect,
  onNew,
  onDelete,
  onSwitchAgent,
  onOpenDocuments,
  onOpenSettings,
  onClose,
}: Props) {
  const [search, setSearch] = useState("");
  const [agentMenuOpen, setAgentMenuOpen] = useState(false);

  const filtered = conversations.filter((c) =>
    c.title.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="flex flex-col h-full w-72 glass-panel-strong border-r border-white/[0.06] particle-dots">
      {/* Header */}
      <div className="p-4 border-b border-white/[0.06]">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2.5">
            <div className="relative">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyber-400 to-neon-500 flex items-center justify-center shadow-glow-cyan">
                <Zap size={16} className="text-white" />
              </div>
              <div className="absolute inset-0 rounded-lg bg-cyber-400/20 animate-glow-pulse" />
            </div>
            <div>
              <h1 className="text-sm font-bold text-white tracking-wide">AI AGENT</h1>
              <p className="text-[10px] text-cyber-400/60 tracking-widest uppercase">Platform</p>
            </div>
          </div>
          {onClose && (
            <button
              onClick={onClose}
              className="lg:hidden text-white/30 hover:text-white/70 transition-colors"
            >
              <X size={18} />
            </button>
          )}
        </div>

        {/* Agent Selector */}
        <div className="relative">
          <button
            onClick={() => setAgentMenuOpen(!agentMenuOpen)}
            className="w-full flex items-center gap-2.5 rounded-lg px-3 py-2.5
                       bg-surface-700/50 border border-white/[0.06]
                       hover:border-cyber-400/20 transition-all duration-200
                       text-left group"
          >
            <div className="w-5 h-5 rounded bg-gradient-to-br from-cyber-400/20 to-neon-500/20
                            border border-cyber-400/20 flex items-center justify-center flex-shrink-0">
              <Cpu size={11} className="text-cyber-400" />
            </div>
            <span className="flex-1 text-xs text-white/70 truncate">
              {activeAgent?.name || "选择 Agent"}
            </span>
            <ChevronDown
              size={14}
              className={`text-white/30 transition-transform duration-200 ${
                agentMenuOpen ? "rotate-180" : ""
              }`}
            />
          </button>

          {/* Dropdown */}
          {agentMenuOpen && (
            <>
              <div className="fixed inset-0 z-10" onClick={() => setAgentMenuOpen(false)} />
              <div className="absolute left-0 right-0 top-full mt-1 z-20
                              glass-panel-strong rounded-lg border border-white/[0.08]
                              shadow-glow-cyan overflow-hidden">
                <div className="max-h-48 overflow-y-auto py-1">
                  {agents.length === 0 ? (
                    <p className="text-xs text-white/20 px-3 py-2 text-center">暂无 Agent</p>
                  ) : (
                    agents.map((agent) => (
                      <button
                        key={agent.id}
                        onClick={() => {
                          onSwitchAgent(agent);
                          setAgentMenuOpen(false);
                        }}
                        className={`w-full flex items-center gap-2.5 px-3 py-2 text-left text-xs
                                    transition-all duration-150 ${
                          activeAgent?.id === agent.id
                            ? "bg-cyber-400/10 text-cyber-300"
                            : "text-white/50 hover:text-white/80 hover:bg-white/[0.04]"
                        }`}
                      >
                        <Cpu size={12} />
                        <span className="flex-1 truncate">{agent.name}</span>
                        {agent.is_default && (
                          <span className="text-[9px] px-1.5 py-0.5 rounded
                                           bg-accent-green/10 text-accent-green
                                           border border-accent-green/20">默认</span>
                        )}
                      </button>
                    ))
                  )}
                </div>
                <div className="border-t border-white/[0.06] p-1">
                  <button
                    onClick={() => {
                      onOpenSettings();
                      setAgentMenuOpen(false);
                    }}
                    className="w-full flex items-center gap-2 px-3 py-2 text-xs
                               text-white/30 hover:text-white/60 transition-colors"
                  >
                    <SettingsIcon size={12} />
                    管理 Agent
                  </button>
                </div>
              </div>
            </>
          )}
        </div>

        {/* New chat button */}
        <button
          onClick={onNew}
          className="w-full flex items-center justify-center gap-2 rounded-lg mt-2.5
                     bg-gradient-to-r from-cyber-500/20 to-neon-500/20
                     border border-cyber-400/20 hover:border-cyber-400/40
                     text-cyber-300 hover:text-cyber-200 px-4 py-2 text-sm font-medium
                     transition-all duration-300 hover:shadow-glow-cyan
                     group"
        >
          <Plus size={15} className="group-hover:rotate-90 transition-transform duration-300" />
          <span>新对话</span>
        </button>
      </div>

      {/* Search */}
      <div className="px-4 py-2">
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/20" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="搜索对话..."
            className="w-full rounded-lg bg-surface-700/50 border border-white/[0.06]
                       pl-9 pr-3 py-2 text-xs text-white/70 placeholder-white/20
                       focus:outline-none focus:border-cyber-400/30 focus:ring-1 focus:ring-cyber-400/20
                       transition-all duration-300"
          />
        </div>
      </div>

      {/* Conversation list */}
      <div className="flex-1 overflow-y-auto px-2 space-y-0.5">
        {filtered.length === 0 ? (
          <div className="text-center py-12">
            <MessageSquare size={28} className="mx-auto text-white/10 mb-3" />
            <p className="text-xs text-white/20">
              {search ? "没有匹配的对话" : "暂无对话"}
            </p>
          </div>
        ) : (
          filtered.map((conv) => (
            <div
              key={conv.id}
              onClick={() => onSelect(conv.id)}
              className={`group flex items-center gap-2.5 rounded-lg px-3 py-2.5 cursor-pointer
                         transition-all duration-200 text-sm ${
                activeId === conv.id
                  ? "bg-cyber-400/10 border border-cyber-400/20 text-cyber-300 shadow-glow-cyan"
                  : "text-white/50 hover:text-white/80 hover:bg-white/[0.04] border border-transparent"
              }`}
            >
              <MessageSquare size={14} className="flex-shrink-0" />
              <span className="flex-1 truncate text-xs">{conv.title}</span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(conv.id);
                }}
                className="opacity-0 group-hover:opacity-100 text-white/20 hover:text-accent-pink
                           transition-all duration-200 p-0.5"
              >
                <Trash2 size={12} />
              </button>
            </div>
          ))
        )}
      </div>

      {/* Bottom actions */}
      <div className="border-t border-white/[0.06] p-2 space-y-0.5">
        <button
          onClick={onOpenDocuments}
          className="w-full flex items-center gap-2.5 rounded-lg px-3 py-2.5 text-xs
                     text-white/40 hover:text-white/80 hover:bg-white/[0.04]
                     transition-all duration-200"
        >
          <FileText size={16} />
          知识库管理
        </button>
        <button
          onClick={onOpenSettings}
          className="w-full flex items-center gap-2.5 rounded-lg px-3 py-2.5 text-xs
                     text-white/40 hover:text-white/80 hover:bg-white/[0.04]
                     transition-all duration-200"
        >
          <SettingsIcon size={16} />
          Agent 设置
        </button>
      </div>

      {/* Bottom glow line */}
      <div className="neon-divider mx-4 mb-2" />
    </div>
  );
}
