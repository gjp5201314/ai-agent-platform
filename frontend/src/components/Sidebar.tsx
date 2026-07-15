import { useState } from "react";
import {
  Plus, MessageSquare, Trash2, FileText, Settings as SettingsIcon, X, Search, Bot, Cpu, ChevronDown, SlidersHorizontal
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
  onOpenAdmin: () => void;
  onClose?: () => void;
  sandboxOnline?: boolean | null;
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
  onOpenAdmin,
  onClose,
  sandboxOnline,
}: Props) {
  const [search, setSearch] = useState("");
  const [agentMenuOpen, setAgentMenuOpen] = useState(false);

  const filtered = conversations.filter((c) =>
    c.title.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="flex flex-col h-full w-64 bg-[#f8f9fa] border-r border-gray-200">
      {/* Header */}
      <div className="p-4 border-b border-gray-200">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-lg bg-ds-500 flex items-center justify-center">
              <Bot size={18} className="text-white" />
            </div>
            <div>
              <h1 className="text-sm font-semibold text-gray-800">AI Agent</h1>
              <p className="text-[10px] text-gray-400">Platform</p>
            </div>
          </div>
          {onClose && (
            <Button variant="ghost" size="icon" className="lg:hidden h-8 w-8 text-gray-500" onClick={onClose}>
              <X size={18} />
            </Button>
          )}
        </div>

        {/* Agent Selector */}
        <div className="relative">
          <button
            onClick={() => setAgentMenuOpen(!agentMenuOpen)}
            className="w-full flex items-center gap-2.5 rounded-lg px-3 py-2
                       bg-white border border-gray-200
                       hover:border-gray-300 transition-all text-left"
          >
            <Cpu size={12} className="text-ds-500" />
            <span className="flex-1 text-xs text-gray-600 truncate">
              {activeAgent?.name || "选择 Agent"}
            </span>
            <ChevronDown
              size={14}
              className={`text-gray-400 transition-transform duration-200 ${
                agentMenuOpen ? "rotate-180" : ""
              }`}
            />
          </button>

          {agentMenuOpen && (
            <>
              <div className="fixed inset-0 z-10" onClick={() => setAgentMenuOpen(false)} />
              <div className="absolute left-0 right-0 top-full mt-1 z-20
                              bg-white rounded-lg border border-gray-200
                              shadow-lg overflow-hidden">
                <div className="max-h-48 overflow-y-auto py-1">
                  {agents.length === 0 ? (
                    <p className="text-xs text-gray-400 px-3 py-2 text-center">暂无 Agent</p>
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
                            ? "bg-ds-50 text-ds-600"
                            : "text-gray-600 hover:text-gray-800 hover:bg-gray-50"
                        }`}
                      >
                        <Cpu size={12} />
                        <span className="flex-1 truncate">{agent.name}</span>
                        {agent.is_default && (
                          <span className="text-[9px] px-1.5 py-0.5 rounded
                                           bg-emerald-50 text-emerald-600
                                           border border-emerald-200">默认</span>
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
          className="w-full gap-2 mt-2.5 bg-ds-500 hover:bg-ds-600 text-white border-0 shadow-sm"
        >
          <Plus size={15} />
          新对话
        </Button>
      </div>

      {/* Search */}
      <div className="px-4 py-2">
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="搜索对话..."
            className="pl-9 h-9 text-xs bg-white border-gray-200"
          />
        </div>
      </div>

      {/* Conversation list */}
      <div className="flex-1 overflow-y-auto px-2 space-y-0.5">
        {filtered.length === 0 ? (
          <div className="text-center py-12">
            <MessageSquare size={28} className="mx-auto text-gray-200 mb-3" />
            <p className="text-xs text-gray-400">
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
                  ? "bg-ds-50 text-ds-600 font-medium"
                  : "text-gray-600 hover:text-gray-800 hover:bg-gray-100"
              }`}
            >
              <MessageSquare size={14} className="flex-shrink-0" />
              <span className="flex-1 truncate text-xs">{conv.title}</span>
              <span className="text-[10px] text-gray-300 tabular-nums flex-shrink-0">
                {conv.message_count}
              </span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(conv.id);
                }}
                className="opacity-0 group-hover:opacity-100 text-gray-300
                           hover:text-red-500 transition-all p-0.5"
              >
                <Trash2 size={12} />
              </button>
            </div>
          ))
        )}
      </div>

      {/* Bottom actions */}
      <Separator className="bg-gray-200" />
      <div className="p-2 space-y-0.5">
        <Button
          variant="ghost"
          onClick={onOpenDocuments}
          className="w-full justify-start gap-2.5 text-xs text-gray-500 hover:text-gray-800 hover:bg-gray-100"
        >
          <FileText size={16} />
          知识库管理
        </Button>
        <Button
          variant="ghost"
          onClick={onOpenSettings}
          className="w-full justify-start gap-2.5 text-xs text-gray-500 hover:text-gray-800 hover:bg-gray-100"
        >
          <SettingsIcon size={16} />
          Agent 设置
        </Button>
        <Button
          variant="ghost"
          onClick={onOpenAdmin}
          className="w-full justify-start gap-2.5 text-xs text-gray-500 hover:text-gray-800 hover:bg-gray-100"
        >
          <SlidersHorizontal size={16} />
          管理后台
        </Button>

        {/* Sandbox status indicator */}
        {sandboxOnline !== null && (
          <div className="flex items-center gap-2 px-3 py-2">
            <span
              className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                sandboxOnline ? "bg-emerald-400" : "bg-red-400"
              }`}
            />
            <span className="text-[10px] text-gray-400">
              {sandboxOnline ? "沙盒运行中" : "沙盒离线"}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
