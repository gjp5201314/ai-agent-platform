import { useState, useEffect, useRef } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { api } from "../api/client";
import { uploadFile } from "../lib/upload";
import { ProgressList, type FileProgress } from "./ProgressBar";
import { toast } from "sonner";
import { LayoutDashboard, Database, Cpu, BookOpen, ArrowLeft, RefreshCw, Upload, Trash2, Check, Zap } from "lucide-react";

const API_BASE = "/api/v1";

/* ================================================================
   Types
   ================================================================ */
interface Stats {
  total_conversations: number;
  total_messages: number;
  total_documents: number;
  total_chunks: number;
  total_storage_mb: number;
  total_agents: number;
  conversations_today: number;
  messages_today: number;
}
interface LLMProvider {
  id: string; name: string; enabled: boolean;
  models: string[]; default_model: string; api_key_set: boolean; base_url: string;
}
interface LLMConfig { providers: LLMProvider[]; default_provider: string; active_model: string; }

interface SandboxStatus {
  reachable: boolean;
  latency_ms: number;
  deps_count: number;
  files_count: number;
}

type Tab = "dashboard" | "rag" | "llm" | "tech";

const NAV_ITEMS: { key: Tab; label: string; icon: React.ReactNode; path: string }[] = [
  { key: "dashboard", label: "仪表盘", icon: <LayoutDashboard size={18} />, path: "/admin/dashboard" },
  { key: "rag", label: "知识库管理", icon: <Database size={18} />, path: "/admin/rag" },
  { key: "llm", label: "大模型配置", icon: <Cpu size={18} />, path: "/admin/llm" },
  { key: "tech", label: "技术解析", icon: <BookOpen size={18} />, path: "/admin/tech" },
];

/* ================================================================
   Main Component
   ================================================================ */
