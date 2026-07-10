import { useState, useEffect } from "react";
import { Plus, MessageSquare, Trash2, FileText, Settings as SettingsIcon, X } from "lucide-react";
import { api } from "../api/client";
import type { Conversation } from "../types";

interface Props {
  conversations: Conversation[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
  onOpenDocuments: () => void;
  onOpenSettings: () => void;
  onClose?: () => void;
}

export function Sidebar({
  conversations,
  activeId,
  onSelect,
  onNew,
  onDelete,
  onOpenDocuments,
  onOpenSettings,
  onClose,
}: Props) {
  const [search, setSearch] = useState("");

  const filtered = conversations.filter((c) =>
    c.title.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="flex flex-col h-full bg-slate-50 border-r border-slate-200 w-72">
      {/* Header */}
      <div className="p-3 flex items-center justify-between border-b border-slate-200">
        <h1 className="font-bold text-lg text-slate-800 flex items-center gap-2">
          <span className="text-2xl">🤖</span>
          AI Agent
        </h1>
        {onClose && (
          <button onClick={onClose} className="lg:hidden text-slate-400 hover:text-slate-600">
            <X size={20} />
          </button>
        )}
      </div>

      {/* New chat */}
      <div className="p-3">
        <button
          onClick={onNew}
          className="w-full flex items-center gap-2 justify-center rounded-xl bg-brand-600 hover:bg-brand-700 text-white px-4 py-2.5 text-sm font-medium transition-colors"
        >
          <Plus size={18} />
          新对话
        </button>
      </div>

      {/* Search */}
      <div className="px-3 pb-2">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="搜索对话..."
          className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-brand-300"
        />
      </div>

      {/* Conversation list */}
      <div className="flex-1 overflow-y-auto px-2 space-y-1">
        {filtered.length === 0 ? (
          <p className="text-center text-sm text-slate-400 mt-8">
            {search ? "没有匹配的对话" : "暂无对话"}
          </p>
        ) : (
          filtered.map((conv) => (
            <div
              key={conv.id}
              onClick={() => onSelect(conv.id)}
              className={`group flex items-center gap-2 rounded-lg px-3 py-2.5 cursor-pointer transition-colors ${
                activeId === conv.id
                  ? "bg-brand-100 text-brand-700"
                  : "hover:bg-slate-100 text-slate-600"
              }`}
            >
              <MessageSquare size={16} className="flex-shrink-0" />
              <span className="flex-1 truncate text-sm">{conv.title}</span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(conv.id);
                }}
                className="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-red-500 transition-opacity"
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))
        )}
      </div>

      {/* Bottom buttons */}
      <div className="border-t border-slate-200 p-2 space-y-1">
        <button
          onClick={onOpenDocuments}
          className="w-full flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-slate-600 hover:bg-slate-100 transition-colors"
        >
          <FileText size={18} />
          知识库管理
        </button>
        <button
          onClick={onOpenSettings}
          className="w-full flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-slate-600 hover:bg-slate-100 transition-colors"
        >
          <SettingsIcon size={18} />
          Agent 设置
        </button>
      </div>
    </div>
  );
}
