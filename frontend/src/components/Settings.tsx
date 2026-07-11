import { useState, useEffect } from "react";
import { X, Plus, Trash2, Save, Cpu, Sliders } from "lucide-react";
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
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="glass-panel-strong rounded-2xl w-full max-w-4xl max-h-[85vh] flex flex-col
                     shadow-glow-neon overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-white/[0.06]">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyber-400/20 to-neon-500/20
                            border border-cyber-400/20 flex items-center justify-center">
              <Sliders size={16} className="text-cyber-400" />
            </div>
            <h2 className="text-lg font-bold text-white">Agent 设置</h2>
          </div>
          <button
            onClick={onClose}
            className="text-white/20 hover:text-white/60 transition-colors p-1"
          >
            <X size={20} />
          </button>
        </div>

        <div className="flex-1 overflow-hidden flex">
          {/* Agent list sidebar */}
          <div className="w-56 border-r border-white/[0.06] overflow-y-auto p-3 space-y-0.5">
            {agents.map((agent) => (
              <div
                key={agent.id}
                onClick={() => handleSelect(agent)}
                className={`group flex items-center gap-2 rounded-lg px-3 py-2.5 cursor-pointer text-sm
                           transition-all duration-200 ${
                  selectedId === agent.id
                    ? "bg-cyber-400/10 border border-cyber-400/20 text-cyber-300"
                    : "text-white/40 hover:text-white/70 hover:bg-white/[0.04] border border-transparent"
                }`}
              >
                <Cpu size={14} />
                <span className="flex-1 truncate text-xs">{agent.name}</span>
                {agent.is_default && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent-green/10
                                   text-accent-green border border-accent-green/20 font-medium">
                    默认
                  </span>
                )}
                {!agent.is_default && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDelete(agent.id);
                    }}
                    className="opacity-0 group-hover:opacity-100 text-white/10 hover:text-accent-pink
                               transition-all duration-200"
                  >
                    <Trash2 size={12} />
                  </button>
                )}
              </div>
            ))}

            {/* New agent button */}
            <button
              onClick={handleNew}
              className="w-full flex items-center gap-2 rounded-lg px-3 py-2.5 text-xs
                         text-cyber-400/60 hover:text-cyber-400
                         hover:bg-cyber-400/5 border border-transparent hover:border-cyber-400/10
                         transition-all duration-200 mt-2"
            >
              <Plus size={14} />
              新建 Agent
            </button>
          </div>

          {/* Editor panel */}
          <div className="flex-1 overflow-y-auto p-6 space-y-5">
            {selectedId && editing ? (
              <>
                {/* Name */}
                <div className="space-y-1.5">
                  <label className="text-xs text-white/40 tracking-wider uppercase font-medium">
                    名称
                  </label>
                  <input
                    value={editing.name || ""}
                    onChange={(e) => setEditing({ ...editing, name: e.target.value })}
                    className="w-full glass-input rounded-lg px-3 py-2.5 text-sm text-white/80
                               placeholder-white/10 focus:outline-none"
                  />
                </div>

                {/* Description */}
                <div className="space-y-1.5">
                  <label className="text-xs text-white/40 tracking-wider uppercase font-medium">
                    描述
                  </label>
                  <input
                    value={editing.description || ""}
                    onChange={(e) => setEditing({ ...editing, description: e.target.value })}
                    className="w-full glass-input rounded-lg px-3 py-2.5 text-sm text-white/80
                               placeholder-white/10 focus:outline-none"
                  />
                </div>

                {/* System prompt */}
                <div className="space-y-1.5">
                  <label className="text-xs text-white/40 tracking-wider uppercase font-medium">
                    系统提示词
                  </label>
                  <textarea
                    value={editing.system_prompt || ""}
                    onChange={(e) => setEditing({ ...editing, system_prompt: e.target.value })}
                    rows={5}
                    className="w-full glass-input rounded-lg px-3 py-2.5 text-sm font-mono text-white/80
                               placeholder-white/10 focus:outline-none resize-y"
                  />
                </div>

                {/* Temperature + Max Tokens */}
                <div className="grid grid-cols-2 gap-5">
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between">
                      <label className="text-xs text-white/40 tracking-wider uppercase font-medium">
                        温度
                      </label>
                      <span className="text-xs text-cyber-400 font-mono">{editing.temperature}</span>
                    </div>
                    <input
                      type="range"
                      min="0"
                      max="2"
                      step="0.1"
                      value={editing.temperature || 0.7}
                      onChange={(e) =>
                        setEditing({ ...editing, temperature: parseFloat(e.target.value) })
                      }
                      className="w-full"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-xs text-white/40 tracking-wider uppercase font-medium">
                      最大 Token
                    </label>
                    <input
                      type="number"
                      value={editing.max_tokens || 4096}
                      onChange={(e) =>
                        setEditing({ ...editing, max_tokens: parseInt(e.target.value) })
                      }
                      className="w-full glass-input rounded-lg px-3 py-2.5 text-sm text-white/80
                                 font-mono focus:outline-none"
                    />
                  </div>
                </div>

                {/* Enabled tools */}
                <div className="space-y-2">
                  <label className="text-xs text-white/40 tracking-wider uppercase font-medium">
                    启用工具
                  </label>
                  <div className="space-y-1.5">
                    {tools.map((tool) => (
                      <label
                        key={tool.name}
                        className="flex items-start gap-3 p-3 rounded-lg
                                   bg-surface-700/30 border border-white/[0.04]
                                   hover:bg-surface-700/50 hover:border-white/[0.08]
                                   cursor-pointer transition-all duration-200"
                      >
                        <input
                          type="checkbox"
                          checked={(editing.enabled_tools || []).includes(tool.name)}
                          onChange={() => toggleTool(tool.name)}
                          className="mt-0.5"
                        />
                        <div>
                          <p className="text-sm font-medium text-white/70">{tool.name}</p>
                          <p className="text-xs text-white/20 mt-0.5">{tool.description}</p>
                        </div>
                      </label>
                    ))}
                  </div>
                </div>

                {/* RAG params */}
                <div className="grid grid-cols-2 gap-5">
                  <div className="space-y-1.5">
                    <label className="text-xs text-white/40 tracking-wider uppercase font-medium">
                      RAG 检索数量 (K)
                    </label>
                    <input
                      type="number"
                      min="1"
                      max="20"
                      value={editing.rag_top_k || 4}
                      onChange={(e) =>
                        setEditing({ ...editing, rag_top_k: parseInt(e.target.value) })
                      }
                      className="w-full glass-input rounded-lg px-3 py-2.5 text-sm text-white/80
                                 font-mono focus:outline-none"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between">
                      <label className="text-xs text-white/40 tracking-wider uppercase font-medium">
                        相似度阈值
                      </label>
                      <span className="text-xs text-cyber-400 font-mono">
                        {editing.rag_similarity_threshold}
                      </span>
                    </div>
                    <input
                      type="range"
                      min="0"
                      max="1"
                      step="0.05"
                      value={editing.rag_similarity_threshold || 0.5}
                      onChange={(e) =>
                        setEditing({
                          ...editing,
                          rag_similarity_threshold: parseFloat(e.target.value),
                        })
                      }
                      className="w-full"
                    />
                  </div>
                </div>

                {/* Save button */}
                <div className="pt-2">
                  <button
                    onClick={handleSave}
                    className="flex items-center gap-2 rounded-lg px-6 py-2.5 text-sm font-medium
                               bg-gradient-to-r from-cyber-500 to-cyber-600
                               hover:from-cyber-400 hover:to-cyber-500
                               text-white shadow-glow-cyan hover:shadow-glow-strong
                               transition-all duration-300"
                  >
                    <Save size={15} />
                    保存设置
                  </button>
                </div>
              </>
            ) : (
              <div className="flex flex-col items-center justify-center h-full gap-3">
                <Cpu size={36} className="text-white/10" />
                <p className="text-sm text-white/20">选择一个 Agent 进行编辑</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
