import { useState, useEffect } from "react";
import { X, Plus, Trash2, Save } from "lucide-react";
import { api } from "../api/client";
import type { AgentConfig, ToolInfo } from "../types";

interface Props {
  onClose: () => void;
  onAgentChange?: (agent: AgentConfig | null) => void;
}

export function Settings({ onClose, onAgentChange }: Props) {
  const [agents, setAgents] = useState<AgentConfig[]>([]);
  const [tools, setTools] = useState<ToolInfo[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [editing, setEditing] = useState<Partial<AgentConfig>>({});

  const loadData = async () => {
    try {
      const [agentList, toolList] = await Promise.all([api.listAgents(), api.listTools()]);
      setAgents(agentList);
      setTools(toolList.tools);
      const defaultAgent = agentList.find((a) => a.is_default) || agentList[0];
      if (defaultAgent) {
        setSelectedId(defaultAgent.id);
        setEditing(defaultAgent);
      }
    } catch (err) {
      console.error("Failed to load settings:", err);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleSelect = (agent: AgentConfig) => {
    setSelectedId(agent.id);
    setEditing(agent);
  };

  const handleSave = async () => {
    if (!selectedId) return;
    try {
      await api.updateAgent(selectedId, editing);
      await loadData();
      alert("保存成功");
    } catch (err) {
      alert(`保存失败: ${(err as Error).message}`);
    }
  };

  const handleNew = async () => {
    try {
      const agent = await api.createAgent({
        name: "新 Agent",
        description: "",
        system_prompt: "You are a helpful AI assistant.",
        temperature: 0.7,
        max_tokens: 4096,
        enabled_tools: ["rag"],
        rag_top_k: 4,
        rag_similarity_threshold: 0.5,
      });
      await loadData();
      setSelectedId(agent.id);
      setEditing(agent);
    } catch (err) {
      alert(`创建失败: ${(err as Error).message}`);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("确定删除此 Agent？")) return;
    try {
      await api.deleteAgent(id);
      await loadData();
      setSelectedId(null);
      setEditing({});
    } catch (err) {
      alert(`删除失败: ${(err as Error).message}`);
    }
  };

  const toggleTool = (toolName: string) => {
    const current = editing.enabled_tools || [];
    setEditing({
      ...editing,
      enabled_tools: current.includes(toolName)
        ? current.filter((t) => t !== toolName)
        : [...current, toolName],
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={onClose}>
      <div
        className="bg-white rounded-2xl shadow-xl w-full max-w-4xl max-h-[85vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-slate-200">
          <h2 className="text-xl font-bold text-slate-800">Agent 设置</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <X size={22} />
          </button>
        </div>

        <div className="flex-1 overflow-hidden flex">
          {/* Agent list */}
          <div className="w-56 border-r border-slate-200 overflow-y-auto p-3 space-y-1">
            {agents.map((agent) => (
              <div
                key={agent.id}
                onClick={() => handleSelect(agent)}
                className={`group flex items-center gap-2 rounded-lg px-3 py-2 cursor-pointer text-sm ${
                  selectedId === agent.id ? "bg-brand-100 text-brand-700" : "hover:bg-slate-100"
                }`}
              >
                <span className="flex-1 truncate">{agent.name}</span>
                {agent.is_default && <span className="text-xs text-green-600">默认</span>}
                {!agent.is_default && (
                  <button
                    onClick={(e) => { e.stopPropagation(); handleDelete(agent.id); }}
                    className="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-red-500"
                  >
                    <Trash2 size={14} />
                  </button>
                )}
              </div>
            ))}
            <button
              onClick={handleNew}
              className="w-full flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-brand-600 hover:bg-brand-50"
            >
              <Plus size={16} /> 新建 Agent
            </button>
          </div>

          {/* Editor */}
          <div className="flex-1 overflow-y-auto p-5 space-y-4">
            {selectedId && editing ? (
              <>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">名称</label>
                  <input
                    value={editing.name || ""}
                    onChange={(e) => setEditing({ ...editing, name: e.target.value })}
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:ring-2 focus:ring-brand-300 focus:outline-none"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">描述</label>
                  <input
                    value={editing.description || ""}
                    onChange={(e) => setEditing({ ...editing, description: e.target.value })}
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:ring-2 focus:ring-brand-300 focus:outline-none"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">系统提示词</label>
                  <textarea
                    value={editing.system_prompt || ""}
                    onChange={(e) => setEditing({ ...editing, system_prompt: e.target.value })}
                    rows={5}
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm font-mono focus:ring-2 focus:ring-brand-300 focus:outline-none resize-y"
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1">
                      温度 ({editing.temperature})
                    </label>
                    <input
                      type="range"
                      min="0"
                      max="2"
                      step="0.1"
                      value={editing.temperature || 0.7}
                      onChange={(e) => setEditing({ ...editing, temperature: parseFloat(e.target.value) })}
                      className="w-full"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1">最大 Token</label>
                    <input
                      type="number"
                      value={editing.max_tokens || 4096}
                      onChange={(e) => setEditing({ ...editing, max_tokens: parseInt(e.target.value) })}
                      className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:ring-2 focus:ring-brand-300 focus:outline-none"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-2">启用工具</label>
                  <div className="space-y-2">
                    {tools.map((tool) => (
                      <label
                        key={tool.name}
                        className="flex items-start gap-3 p-2 rounded-lg hover:bg-slate-50 cursor-pointer"
                      >
                        <input
                          type="checkbox"
                          checked={(editing.enabled_tools || []).includes(tool.name)}
                          onChange={() => toggleTool(tool.name)}
                          className="mt-1"
                        />
                        <div>
                          <p className="text-sm font-medium text-slate-700">{tool.name}</p>
                          <p className="text-xs text-slate-400">{tool.description}</p>
                        </div>
                      </label>
                    ))}
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1">RAG 检索数量 (K)</label>
                    <input
                      type="number"
                      min="1"
                      max="20"
                      value={editing.rag_top_k || 4}
                      onChange={(e) => setEditing({ ...editing, rag_top_k: parseInt(e.target.value) })}
                      className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:ring-2 focus:ring-brand-300 focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1">
                      相似度阈值 ({editing.rag_similarity_threshold})
                    </label>
                    <input
                      type="range"
                      min="0"
                      max="1"
                      step="0.05"
                      value={editing.rag_similarity_threshold || 0.5}
                      onChange={(e) => setEditing({ ...editing, rag_similarity_threshold: parseFloat(e.target.value) })}
                      className="w-full"
                    />
                  </div>
                </div>

                <button
                  onClick={handleSave}
                  className="flex items-center gap-2 rounded-lg bg-brand-600 hover:bg-brand-700 text-white px-6 py-2.5 text-sm font-medium transition-colors"
                >
                  <Save size={16} /> 保存设置
                </button>
              </>
            ) : (
              <div className="flex items-center justify-center h-full text-slate-400">
                选择一个 Agent 进行编辑
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
