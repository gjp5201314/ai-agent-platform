import { useState, useEffect } from "react";
import { Plus, Trash2, Cpu, Save } from "lucide-react";
import { api } from "../api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
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
        allow_delegation: true,
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
    <Dialog open onOpenChange={() => onClose()}>
      <DialogContent className="!max-w-5xl w-[90vw] h-[88vh] p-0 gap-0 flex flex-col bg-white border border-gray-200">
        <DialogHeader className="px-6 py-4 border-b border-gray-200 flex-shrink-0">
          <DialogTitle className="text-lg text-gray-800">Agent 设置</DialogTitle>
          <DialogDescription className="text-xs text-gray-400">
            管理你的 AI Agent 配置：系统提示词、工具、参数
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 grid grid-cols-[220px_1fr] min-h-0">
          {/* Agent list sidebar */}
          <div className="border-r border-gray-200 flex flex-col min-h-0 bg-gray-50/50">
            <div className="px-4 py-3 border-b border-gray-200 flex-shrink-0">
              <p className="text-xs text-gray-400 font-medium">Agent 列表</p>
            </div>
            <ScrollArea className="flex-1">
              <div className="p-2 space-y-1">
                {agents.map((agent) => (
                  <div
                    key={agent.id}
                    onClick={() => handleSelect(agent)}
                    className={`group flex items-center gap-2 rounded-md px-3 py-2.5 cursor-pointer text-sm
                               transition-colors ${
                      selectedId === agent.id
                        ? "bg-ds-50 text-ds-600 border border-ds-200"
                        : "text-gray-600 hover:text-gray-800 hover:bg-gray-100 border border-transparent"
                    }`}
                  >
                    <Cpu size={13} className="flex-shrink-0" />
                    <span className="flex-1 truncate text-xs">{agent.name}</span>
                    {agent.is_default ? (
                      <span className="text-[9px] px-1.5 py-0.5 rounded-sm
                                       bg-emerald-50 text-emerald-600
                                       border border-emerald-200 font-medium">
                        默认
                      </span>
                    ) : (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDelete(agent.id);
                        }}
                        className="opacity-0 group-hover:opacity-100 text-gray-300
                                   hover:text-red-500 transition-all p-0.5"
                      >
                        <Trash2 size={12} />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </ScrollArea>
            <div className="p-2 border-t border-gray-200 flex-shrink-0">
              <Button
                variant="secondary"
                size="sm"
                onClick={handleNew}
                className="w-full gap-2 text-xs bg-white border-gray-200 hover:bg-gray-50"
              >
                <Plus size={13} />
                新建 Agent
              </Button>
            </div>
          </div>

          {/* Editor panel */}
          <div className="flex flex-col min-h-0">
            {selectedId && editing ? (
              <>
                <div className="px-6 py-3 border-b border-gray-200 flex items-center justify-between flex-shrink-0">
                  <div>
                    <p className="text-xs text-gray-400 font-medium">编辑</p>
                    <p className="text-sm font-medium mt-0.5 text-gray-800">{editing.name || "(未命名)"}</p>
                  </div>
                  <Button onClick={handleSave} size="sm" className="gap-2 !bg-ds-500 hover:!bg-ds-600 !text-white border-0 shadow-sm font-medium">
                    <Save size={13} className="!text-white" />
                    保存设置
                  </Button>
                </div>

                <ScrollArea className="flex-1">
                  <div className="p-6 space-y-6">
                    {/* Name + Description */}
                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <Label className="text-xs text-gray-400 font-medium">名称</Label>
                        <Input
                          value={editing.name || ""}
                          onChange={(e) => setEditing({ ...editing, name: e.target.value })}
                          placeholder="Agent 名称"
                          className="bg-white border-gray-200"
                        />
                      </div>
                      <div className="space-y-2">
                        <Label className="text-xs text-gray-400 font-medium">描述</Label>
                        <Input
                          value={editing.description || ""}
                          onChange={(e) => setEditing({ ...editing, description: e.target.value })}
                          placeholder="简要描述 Agent 的功能"
                          className="bg-white border-gray-200"
                        />
                      </div>
                    </div>

                    {/* System prompt */}
                    <div className="space-y-2">
                      <Label className="text-xs text-gray-400 font-medium">系统提示词</Label>
                      <Textarea
                        value={editing.system_prompt || ""}
                        onChange={(e) => setEditing({ ...editing, system_prompt: e.target.value })}
                        rows={4}
                        className="font-mono text-xs bg-white border-gray-200"
                        placeholder="设定 Agent 的行为..."
                      />
                    </div>

                    <Separator className="bg-gray-200" />

                    {/* Temperature + Max Tokens */}
                    <div className="grid grid-cols-2 gap-6">
                      <div className="space-y-3">
                        <div className="flex items-center justify-between">
                          <Label className="text-xs text-gray-400 font-medium">温度</Label>
                          <span className="text-xs text-ds-500 font-mono tabular-nums font-medium">
                            {(editing.temperature ?? 0.7).toFixed(1)}
                          </span>
                        </div>
                        <Slider
                          min={0}
                          max={2}
                          step={0.1}
                          value={[editing.temperature ?? 0.7]}
                          onValueChange={(value) =>
                            setEditing({ ...editing, temperature: Array.isArray(value) ? value[0] : value })
                          }
                        />
                        <div className="flex justify-between text-[10px] text-gray-400">
                          <span>精确</span>
                          <span>创意</span>
                        </div>
                      </div>
                      <div className="space-y-2">
                        <Label className="text-xs text-gray-400 font-medium">最大 Token</Label>
                        <Input
                          type="number"
                          value={editing.max_tokens || 4096}
                          onChange={(e) =>
                            setEditing({ ...editing, max_tokens: parseInt(e.target.value) || 4096 })
                          }
                          className="font-mono text-sm bg-white border-gray-200"
                        />
                        <p className="text-[10px] text-gray-400">单次回复的最大 token 数</p>
                      </div>
                    </div>

                    <Separator className="bg-gray-200" />

                    {/* Enabled tools */}
                    <div className="space-y-3">
                      <div className="flex items-center justify-between">
                        <Label className="text-xs text-gray-400 font-medium">启用工具</Label>
                        <span className="text-[10px] text-gray-400">
                          {(editing.enabled_tools || []).length} / {tools.length} 已启用
                        </span>
                      </div>
                      <div className="grid grid-cols-2 gap-2">
                        {tools.map((tool) => (
                          <div
                            key={tool.name}
                            className="flex items-center justify-between rounded-lg border border-gray-200 bg-white px-3 py-2.5
                                       hover:bg-gray-50 transition-colors"
                          >
                            <div className="flex-1 min-w-0 mr-3">
                              <p className="text-sm font-medium text-gray-700 truncate">{tool.name}</p>
                              <p className="text-[11px] text-gray-400 truncate mt-0.5">
                                {tool.description}
                              </p>
                            </div>
                            <Switch
                              checked={(editing.enabled_tools || []).includes(tool.name)}
                              onCheckedChange={() => toggleTool(tool.name)}
                            />
                          </div>
                        ))}
                      </div>
                    </div>

                    <Separator className="bg-gray-200" />

                    {/* Agent Delegation */}
                    <div className="flex items-center justify-between rounded-lg border border-gray-200 bg-white px-4 py-3">
                      <div className="flex-1 min-w-0 mr-3">
                        <p className="text-sm font-medium text-gray-700">允许委托</p>
                        <p className="text-[11px] text-gray-400 mt-0.5">
                          允许其他 Agent 通过 delegate_to_agent 工具调用此 Agent
                        </p>
                      </div>
                      <Switch
                        checked={editing.allow_delegation !== false}
                        onCheckedChange={(checked) =>
                          setEditing({ ...editing, allow_delegation: checked })
                        }
                      />
                    </div>

                    <Separator className="bg-gray-200" />

                    {/* RAG params */}
                    <div className="grid grid-cols-2 gap-6">
                      <div className="space-y-2">
                        <Label className="text-xs text-gray-400 font-medium">
                          RAG 检索数量 (K)
                        </Label>
                        <Input
                          type="number"
                          min={1}
                          max={20}
                          value={editing.rag_top_k || 4}
                          onChange={(e) =>
                            setEditing({ ...editing, rag_top_k: parseInt(e.target.value) || 4 })
                          }
                          className="font-mono text-sm bg-white border-gray-200"
                        />
                        <p className="text-[10px] text-gray-400">检索相关文档的最大数量</p>
                      </div>
                      <div className="space-y-3">
                        <div className="flex items-center justify-between">
                          <Label className="text-xs text-gray-400 font-medium">相似度阈值</Label>
                          <span className="text-xs text-ds-500 font-mono tabular-nums font-medium">
                            {(editing.rag_similarity_threshold ?? 0.5).toFixed(2)}
                          </span>
                        </div>
                        <Slider
                          min={0}
                          max={1}
                          step={0.05}
                          value={[editing.rag_similarity_threshold ?? 0.5]}
                          onValueChange={(value) =>
                            setEditing({
                              ...editing,
                              rag_similarity_threshold: Array.isArray(value) ? value[0] : value,
                            })
                          }
                        />
                        <div className="flex justify-between text-[10px] text-gray-400">
                          <span>宽松</span>
                          <span>严格</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </ScrollArea>
              </>
            ) : (
              <div className="flex-1 flex flex-col items-center justify-center gap-3 text-gray-400">
                <Cpu size={40} className="opacity-15" />
                <p className="text-sm">选择一个 Agent 进行编辑</p>
                <p className="text-xs opacity-60">或点击左侧"新建 Agent"创建</p>
              </div>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
