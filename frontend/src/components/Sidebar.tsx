import { useState } from "react";
import {
  Plus, MessageSquare, Trash2, FileText, Settings as SettingsIcon, X, Search, Zap, Cpu, ChevronDown
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
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
    <div className="flex flex-col h-full w-72 glass-panel-strong border-r border-border particle-dots">
      {/* Header */}
      <div className="p-4 border-b border-border">
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
            <Button variant="ghost" size="icon" className="lg:hidden h-8 w-8" onClick={onClose}>
              <X size={18} />
            </Button>
          )}
        </div>

        {/* Agent Selector */}
        <div className="relative">
          <button
            onClick={() => setAgentMenuOpen(!agentMenuOpen)}
            className="w-full flex items-center gap-2.5 rounded-lg px-3 py-2.5
                       bg-surface-700/50 border border-border
                       hover:border-primary/20 transition-all text-left group"
          >
            <Cpu size={12} className="text-primary" />
            <span className="flex-1 text-xs text-foreground/70 truncate">
              {activeAgent?.name || "选择 Agent"}
            </span>
            <ChevronDown
              size={14}
              className={`text-muted-foreground transition-transform duration-200 ${
                agentMenuOpen ? "rotate-180" : ""
              }`}
            />
          </button>

          {agentMenuOpen && (
            <>
              <div className="fixed inset-0 z-10" onClick={() => setAgentMenuOpen(false)} />
              <div className="absolute left-0 right-0 top-full mt-1 z-20
                              glass-panel-strong rounded-lg border border-border
                              shadow-glow-cyan overflow-hidden">
                <div className="max-h-48 overflow-y-auto py-1">
                  {agents.length === 0 ? (
                    <p className="text-xs text-muted-foreground px-3 py-2 text-center">暂无 Agent</p>
                  ) : (
                    agents.map((agent) => (
                      <button
                        key={agent.id}
                        onClick={() => {
                          onSwitchAgent(agent);
                          setAgentMenuOpen(false);
                        }}
                        className={`w-full flex items-center gap-2.5 px-3 py-2 text-left text-xs
                                    transition-colors ${
                          activeAgent?.id === agent.id
                            ? "bg-primary/10 text-primary"
                            : "text-muted-foreground hover:text-foreground hover:bg-muted/30"
                        }`}
                      >
                        <Cpu size={12} />
                        <span className="flex-1 truncate">{agent.name}</span>
                        {agent.is_default && (
                          <span className="text-[9px] px-1.5 py-0.5 rounded
                                           bg-emerald-500/10 text-emerald-500
                                           border border-emerald-500/20">默认</span>
                        )}
                      </button>
                    ))
                  )}
                </div>
              </div>
            </>
          )}
        </div>

        {/* New chat button */}
        <Button
          onClick={onNew}
          className="w-full gap-2 mt-2.5 bg-gradient-to-r from-cyber-500/80 to-neon-500/80
                     hover:from-cyber-500 hover:to-neon-500 text-white border-0"
        >
          <Plus size={15} />
          新对话
        </Button>
      </div>

      {/* Search */}
      <div className="px-4 py-2">
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="搜索对话..."
            className="pl-9 h-9 text-xs bg-surface-700/50"
          />
        </div>
      </div>

      {/* Conversation list */}
      <div className="flex-1 overflow-y-auto px-2 space-y-0.5">
        {filtered.length === 0 ? (
          <div className="text-center py-12">
            <MessageSquare size={28} className="mx-auto text-muted-foreground/20 mb-3" />
            <p className="text-xs text-muted-foreground">
              {search ? "没有匹配的对话" : "暂无对话"}
            </p>
          </div>
        ) : (
          filtered.map((conv) => (
            <div
              key={conv.id}
              onClick={() => onSelect(conv.id)}
              className={`group flex items-center gap-2.5 rounded-lg px-3 py-2.5 cursor-pointer
                         transition-colors text-sm ${
                activeId === conv.id
                  ? "bg-primary/10 border border-primary/20 text-primary"
                  : "text-muted-foreground hover:text-foreground hover:bg-muted/30 border border-transparent"
              }`}
            >
              <MessageSquare size={14} className="flex-shrink-0" />
              <span className="flex-1 truncate text-xs">{conv.title}</span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(conv.id);
                }}
                className="opacity-0 group-hover:opacity-100 text-muted-foreground/30
                           hover:text-destructive transition-all p-0.5"
              >
                <Trash2 size={12} />
              </button>
            </div>
          ))
        )}
      </div>

      {/* Bottom actions */}
      <Separator />
      <div className="p-2 space-y-1">
        <Button
          variant="ghost"
          onClick={onOpenDocuments}
          className="w-full justify-start gap-2.5 text-xs text-muted-foreground hover:text-foreground"
        >
          <FileText size={16} />
          知识库管理
        </Button>
        <Button
          variant="ghost"
          onClick={onOpenSettings}
          className="w-full justify-start gap-2.5 text-xs text-muted-foreground hover:text-foreground"
        >
          <SettingsIcon size={16} />
          Agent 设置
        </Button>
      </div>
    </div>
  );
}