export function AdminPage({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate();
  const location = useLocation();

  // Derive active tab from URL path
  const activeTab: Tab = (() => {
    if (location.pathname.includes("/admin/rag")) return "rag";
    if (location.pathname.includes("/admin/llm")) return "llm";
    if (location.pathname.includes("/admin/tech")) return "tech";
    return "dashboard";
  })();

  const [loading, setLoading] = useState(false);
  const [stats, setStats] = useState<Stats | null>(null);
  const [llmConfig, setLlmConfig] = useState<LLMConfig | null>(null);
  const [documents, setDocuments] = useState<any[]>([]);
  const [sandboxStatus, setSandboxStatus] = useState<SandboxStatus | null>(null);

  const loadAll = async () => {
    setLoading(true);
    try {
      const [s, l, d] = await Promise.all([api.adminDashboard(), api.adminLlmList(), api.adminRagDocuments()]);
      setStats(s); setLlmConfig(l); setDocuments(d);
    } catch { /* silent */ }
    // Sandbox health — non-blocking, can fail gracefully
    try {
      const ss = await api.sandboxStats();
      setSandboxStatus({
        reachable: ss.health.reachable,
        latency_ms: ss.health.latency_ms,
        deps_count: ss.dependencies.count,
        files_count: ss.files.count,
      });
    } catch {
      setSandboxStatus({ reachable: false, latency_ms: 0, deps_count: 0, files_count: 0 });
    }
    setLoading(false);
  };
  useEffect(() => { loadAll(); }, []);

  const maxMsg = stats ? Math.max(stats.total_messages, 1) : 1;

  // Tab navigation handler
  const goToTab = (tab: Tab) => {
    const item = NAV_ITEMS.find(n => n.key === tab);
    if (item) navigate(item.path);
  };

  return (
    <div className="fixed inset-0 z-[1000] bg-gray-50 flex font-sans">
      {/* Sidebar */}
      <div className="w-[220px] bg-white border-r border-gray-200 flex flex-col flex-shrink-0">
        <div className="px-5 py-6 border-b border-gray-200">
          <div className="text-base font-bold text-ds-500">AI Agent</div>
          <div className="text-xs text-gray-400 mt-0.5">管理后台</div>
        </div>
        <div className="flex-1 p-2.5">
          {NAV_ITEMS.map((item) => {
            const active = activeTab === item.key;
            return (
              <button
                key={item.key}
                onClick={() => goToTab(item.key)}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors mb-0.5 ${
                  active
                    ? "bg-ds-50 text-ds-600"
                    : "text-gray-500 hover:text-gray-700 hover:bg-gray-50"
                }`}
              >
                <span className={active ? "text-ds-500" : "text-gray-400"}>{item.icon}</span>
                {item.label}
              </button>
            );
          })}
        </div>
        <div className="p-3 border-t border-gray-200">
          <button
            onClick={onClose}
            className="w-full flex items-center gap-2 px-3 py-2.5 rounded-lg text-sm text-gray-400
                       hover:text-red-500 hover:bg-red-50 transition-colors font-medium"
          >
            <ArrowLeft size={16} />
            返回前台
          </button>
        </div>
      </div>

      {/* Main */}
      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="h-14 flex items-center justify-between px-7 bg-white border-b border-gray-200 flex-shrink-0">
          <div className="flex items-center gap-2.5">
            <span className="text-ds-500">{NAV_ITEMS.find((n) => n.key === activeTab)?.icon}</span>
            <span className="text-sm font-semibold text-gray-800">
              {NAV_ITEMS.find((n) => n.key === activeTab)?.label}
            </span>
          </div>
          <div className="flex items-center gap-3">
            {loading && <span className="text-xs text-ds-500">加载中...</span>}
            <button
              onClick={loadAll}
              className="flex items-center gap-1 text-xs text-gray-400 hover:text-ds-500 transition-colors"
            >
              <RefreshCw size={13} /> 刷新
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-auto p-8">
          {activeTab === "dashboard" && stats && <Dashboard stats={stats} llmConfig={llmConfig} sandboxStatus={sandboxStatus} maxMsg={maxMsg} />}
          {activeTab === "rag" && <RagPanel documents={documents} onRefresh={loadAll} />}
          {activeTab === "llm" && llmConfig && <LlmPanel llmConfig={llmConfig} />}
          {activeTab === "tech" && <TechPanel />}
        </div>
      </div>
    </div>
  );
}

/* ================================================================
   Dashboard (unchanged)
   ================================================================ */
function Dashboard({ stats, llmConfig, sandboxStatus, maxMsg }: { stats: Stats; llmConfig: LLMConfig | null; sandboxStatus: SandboxStatus | null; maxMsg: number }) {
  const cards = [
    { label: "对话总数", value: stats.total_conversations, sub: `今日 +${stats.conversations_today}`, color: "text-ds-500", bg: "bg-ds-50", icon: "💬" },
    { label: "消息总数", value: stats.total_messages, sub: `今日 +${stats.messages_today}`, color: "text-purple-500", bg: "bg-purple-50", icon: "📨" },
    { label: "知识库文档", value: stats.total_documents, sub: `${stats.total_chunks} 个分块`, color: "text-emerald-500", bg: "bg-emerald-50", icon: "📄" },
    { label: "存储空间", value: `${stats.total_storage_mb} MB`, sub: `${stats.total_agents} 个 Agent`, color: "text-amber-500", bg: "bg-amber-50", icon: "💾" },
  ];

  return (
    <div className="space-y-8">
      <div className="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-4">
        {cards.map((c) => (
          <div key={c.label} className="bg-white rounded-xl border border-gray-200 p-5 hover:border-gray-300 hover:shadow-sm transition-all relative overflow-hidden">
            <span className="absolute top-4 right-4 text-xl opacity-40">{c.icon}</span>
            <div className="text-xs text-gray-400 font-medium mb-1.5">{c.label}</div>
            <div className="text-2xl font-bold text-gray-800">{c.value}</div>
            <div className={`inline-flex items-center gap-1.5 text-xs font-medium mt-2 px-2 py-0.5 rounded-full ${c.bg} ${c.color}`}>
              <span className={`w-1.5 h-1.5 rounded-full ${c.color.replace("text-", "bg-")}`} /> {c.sub}
            </div>
          </div>
        ))}
      </div>
      <div className="grid grid-cols-2 gap-4">
        <UsageBar label="消息活跃度" pct={Math.min(100, (stats.messages_today / Math.max(maxMsg / 10, 1)) * 100)} color="#4D6BFE" />
        <UsageBar label="文档存储率" pct={Math.min(100, stats.total_storage_mb * 5)} color="#10b981" />
      </div>
      <div>
        <div className="text-sm font-semibold text-gray-800 mb-4">LLM 提供商状态</div>
        <div className="grid grid-cols-[repeat(auto-fill,minmax(240px,1fr))] gap-3.5">
          {(llmConfig?.providers || []).map((p) => (
            <div key={p.id} className={`bg-white rounded-xl border p-5 transition-all relative overflow-hidden ${p.enabled ? "border-gray-200 hover:border-gray-300" : "border-gray-100 opacity-60"}`}>
              <div className="absolute top-0 left-0 right-0 h-0.5" style={{ background: p.enabled ? "linear-gradient(90deg, #4D6BFE, transparent)" : "#f3f4f6" }} />
              <div className="flex items-center justify-between mb-2.5">
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full" style={{ background: p.enabled ? "#10b981" : "#d1d5db" }} />
                  <span className="text-sm font-semibold text-gray-800">{p.name}</span>
                </div>
                <span className={`inline-flex text-[10px] px-2 py-0.5 rounded-full font-medium ${p.enabled ? "bg-emerald-50 text-emerald-600 border border-emerald-200" : "bg-gray-100 text-gray-400 border border-gray-200"}`}>
                  {p.enabled ? "已启用" : "未配置"}
                </span>
              </div>
              <div className="text-xs text-gray-500 space-y-1">
                <div>默认模型 <span className="text-gray-700">{p.default_model || "—"}</span></div>
                <div>API Key <span className={p.api_key_set ? "text-emerald-500" : "text-red-500"}>{p.api_key_set ? "已配置" : "未配置"}</span></div>
              </div>
              {p.enabled && (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {p.models.slice(0, 4).map((m) => (
                    <span key={m} className={`inline-flex text-[10px] px-2 py-0.5 rounded-full font-medium ${m === p.default_model ? "bg-ds-50 text-ds-600 border border-ds-200" : "bg-gray-50 text-gray-500 border border-gray-200"}`}>{m}</span>
                  ))}
                  {p.models.length > 4 && <span className="inline-flex text-[10px] px-2 py-0.5 rounded-full bg-gray-50 text-gray-400 border border-gray-200">+{p.models.length - 4}</span>}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Sandbox 沙盒状态 */}
      <div>
        <div className="text-sm font-semibold text-gray-800 mb-4">DifySandbox 代码沙盒</div>
        <div className="grid grid-cols-[repeat(auto-fill,minmax(240px,1fr))] gap-3.5">
          {/* Sandbox health card */}
          <div className={`bg-white rounded-xl border p-5 transition-all relative overflow-hidden ${sandboxStatus?.reachable ? "border-gray-200 hover:border-gray-300" : "border-red-200"}`}>
            <div className="absolute top-0 left-0 right-0 h-0.5" style={{ background: sandboxStatus?.reachable ? "linear-gradient(90deg, #10b981, transparent)" : "linear-gradient(90deg, #ef4444, transparent)" }} />
            <div className="flex items-center justify-between mb-2.5">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full" style={{ background: sandboxStatus?.reachable ? "#10b981" : "#ef4444" }} />
                <span className="text-sm font-semibold text-gray-800">沙盒服务</span>
              </div>
              <span className={`inline-flex text-[10px] px-2 py-0.5 rounded-full font-medium ${
                sandboxStatus?.reachable
                  ? "bg-emerald-50 text-emerald-600 border border-emerald-200"
                  : "bg-red-50 text-red-600 border border-red-200"
              }`}>
                {sandboxStatus?.reachable ? "运行中" : "不可达"}
              </span>
            </div>
            <div className="text-xs text-gray-500 space-y-1">
              <div>延迟 <span className={sandboxStatus?.reachable ? "text-emerald-600 font-medium" : "text-gray-700"}>
                {sandboxStatus?.reachable ? `${sandboxStatus.latency_ms} ms` : "—"}
              </span></div>
              <div>已安装包 <span className="text-gray-700 font-medium">{sandboxStatus?.deps_count ?? "—"}</span></div>
              <div>沙盒文件 <span className="text-gray-700 font-medium">{sandboxStatus?.files_count ?? "—"}</span></div>
            </div>
          </div>

          {/* Sandbox capability cards */}
          <SandboxCapCard icon="🐍" title="Python 3" desc="数据分析、计算、绘图" />
          <SandboxCapCard icon="🟨" title="JavaScript" desc="Node.js 脚本执行" />
          <SandboxCapCard icon="⬛" title="Bash Shell" desc="终端命令执行" />
        </div>
      </div>
    </div>
  );
}

function SandboxCapCard({ icon, title, desc }: { icon: string; title: string; desc: string }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 hover:border-gray-300 transition-all">
      <div className="flex items-center gap-3">
        <span className="text-2xl">{icon}</span>
        <div>
          <div className="text-sm font-semibold text-gray-800">{title}</div>
          <div className="text-xs text-gray-400 mt-0.5">{desc}</div>
        </div>
      </div>
    </div>
  );
}

function UsageBar({ label, pct, color }: { label: string; pct: number; color: string }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <div className="flex justify-between mb-2">
        <span className="text-xs text-gray-400 font-medium">{label}</span>
        <span className="text-xs font-semibold" style={{ color }}>{Math.round(pct)}%</span>
      </div>
      <div className="h-1.5 rounded-full bg-gray-100 overflow-hidden">
        <div className="h-full rounded-full transition-all duration-800" style={{ width: `${pct}%`, background: color }} />
      </div>
    </div>
  );
}

/* ================================================================
   RAG Panel — with progress bars
   ================================================================ */
function RagPanel({ documents, onRefresh }: { documents: any[]; onRefresh: () => void }) {
  const [uploading, setUploading] = useState(false);
  const [fileProgresses, setFileProgresses] = useState<FileProgress[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleUpload = async (files: FileList | null) => {
    if (!files?.length) return;
    const fileArr = Array.from(files);

    // Initialize progress state for all files
    const initial: FileProgress[] = fileArr.map(f => ({
      filename: f.name,
      percent: 0,
      state: "uploading" as const,
    }));
    setFileProgresses(initial);
    setUploading(true);

    for (let i = 0; i < fileArr.length; i++) {
      try {
        await uploadFile(
          `${API_BASE}/admin/rag/upload`,
          fileArr[i],
          (p) => {
            setFileProgresses(prev => {
              const next = [...prev];
              next[i] = { ...next[i], percent: p.percent, state: "uploading" };
              return next;
            });
          },
        );
        // Mark as success
        setFileProgresses(prev => {
          const next = [...prev];
          next[i] = { ...next[i], percent: 100, state: "success" };
          return next;
        });
      } catch (e: any) {
        setFileProgresses(prev => {
          const next = [...prev];
          next[i] = { ...next[i], percent: 100, state: "error", error: e.message };
          return next;
        });
      }
    }

    setUploading(false);
    if (fileRef.current) fileRef.current.value = "";
    onRefresh();
    // Clear progress after 3 seconds
    setTimeout(() => setFileProgresses([]), 3000);
  };

  const handleDelete = async (id: string, name: string) => {
    if (!confirm(`确定删除"${name}"？`)) return;
    try { await api.adminRagDelete(id); onRefresh(); } catch (e: any) { alert("删除失败: " + e.message); }
  };

  return (
    <div className="space-y-5">
      <div className="flex justify-between items-center">
        <div>
          <div className="text-sm font-semibold text-gray-800">管理员知识库文档</div>
          <div className="text-xs text-gray-400 mt-1">
            共 {documents.length} 个文档 — 仅供「知识库助手」Agent 检索
          </div>
        </div>
        <div className="flex gap-2.5">
          <input ref={fileRef} type="file" multiple accept=".pdf,.docx,.txt,.md"
            onChange={(e) => handleUpload(e.target.files)} className="hidden" />
          <button
            onClick={() => fileRef.current?.click()}
            disabled={uploading}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-semibold
                       bg-ds-500 text-white hover:bg-ds-600 transition-colors shadow-sm disabled:opacity-50"
          >
            <Upload size={13} />
            {uploading ? "上传中..." : "上传文档"}
          </button>
        </div>
      </div>

      {/* Progress bars */}
      {fileProgresses.length > 0 && <ProgressList files={fileProgresses} />}

      {/* Table */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="grid grid-cols-[2fr_0.6fr_0.6fr_0.6fr_0.8fr_1fr_0.5fr] gap-3 px-4 py-3
                        text-[11px] text-gray-400 font-medium border-b border-gray-100 uppercase tracking-wider">
          <span>文件名</span><span>类型</span><span>大小</span><span>分块</span><span>状态</span><span>上传时间</span><span>操作</span>
        </div>

        {documents.length === 0 ? (
          <div className="text-center py-16 text-gray-400 text-sm">暂无管理端文档，点击右上角上传</div>
        ) : (
          documents.map((doc) => (
            <div key={doc.id} className="grid grid-cols-[2fr_0.6fr_0.6fr_0.6fr_0.8fr_1fr_0.5fr] gap-3 px-4 py-3.5 text-sm text-gray-600 items-center border-b border-gray-50 hover:bg-gray-50/50 transition-colors">
              <span className="text-gray-800 font-medium truncate">{doc.filename}</span>
              <span className="inline-flex text-[10px] px-2 py-0.5 rounded-full bg-ds-50 text-ds-600 border border-ds-200 font-medium w-fit">{doc.file_type}</span>
              <span>{(doc.file_size / 1024).toFixed(1)} KB</span>
              <span>{doc.chunk_count}</span>
              <span className="inline-flex items-center gap-1.5 text-xs">
                <span className="w-1.5 h-1.5 rounded-full" style={{ background: doc.status === "ready" ? "#10b981" : "#f59e0b" }} />
                {doc.status === "ready" ? "就绪" : doc.status}
              </span>
              <span className="text-xs text-gray-400">
                {new Date(doc.created_at).toLocaleDateString("zh-CN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
              </span>
              <button onClick={() => handleDelete(doc.id, doc.filename)} className="text-gray-300 hover:text-red-500 transition-colors text-xs font-medium justify-self-center">删除</button>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

/* ================================================================
   LLM Panel (unchanged)
   ================================================================ */
function LlmPanel({ llmConfig }: { llmConfig: LLMConfig }) {
  const [provider, setProvider] = useState(llmConfig.default_provider);
  const [model, setModel] = useState(llmConfig.active_model || "");
  const [customModel, setCustomModel] = useState("");
  const [showCustom, setShowCustom] = useState(false);
  const [saving, setSaving] = useState(false);
  const [activeProvider, setActiveProvider] = useState(llmConfig.default_provider);
  const [activeModel, setActiveModel] = useState(llmConfig.active_model || "");

  const currentProvider = llmConfig.providers.find(p => p.id === provider);
  const models = currentProvider?.models || [];
  const effectiveModel = showCustom ? customModel : model;
  const isActive = provider === activeProvider && effectiveModel === activeModel;

  useEffect(() => {
    if (currentProvider && !models.includes(model) && !showCustom) {
      setModel(currentProvider.default_model || models[0] || "");
    }
  }, [provider, currentProvider, models, model, showCustom]);

  const handleSave = async () => {
    const finalModel = showCustom ? customModel.trim() : model;
    if (!provider || !finalModel) return;
    setSaving(true);
    try {
      await api.adminLlmUpdate(provider, { model: finalModel });
      setActiveProvider(provider);
      setActiveModel(finalModel);
      if (showCustom) setCustomModel("");
      setShowCustom(false);
      toast.success(`已切换至 ${finalModel}`, { description: `${currentProvider?.name} 现已生效，无需刷新` });
    } catch (e: any) {
      toast.error("切换失败", { description: e?.message || String(e) });
    }
    setSaving(false);
  };

  return (
    <div className="space-y-6">
      <div className="bg-gradient-to-r from-ds-50 to-indigo-50 rounded-xl border border-ds-100 p-5">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-ds-100 flex items-center justify-center"><Zap size={18} className="text-ds-500" /></div>
          <div>
            <div className="text-xs text-ds-400 font-medium">当前激活</div>
            <div className="text-sm font-bold text-ds-600">{activeProvider} / {activeModel || "未设置"}</div>
          </div>
        </div>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-5">
        <div>
          <label className="text-[11px] text-gray-400 font-medium mb-2 block">选择提供商</label>
          <div className="grid grid-cols-3 gap-2">
            {llmConfig.providers.map((p) => (
              <button key={p.id} onClick={() => { p.enabled && setProvider(p.id); setShowCustom(false); }} disabled={!p.enabled || saving}
                className={`relative px-4 py-3 rounded-lg border text-left transition-all ${!p.enabled ? "opacity-40 cursor-not-allowed bg-gray-50 border-gray-100" : provider === p.id ? "border-ds-300 bg-ds-50 ring-1 ring-ds-200" : "border-gray-200 bg-white hover:border-gray-300"}`}>
                {provider === p.id && <Check size={14} className="absolute top-2 right-2 text-ds-500" />}
                <div className="text-xs font-semibold text-gray-700">{p.name}</div>
                <div className="text-[10px] text-gray-400 mt-0.5">{p.models.length} 个模型</div>
              </button>
            ))}
          </div>
        </div>

        <div>
          <label className="text-[11px] text-gray-400 font-medium mb-2 block">选择模型 {currentProvider ? `(${currentProvider.name})` : ""}</label>
          <div className="flex flex-wrap gap-2">
            {models.map((m) => (
              <button key={m} onClick={() => { setModel(m); setShowCustom(false); }} disabled={saving}
                className={`px-3.5 py-2 rounded-lg border text-sm font-medium transition-all ${model === m && !showCustom ? "border-ds-300 bg-ds-50 text-ds-600 ring-1 ring-ds-200" : "border-gray-200 bg-white text-gray-600 hover:border-gray-300"} ${saving ? "opacity-50 cursor-wait" : ""}`}>{m}</button>
            ))}
            <button onClick={() => { setShowCustom(true); setCustomModel(""); }} disabled={saving}
              className={`px-3.5 py-2 rounded-lg border text-sm font-medium transition-all ${showCustom ? "border-ds-300 bg-ds-50 text-ds-600 ring-1 ring-ds-200" : "border-dashed border-gray-300 bg-white text-gray-400 hover:border-gray-400 hover:text-gray-500"} ${saving ? "opacity-50 cursor-wait" : ""}`}>+ 自定义</button>
          </div>
        </div>

        {showCustom && (
          <div className="animate-in">
            <label className="text-[11px] text-gray-400 font-medium mb-2 block">自定义模型名称</label>
            <input type="text" value={customModel} onChange={(e) => setCustomModel(e.target.value)}
              placeholder="例如: qwen-flash, gpt-4o, deepseek-v3..." disabled={saving}
              className="w-full px-4 py-2.5 rounded-lg border border-ds-200 bg-white text-sm text-gray-700 placeholder:text-gray-300 focus:outline-none focus:ring-2 focus:ring-ds-200 disabled:opacity-50" autoFocus
              onKeyDown={(e) => e.key === "Enter" && handleSave()} />
          </div>
        )}

        <div className="pt-3 border-t border-gray-100 flex items-center justify-between">
          <div className="text-[11px] text-gray-400">{isActive ? "已是最新配置" : `将切换至 ${provider} / ${effectiveModel}`}</div>
          <button onClick={handleSave} disabled={isActive || saving || !provider || !effectiveModel}
            className={`inline-flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-semibold transition-all ${isActive ? "bg-gray-100 text-gray-400 cursor-not-allowed" : "bg-ds-500 text-white hover:bg-ds-600 shadow-sm shadow-ds-200"} ${saving ? "opacity-70 cursor-wait" : ""}`}>
            <Zap size={14} />
            {saving ? "切换中..." : isActive ? "已激活" : "确认切换"}
          </button>
        </div>
      </div>

      <div>
        <div className="text-sm font-semibold text-gray-800 mb-4">提供商详情</div>
        <div className="grid grid-cols-1 gap-4">
          {llmConfig.providers.map((p) => <ProviderCard key={p.id} p={p} />)}
        </div>
      </div>
    </div>
  );
}

function ProviderCard({ p }: { p: LLMProvider }) {
  return (
    <div className={`bg-white rounded-xl border p-5 flex items-center gap-4 ${p.enabled ? "border-gray-200" : "border-gray-100 opacity-50"}`}>
      <div className="flex-shrink-0"><span className="w-3 h-3 rounded-full inline-block" style={{ background: p.enabled ? "#4D6BFE" : "#d1d5db" }} /></div>
      <div className="flex-1 min-w-0">
        <div className="text-sm font-semibold text-gray-800">{p.name}</div>
        <div className="text-[11px] text-gray-400 mt-0.5">{p.enabled ? `${p.models.length} 个模型可用 · ${p.base_url}` : "未配置 API Key"}</div>
      </div>
      <div className="flex-shrink-0">
        <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${p.enabled ? "bg-emerald-50 text-emerald-600 border border-emerald-200" : "bg-gray-100 text-gray-400 border border-gray-200"}`}>{p.enabled ? "可用" : "未启用"}</span>
      </div>
    </div>
  );
}

/* ================================================================
   Tech Panel (unchanged but updates Mem0 description)
   ================================================================ */
function TechPanel() {
  const sections = [
    {
      title: "LangGraph Agent 引擎", color: "#4D6BFE", content: "基于 LangGraph 构建的有状态 Agent 图执行引擎。",
      items: [
        ["图状态管理", "AgentState TypedDict 统一管理消息流、工具启用列表、RAG 上下文、迭代计数"],
        ["节点定义", "agent_node（LLM 推理）、rag_node（知识库检索）、tool_node（工具执行）"],
        ["路由逻辑", "should_continue 条件边：ToolMessage → tool_node 循环调用，AIMessage → END 终止"],
        ["迭代保护", "最大迭代 8 轮硬上限，防止 Agent 无限循环（guardrail pattern）"],
      ],
    },
    {
      title: "RAG 混合检索", color: "#10b981", content: "语义向量检索 + BM25 关键词检索双路融合，通过 RRF 算法联合排序。",
      items: [
        ["语义检索", "DashScope text-embedding-v3 (1024d) → pgvector HNSW 索引 → cosine_distance 排序"],
        ["关键词检索 (BM25)", "PostgreSQL tsvector + GIN 倒排索引 → ts_rank 排序，CJK 逐字分词"],
        ["RRF 融合", "Reciprocal Rank Fusion (k=60)：两路结果加权合并去重"],
        ["文档处理", "PDF (pdfplumber) / DOCX (python-docx) → 语义分块 → 批量向量化"],
        ["相似度阈值", "Agent 配置 rag_similarity_threshold (默认 0.5) 过滤低质量结果"],
      ],
    },
    {
      title: "SSE 流式输出", color: "#818cf8", content: "Server-Sent Events 逐 token 推送，支持多模态消息和工具调用。",
      items: [
        ["事件类型", "conversation_id → rag_context → token → tool_start → done → error"],
        ["生成器模式", "FastAPI StreamingResponse + async generator 实现非阻塞流式输出"],
        ["会话独立", "SSE 流内独立管理 DB session，覆盖 FastAPI DI 生命周期"],
        ["自动命名", "首条用户消息前 50 字符自动设为对话标题"],
        ["流中断", "前端 AbortController 实现停止生成功能"],
      ],
    },
    {
      title: "Mem0 长期记忆", color: "#f59e0b", content: "跨会话记忆持久化，基于 Mem0 + PostgreSQL/pgvector 向量存储。",
      items: [
        ["记忆存储", "每轮对话结束后异步保存 user+assistant 消息对到 Mem0"],
        ["记忆检索", "发送新消息前基于当前 query 搜索 Mem0 相关记忆，注入 System Prompt"],
        ["用户识别", "基于客户端 IP 作为 user_id（无认证系统下的最佳实践）"],
        ["持久化", "Mem0 pgvector 存储到 PostgreSQL，容器重启数据不丢失"],
        ["容错降级", "Mem0 初始化/存储/检索失败静默处理，不阻塞主流程"],
      ],
    },
    {
      title: "上下文压缩与多模态", color: "#c084fc", content: "长对话自动压缩 + 视觉模型自动切换。",
      items: [
        ["触发条件", "预估 tokens 超过 max_tokens × 70% 时自动触发压缩"],
        ["压缩策略", "保留最近 6 条消息，LLM 将更早消息压缩为 200 字中文摘要"],
        ["Token 估算", "字符数 / 2（混合中英文实用估算），前端实时显示用量进度条"],
        ["视觉模型", "检测到图片附件后自动切换到多模态模型"],
        ["Base64 内联", "本地图片自动转 base64 data URL 传给 API"],
      ],
    },
    {
      title: "工具系统", color: "#6b7280", content: "15 个 LangChain Tool 实现 Agent Function Calling，含 DifySandbox 代码沙盒。",
      items: [
        ["工具列表", "calculator、web_search、get_weather、get_news、run_python_code、run_javascript_code、run_shell_command、install_python_packages 等 15 个工具"],
        ["代码沙盒", "DifySandbox 容器隔离执行 Python/JS/Bash，网络禁用、超时控制、依赖按需安装"],
        ["语义路由", "bigram Jaccard 匹配自动选择相关工具组，减少 prompt tokens"],
        ["安全措施", "calculator AST 白名单；沙盒分层禁止 subprocess/os.system；代码预检拦截危险模式"],
      ],
    },
    {
      title: "LLM 多提供商", color: "#4D6BFE", content: "Qwen (DashScope) / OpenAI / Claude 三提供商统一接口。",
      items: [
        ["Qwen 默认", "qwen3.7-plus 主力模型 + qwen-vl-plus 视觉模型"],
        ["通用工厂", "get_llm() 统一创建 ChatOpenAI 实例"],
        ["LLM 缓存", "字典缓存 provider_model_temp_tokens → ChatOpenAI"],
        ["前台切换", "前端 ModelSelector → agent_config → get_llm()"],
      ],
    },
    {
      title: "基础设施", color: "#f59e0b", content: "FastAPI + PostgreSQL/pgvector + Redis + React 企业级技术栈。",
      items: [
        ["数据库", "PostgreSQL 16 + pgvector 扩展 (HNSW 索引) + async SQLAlchemy 连接池"],
        ["缓存/限流", "Redis 滑动窗口计数器，按 IP 区分"],
        ["安全加固", "全 POST API + JSON body；安全 Header；10MB 请求体上限；api/v1 版本化"],
        ["前端", "React 18 + Vite + Tailwind CSS 4 + shadcn/ui + react-router-dom"],
        ["部署", "Docker Compose 5 容器 (frontend nginx + backend uvicorn + postgres + redis + difysandbox)"],
      ],
    },
  ];

  const [expanded, setExpanded] = useState<Set<number>>(() => new Set(sections.map((_, i) => i)));
  const toggle = (i: number) => {
    const next = new Set(expanded);
    next.has(i) ? next.delete(i) : next.add(i);
    setExpanded(next);
  };

  return (
    <div className="space-y-4">
      <div>
        <div className="text-sm font-semibold text-gray-800 mb-1">AI Agent 技术全景</div>
        <div className="text-xs text-gray-400">本平台基于 LangGraph + FastAPI + PostgreSQL/pgvector 构建</div>
      </div>
      {sections.map((sec, i) => {
        const open = expanded.has(i);
        return (
          <div key={i} className="bg-white rounded-xl border border-gray-200 overflow-hidden transition-colors" style={{ borderColor: open ? `${sec.color}30` : "" }}>
            <button onClick={() => toggle(i)} className="w-full flex items-center gap-3 px-5 py-4 text-left cursor-pointer select-none hover:bg-gray-50/50 transition-colors">
              <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 text-sm font-bold" style={{ background: `${sec.color}15`, color: sec.color }}>{i + 1}</div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-semibold text-gray-800">{sec.title}</div>
                <div className="text-xs text-gray-400 mt-0.5">{sec.content}</div>
              </div>
              <span className="text-gray-300 transition-transform duration-300 text-sm" style={{ transform: open ? "rotate(180deg)" : "rotate(0deg)" }}>▼</span>
            </button>
            <div style={{ maxHeight: open ? "999px" : "0px", opacity: open ? 1 : 0, padding: open ? "0 20px 18px 64px" : "0 20px 0 64px", transition: "max-height 0.4s ease, padding 0.3s, opacity 0.2s", overflow: "hidden" }}>
              {sec.items.map(([label, desc], j) => (
                <div key={j} className="flex gap-3.5 py-2.5" style={{ borderBottom: j < sec.items.length - 1 ? "1px solid rgba(0,0,0,0.04)" : "none" }}>
                  <div className="w-1.5 h-1.5 rounded-full flex-shrink-0 mt-1.5" style={{ background: sec.color }} />
                  <div className="min-w-0">
                    <div className="text-xs font-semibold text-gray-700">{label}</div>
                    <div className="text-xs text-gray-400 leading-relaxed mt-0.5">{desc}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      })}
      <div className="text-center py-6">
        <span className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-full bg-ds-50 border border-ds-200 text-xs text-ds-600">
          <span className="w-1.5 h-1.5 rounded-full bg-ds-500" />
          FastAPI + LangGraph + PostgreSQL/pgvector + Redis + React + react-router-dom
        </span>
      </div>
    </div>
  );
}
