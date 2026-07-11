import { useState, useEffect, useRef } from "react";
import { api } from "../api/client";

/* ================================================================
   CSS-in-JS design tokens — matching main app cyberpunk aesthetic
   ================================================================ */
const C = {
  bg: "#0b0b16",
  surface: "#14141f",
  card: "#1a1a2e",
  border: "rgba(255,255,255,0.06)",
  borderHover: "rgba(0,229,255,0.15)",
  text: "#e6e8ee",
  textDim: "rgba(255,255,255,0.45)",
  textMuted: "rgba(255,255,255,0.25)",
  accent: "#00e5ff",
  accentDim: "rgba(0,229,255,0.15)",
  accentGlow: "0 0 20px rgba(0,229,255,0.12)",
  green: "#34d399",
  greenDim: "rgba(52,211,153,0.12)",
  amber: "#fbbf24",
  amberDim: "rgba(251,191,36,0.12)",
  red: "#f87171",
  redDim: "rgba(248,113,113,0.12)",
  radius: "12px",
  radiusSm: "8px",
};

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
interface LLMConfig { providers: LLMProvider[]; default_provider: string; }

type Tab = "dashboard" | "rag" | "llm" | "tech";

/* ================================================================
   Inline styles
   ================================================================ */
const s = {
  overlay: {
    position: "fixed" as const, inset: 0, zIndex: 1000,
    background: C.bg, display: "flex", fontFamily: "inherit",
  },
  sidebar: {
    width: 220, background: "rgba(255,255,255,0.02)",
    borderRight: `1px solid ${C.border}`, display: "flex", flexDirection: "column" as const,
    flexShrink: 0,
  },
  sidebarLogo: {
    padding: "24px 20px 20px", borderBottom: `1px solid ${C.border}`,
  },
  sidebarNav: { flex: 1, padding: "8px 10px" },
  navItem: (active: boolean): React.CSSProperties => ({
    display: "flex", alignItems: "center", gap: 10, padding: "10px 12px",
    borderRadius: C.radiusSm, cursor: "pointer", fontSize: 13, fontWeight: 500,
    transition: "all 0.2s",
    color: active ? C.accent : C.textDim,
    background: active ? C.accentDim : "transparent",
    marginBottom: 2,
  }),
  main: {
    flex: 1, display: "flex", flexDirection: "column" as const, overflow: "hidden",
  },
  header: {
    height: 56, display: "flex", alignItems: "center", justifyContent: "space-between",
    padding: "0 28px", borderBottom: `1px solid ${C.border}`,
    background: C.surface, flexShrink: 0,
  },
  content: {
    flex: 1, overflow: "auto", padding: "32px 28px",
  },
  card: {
    background: C.card, borderRadius: C.radius, border: `1px solid ${C.border}`,
    padding: "22px 24px", transition: "all 0.3s",
    position: "relative" as const, overflow: "hidden",
  },
  statLabel: {
    fontSize: 12, color: C.textMuted, textTransform: "uppercase" as const,
    letterSpacing: "0.05em", marginBottom: 6,
  },
  statValue: {
    fontSize: 32, fontWeight: 700, color: C.text, lineHeight: 1.1,
    fontVariantNumeric: "tabular-nums" as const,
  },
  statBadge: {
    display: "inline-flex", alignItems: "center", gap: 4,
    fontSize: 12, padding: "2px 8px", borderRadius: 100,
    marginTop: 8, fontWeight: 500,
  },
  providerCard: (enabled: boolean) => ({
    background: enabled ? C.card : "rgba(255,255,255,0.03)",
    borderRadius: C.radius, border: `1px solid ${enabled ? C.border : "rgba(255,255,255,0.04)"}`,
    padding: "20px 22px", transition: "all 0.3s", opacity: enabled ? 1 : 0.55,
    position: "relative" as const, overflow: "hidden",
  }),
  tag: (active: boolean) => ({
    display: "inline-flex", alignItems: "center", gap: 4,
    fontSize: 11, padding: "3px 10px", borderRadius: 100,
    background: active ? C.accentDim : "rgba(255,255,255,0.05)",
    color: active ? C.accent : C.textDim, fontWeight: 500,
    border: `1px solid ${active ? "rgba(0,229,255,0.2)" : "rgba(255,255,255,0.06)"}`,
  }),
  dot: (color: string) => ({
    width: 8, height: 8, borderRadius: "50%", background: color,
    boxShadow: `0 0 8px ${color}66`, flexShrink: 0,
  }),
  barTrack: {
    height: 6, borderRadius: 3, background: "rgba(255,255,255,0.06)", overflow: "hidden",
  },
  barFill: (pct: number, color: string) => ({
    height: "100%", width: `${pct}%`, borderRadius: 3,
    background: color, transition: "width 0.8s ease",
    boxShadow: `0 0 8px ${color}66`,
  }),
};

const navIcons: Record<Tab, string> = { dashboard: "◉", rag: "◈", llm: "◆", tech: "◬" };
const navLabels: Record<Tab, string> = { dashboard: "仪表盘", rag: "知识库管理", llm: "大模型配置", tech: "技术解析" };

/* ================================================================
   Component
   ================================================================ */
export function AdminPage({ onClose }: { onClose: () => void }) {
  const [tab, setTab] = useState<Tab>("dashboard");
  const [loading, setLoading] = useState(false);
  const [stats, setStats] = useState<Stats | null>(null);
  const [llmConfig, setLlmConfig] = useState<LLMConfig | null>(null);
  const [documents, setDocuments] = useState<any[]>([]);

  const loadAll = async () => {
    setLoading(true);
    try {
      const [s, l, d] = await Promise.all([api.adminDashboard(), api.adminLlmList(), api.adminRagDocuments()]);
      setStats(s); setLlmConfig(l); setDocuments(d);
    } catch { /* silent */ }
    setLoading(false);
  };
  useEffect(() => { loadAll(); }, []);

  const maxMsg = stats ? Math.max(stats.total_messages, 1) : 1;

  return (
    <div style={s.overlay}>
      {/* Sidebar */}
      <div style={s.sidebar}>
        <div style={s.sidebarLogo}>
          <div style={{ fontSize: 16, fontWeight: 700, color: C.accent, letterSpacing: 1 }}>AI AGENT</div>
          <div style={{ fontSize: 11, color: C.textMuted, letterSpacing: 2, marginTop: 2 }}>管理后台</div>
        </div>
        <div style={s.sidebarNav}>
          {(Object.keys(navLabels) as Tab[]).map((k) => (
            <div key={k} style={s.navItem(tab === k)} onClick={() => setTab(k)}
              onMouseEnter={(e) => { if (tab !== k) { e.currentTarget.style.background = "rgba(255,255,255,0.04)"; e.currentTarget.style.color = C.text; }}}
              onMouseLeave={(e) => { if (tab !== k) { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = C.textDim; }}}
            >
              <span style={{ fontSize: 14, color: tab === k ? C.accent : C.textMuted }}>{navIcons[k]}</span>
              {navLabels[k]}
            </div>
          ))}
        </div>
        <div style={{ padding: "12px 16px", borderTop: `1px solid ${C.border}` }}>
          <div onClick={onClose} style={{ ...s.navItem(false), cursor: "pointer" }}
            onMouseEnter={(e) => { e.currentTarget.style.background = "rgba(248,113,113,0.1)"; e.currentTarget.style.color = C.red; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = C.textDim; }}
          >
            <span>←</span> 返回前台
          </div>
        </div>
      </div>

      {/* Main */}
      <div style={s.main}>
        <div style={s.header}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 18, color: C.accent }}>{navIcons[tab]}</span>
            <span style={{ fontSize: 15, fontWeight: 600, color: C.text }}>{navLabels[tab]}</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 12, fontSize: 12, color: C.textMuted }}>
            {loading && <span style={{ color: C.accent }}>加载中...</span>}
            <span onClick={loadAll} style={{ cursor: "pointer", color: C.textDim, transition: "color 0.2s" }}
              onMouseEnter={(e) => { e.currentTarget.style.color = C.accent; }}
              onMouseLeave={(e) => { e.currentTarget.style.color = C.textDim; }}
            >↻ 刷新</span>
          </div>
        </div>

        <div style={s.content}>
          {tab === "dashboard" && stats && <Dashboard stats={stats} llmConfig={llmConfig} maxMsg={maxMsg} />}
          {tab === "rag" && <RagPanel documents={documents} onRefresh={loadAll} />}
          {tab === "llm" && llmConfig && <LlmPanel llmConfig={llmConfig} />}
          {tab === "tech" && <TechPanel />}
        </div>
      </div>
    </div>
  );
}

/* ================================================================
   Dashboard Tab
   ================================================================ */
function Dashboard({ stats, llmConfig, maxMsg }: { stats: Stats; llmConfig: LLMConfig | null; maxMsg: number }) {
  const cards = [
    { label: "对话总数", value: stats.total_conversations, sub: `今日 +${stats.conversations_today}`, color: C.accent, icon: "💬" },
    { label: "消息总数", value: stats.total_messages, sub: `今日 +${stats.messages_today}`, color: "#818cf8", icon: "📨" },
    { label: "知识库文档", value: stats.total_documents, sub: `${stats.total_chunks} 个分块`, color: C.green, icon: "📄" },
    { label: "存储空间", value: `${stats.total_storage_mb} MB`, sub: `${stats.total_agents} 个 Agent`, color: C.amber, icon: "💾" },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 28 }}>
      {/* Stat cards row */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 16 }}>
        {cards.map((c) => (
          <div key={c.label} style={s.card}
            onMouseEnter={(e) => { e.currentTarget.style.borderColor = C.borderHover; e.currentTarget.style.boxShadow = C.accentGlow; }}
            onMouseLeave={(e) => { e.currentTarget.style.borderColor = C.border; e.currentTarget.style.boxShadow = "none"; }}
          >
            <span style={{ fontSize: 20, position: "absolute", top: 16, right: 16, opacity: 0.5 }}>{c.icon}</span>
            <div style={s.statLabel}>{c.label}</div>
            <div style={s.statValue}>{c.value}</div>
            <div style={{ ...s.statBadge, background: `${c.color}15`, color: c.color, border: `1px solid ${c.color}25` }}>
              <span style={s.dot(c.color)} /> {c.sub}
            </div>
          </div>
        ))}
      </div>

      {/* Usage bars */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
        <UsageBar label="消息活跃度" pct={Math.min(100, (stats.messages_today / Math.max(maxMsg / 10, 1)) * 100)} color={C.accent} />
        <UsageBar label="文档存储率" pct={Math.min(100, stats.total_storage_mb * 5)} color={C.green} />
      </div>

      {/* Provider status */}
      <div>
        <div style={{ fontSize: 14, fontWeight: 600, color: C.text, marginBottom: 16 }}>LLM 提供商状态</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: 14 }}>
          {(llmConfig?.providers || []).map((p) => (
            <div key={p.id} style={s.providerCard(p.enabled)}
              onMouseEnter={(e) => { if (p.enabled) { e.currentTarget.style.borderColor = C.borderHover; } }}
              onMouseLeave={(e) => { if (p.enabled) { e.currentTarget.style.borderColor = C.border; } }}
            >
              <div style={{ position: "absolute", top: 0, left: 0, width: "100%", height: 2,
                background: p.enabled ? `linear-gradient(90deg, ${C.accent}, transparent)` : "rgba(255,255,255,0.04)" }} />
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={s.dot(p.enabled ? C.green : C.textMuted)} />
                  <span style={{ fontSize: 14, fontWeight: 600, color: C.text }}>{p.name}</span>
                </div>
                <span style={s.tag(p.enabled)}>{p.enabled ? "已启用" : "未配置"}</span>
              </div>
              <div style={{ fontSize: 12, color: C.textDim, lineHeight: 1.8 }}>
                <div>默认模型 <span style={{ color: C.text }}>{p.default_model || "—"}</span></div>
                <div>API Key <span style={{ color: p.api_key_set ? C.green : C.red }}>{p.api_key_set ? "已配置" : "未配置"}</span></div>
              </div>
              {p.enabled && (
                <div style={{ marginTop: 12, display: "flex", flexWrap: "wrap", gap: 6 }}>
                  {p.models.slice(0, 4).map((m) => (
                    <span key={m} style={s.tag(m === p.default_model)}>{m}</span>
                  ))}
                  {p.models.length > 4 && <span style={s.tag(false)}>+{p.models.length - 4}</span>}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function UsageBar({ label, pct, color }: { label: string; pct: number; color: string }) {
  return (
    <div style={s.card}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
        <span style={{ fontSize: 12, color: C.textDim, textTransform: "uppercase" as const, letterSpacing: "0.05em" }}>{label}</span>
        <span style={{ fontSize: 12, color, fontWeight: 600 }}>{Math.round(pct)}%</span>
      </div>
      <div style={s.barTrack}>
        <div style={s.barFill(pct, color)} />
      </div>
    </div>
  );
}

/* ================================================================
   RAG Panel
   ================================================================ */
function RagPanel({ documents, onRefresh }: { documents: any[]; onRefresh: () => void }) {
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleUpload = async (files: FileList | null) => {
    if (!files?.length) return;
    setUploading(true);
    for (const f of Array.from(files)) {
      try { await api.adminRagUpload(f); } catch (e: any) { alert("上传失败: " + e.message); }
    }
    setUploading(false);
    if (fileRef.current) fileRef.current.value = "";
    onRefresh();
  };

  const handleDelete = async (id: string, name: string) => {
    if (!confirm(`确定删除"${name}"？`)) return;
    try { await api.adminRagDelete(id); onRefresh(); } catch (e: any) { alert("删除失败: " + e.message); }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <div style={{ fontSize: 14, fontWeight: 600, color: C.text }}>管理员知识库文档</div>
          <div style={{ fontSize: 12, color: C.textMuted, marginTop: 4 }}>
            共 {documents.length} 个文档 — 仅供「知识库助手」Agent 检索
          </div>
        </div>
        <div style={{ display: "flex", gap: 10 }}>
          <input ref={fileRef} type="file" multiple accept=".pdf,.docx,.txt,.md"
            onChange={(e) => handleUpload(e.target.files)} style={{ display: "none" }} />
          <span onClick={() => fileRef.current?.click()} style={{
            display: "inline-flex", alignItems: "center", gap: 6, cursor: "pointer",
            padding: "7px 16px", borderRadius: C.radiusSm, fontSize: 12, fontWeight: 600,
            background: C.accentDim, color: C.accent, border: `1px solid ${C.accent}20`,
            transition: "all 0.2s",
          }}
            onMouseEnter={(e) => { e.currentTarget.style.background = C.accent; e.currentTarget.style.color = "#000"; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = C.accentDim; e.currentTarget.style.color = C.accent; }}
          >
            {uploading ? "上传中..." : "+ 上传文档"}
          </span>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "2fr 0.6fr 0.6fr 0.6fr 0.8fr 1fr 0.4fr", gap: 12,
        padding: "10px 14px", fontSize: 11, color: C.textMuted, textTransform: "uppercase" as const,
        letterSpacing: "0.05em", borderBottom: `1px solid ${C.border}` }}>
        <span>文件名</span><span>类型</span><span>大小</span><span>分块</span><span>状态</span><span>上传时间</span><span>操作</span>
      </div>

      {documents.length === 0 ? (
        <div style={{ textAlign: "center", padding: 64, color: C.textMuted, fontSize: 14 }}>
          暂无管理端文档，点击右上角上传
        </div>
      ) : (
        documents.map((doc) => (
          <div key={doc.id} style={{
            display: "grid", gridTemplateColumns: "2fr 0.6fr 0.6fr 0.6fr 0.8fr 1fr 0.4fr", gap: 12,
            padding: "14px", fontSize: 13, color: C.textDim, alignItems: "center",
            borderRadius: C.radiusSm, transition: "all 0.2s",
            background: "transparent", borderBottom: `1px solid rgba(255,255,255,0.03)`,
          }}
            onMouseEnter={(e) => { e.currentTarget.style.background = "rgba(255,255,255,0.03)"; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
          >
            <span style={{ color: C.text, fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{doc.filename}</span>
            <span style={s.tag(true)}>{doc.file_type}</span>
            <span>{(doc.file_size / 1024).toFixed(1)} KB</span>
            <span>{doc.chunk_count}</span>
            <span>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                <span style={{ width: 6, height: 6, borderRadius: "50%",
                  background: doc.status === "ready" ? C.green : C.amber,
                  boxShadow: `0 0 6px ${doc.status === "ready" ? C.green : C.amber}66` }} />
                {doc.status === "ready" ? "就绪" : doc.status}
              </span>
            </span>
            <span>{new Date(doc.created_at).toLocaleDateString("zh-CN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}</span>
            <span onClick={() => handleDelete(doc.id, doc.filename)} style={{
              cursor: "pointer", color: C.textMuted, textAlign: "center" as const,
              transition: "color 0.2s", fontSize: 11,
            }}
              onMouseEnter={(e) => { e.currentTarget.style.color = C.red; }}
              onMouseLeave={(e) => { e.currentTarget.style.color = C.textMuted; }}
            >删除</span>
          </div>
        ))
      )}
    </div>
  );
}

/* ================================================================
   LLM Panel
   ================================================================ */
function LlmPanel({ llmConfig }: { llmConfig: LLMConfig }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <div>
        <div style={{ fontSize: 14, fontWeight: 600, color: C.text, marginBottom: 4 }}>大模型提供商</div>
        <div style={{ fontSize: 12, color: C.textMuted }}>
          默认提供商 <span style={{ color: C.accent, fontWeight: 600 }}>{llmConfig.default_provider}</span>。
          在 .env 中配置 API Key 后，对应提供商将自动启用。
        </div>
      </div>

      {llmConfig.providers.map((p) => (
        <div key={p.id} style={{
          background: p.enabled ? C.card : "rgba(255,255,255,0.02)",
          borderRadius: C.radius, border: `1px solid ${p.enabled ? C.border : "rgba(255,255,255,0.04)"}`,
          padding: "24px", opacity: p.enabled ? 1 : 0.6, transition: "all 0.3s",
        }}>
          {/* Header */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 18 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span style={s.dot(p.enabled ? C.accent : C.textMuted)} />
              <span style={{ fontSize: 16, fontWeight: 700, color: C.text }}>{p.name}</span>
              <span style={{ fontSize: 11, color: C.textMuted, fontFamily: "monospace" }}>{p.id}</span>
            </div>
            <span style={s.tag(p.enabled)}>{p.enabled ? "已启用" : "未配置 API Key"}</span>
          </div>

          {/* Config grid */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px 32px" }}>
            <ConfigRow label="API 地址" value={p.base_url} />
            <ConfigRow label="默认模型" value={p.default_model || "未设置"} highlight />
            <ConfigRow label="API Key" value={p.api_key_set ? "****" + "●".repeat(12) : "—"} highlight />
            <ConfigRow label="可用模型数" value={`${p.models.length} 个`} />
          </div>

          {/* Model tags */}
          {p.enabled && (
            <div style={{ marginTop: 20, paddingTop: 16, borderTop: `1px solid ${C.border}` }}>
              <div style={{ fontSize: 11, color: C.textMuted, marginBottom: 8, textTransform: "uppercase" as const, letterSpacing: "0.05em" }}>可用模型</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {p.models.map((m) => (
                  <span key={m} style={s.tag(m === p.default_model)}>{m}{m === p.default_model ? " (默认)" : ""}</span>
                ))}
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function ConfigRow({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div>
      <div style={{ fontSize: 11, color: C.textMuted, textTransform: "uppercase" as const, letterSpacing: "0.05em", marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 13, color: highlight ? C.accent : C.textDim, fontFamily: highlight ? "monospace" : "inherit" }}>{value}</div>
    </div>
  );
}

/* ================================================================
   Tech Panel — comprehensive AI Agent technology breakdown
   ================================================================ */
function TechPanel() {
  const sections = [
    {
      icon: "◉", title: "LangGraph Agent 引擎", color: C.accent,
      content: "基于 LangGraph 构建的有状态 Agent 图执行引擎，实现 Tool-calling + RAG 深度集成。",
      items: [
        ["图状态管理", "AgentState TypedDict 统一管理消息流、工具启用列表、RAG 上下文、迭代计数"],
        ["节点定义", "agent_node（LLM 推理）、rag_node（知识库检索）、tool_node（工具执行）"],
        ["路由逻辑", "should_continue 条件边：ToolMessage → tool_node 循环调用，AIMessage → END 终止"],
        ["迭代保护", "最大迭代 8 轮硬上限，防止 Agent 无限循环（guardrail pattern）"],
      ],
    },
    {
      icon: "◈", title: "RAG 混合检索", color: C.green,
      content: "语义向量检索 + BM25 关键词检索双路融合，通过 RRF 算法联合排序。",
      items: [
        ["语义检索", "DashScope text-embedding-v3 (1024d) → pgvector HNSW 索引 → cosine_distance 排序"],
        ["关键词检索 (BM25)", "PostgreSQL tsvector + GIN 倒排索引 → ts_rank 排序，CJK 逐字分词"],
        ["RRF 融合", "Reciprocal Rank Fusion (k=60)：两路结果加权合并去重，弥补纯语义的专有名词短板"],
        ["文档处理", "PDF (pdfplumber) / DOCX (python-docx) → 语义分块 (500 char / 50 overlap) → 批量向量化"],
        ["相似度阈值", "Agent 配置 rag_similarity_threshold (默认 0.5) 过滤低质量结果"],
      ],
    },
    {
      icon: "→", title: "SSE 流式输出", color: "#818cf8",
      content: "Server-Sent Events 逐 token 推送，支持多模态消息和工具调用实时反馈。",
      items: [
        ["事件类型", "conversation_id → rag_context → token → tool_start → done → error"],
        ["生成器模式", "FastAPI StreamingResponse + async generator 实现非阻塞流式输出"],
        ["会话独立", "SSE 流内独立管理 DB session（async_session_factory），覆盖 FastAPI DI 生命周期"],
        ["自动命名", "首条用户消息前 50 字符自动设为对话标题"],
        ["流中断", "前端 AbortController 实现停止生成功能"],
      ],
    },
    {
      icon: "●", title: "Mem0 长期记忆", color: C.amber,
      content: "跨会话记忆持久化，基于 Mem0 + Qdrant 向量存储，自动提取用户偏好与事实。",
      items: [
        ["记忆存储", "每轮对话结束后异步保存 user+assistant 消息对到 Mem0 (Qdrant 内嵌模式)"],
        ["记忆检索", "发送新消息前基于当前 query 搜索 Mem0 相关记忆，注入 System Prompt"],
        ["用户识别", "基于客户端 IP 作为 user_id，同一 IP 所有对话共享记忆（无认证系统下的最佳实践）"],
        ["容错降级", "Mem0 初始化/存储/检索失败静默处理，不阻塞主流程"],
      ],
    },
    {
      icon: "◆", title: "上下文压缩与多模态", color: "#c084fc",
      content: "长对话自动压缩 + 视觉模型自动切换，突破上下文窗口限制。",
      items: [
        ["触发条件", "预估 tokens 超过 max_tokens × 70% 时自动触发压缩"],
        ["压缩策略", "保留最近 6 条消息不变，LLM 将更早消息压缩为 200 字中文摘要 → 存入 DB system role"],
        ["Token 估算", "字符数 / 2（混合中英文实用估算），前端实时显示用量进度条（青色/琥珀/红色三段）"],
        ["视觉模型", "检测到图片附件后自动从 qwen-plus 切换到 qwen-vl-plus 多模态模型"],
        ["Base64 内联", "本地 /uploads/ 图片自动转 base64 data URL 传给 DashScope API"],
      ],
    },
    {
      icon: "◇", title: "工具系统", color: C.textDim,
      content: "10 个 LangChain Tool 实现 Agent Function Calling，覆盖计算、搜索、天气等场景。",
      items: [
        ["工具列表", "calculator (AST 安全解析)、web_search (DuckDuckGo)、get_current_time、get_weather (wttr.in)、get_news、lookup_ip (ip-api)、exchange_rate、fetch_url、tell_joke"],
        ["RAG 特殊工具", "rag 非 LangChain Tool，在图节点中单独处理，由 enabled_tools 配置控制"],
        ["安全措施", "calculator 用 Python AST 白名单解析（禁止任意代码执行）；fetch_url 需进一步加固 SSRF 防护"],
      ],
    },
    {
      icon: "◎", title: "LLM 多提供商", color: C.accent,
      content: "Qwen (DashScope) / OpenAI / Claude 三提供商统一接口，OpenAI-compatible 协议。",
      items: [
        ["Qwen 默认", "qwen-plus 主力模型 + qwen-vl-plus 视觉模型，DashScope OpenAI-compatible endpoint"],
        ["通用工厂", "get_llm() 统一创建 ChatOpenAI 实例，根据 provider 自动切换 api_key/base_url/model"],
        ["LLM 缓存", "字典缓存 provider_model_temp_tokens → ChatOpenAI，避免重复创建"],
        ["前台切换", "前端 ModelSelector → ChatRequest.model_provider → agent_config → get_llm()"],
      ],
    },
    {
      icon: "⬡", title: "基础设施", color: C.amber,
      content: "FastAPI + PostgreSQL/pgvector + Redis + React 企业级技术栈。",
      items: [
        ["数据库", "PostgreSQL 16 + pgvector 扩展 (HNSW 索引) + async SQLAlchemy 连接池 (pool_size=10)"],
        ["缓存/限流", "Redis 滑动窗口计数器，写入 10/60s，读取 60/60s，按 IP 区分"],
        ["安全加固", "全 POST API + JSON body（防 URL 暴露）；X-Content-Type-Options / X-Frame-Options / Permissions-Policy；10MB 请求体上限；IdRequest 路径遍历过滤；api/v1 版本化"],
        ["前端", "React 18 + Vite 5 + Tailwind CSS 4 + shadcn/ui + 自定义科技风暗色主题"],
        ["部署", "Docker Compose 4 容器 (frontend nginx + backend uvicorn + postgres + redis)"],
      ],
    },
  ];

  // --- Accordion state ---
  const [expanded, setExpanded] = useState<Set<number>>(() => new Set(sections.map((_, i) => i)));

  const toggle = (i: number) => {
    const next = new Set(expanded);
    next.has(i) ? next.delete(i) : next.add(i);
    setExpanded(next);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div>
        <div style={{ fontSize: 14, fontWeight: 600, color: C.text, marginBottom: 4 }}>AI Agent 技术全景</div>
        <div style={{ fontSize: 12, color: C.textMuted }}>
          本平台基于 LangGraph + FastAPI + PostgreSQL/pgvector 构建，以下为各子系统技术栈详解
        </div>
      </div>

      {sections.map((sec, i) => {
        const open = expanded.has(i);
        return (
          <div
            key={i}
            style={{
              background: C.card, borderRadius: C.radius,
              border: `1px solid ${open ? sec.color + "30" : C.border}`,
              overflow: "hidden", transition: "border-color 0.3s",
            }}
          >
            {/* Header */}
            <div
              onClick={() => toggle(i)}
              style={{
                display: "flex", alignItems: "center", gap: 12,
                padding: "16px 20px", cursor: "pointer",
                userSelect: "none" as const,
                transition: "background 0.2s",
                background: open ? `${sec.color}06` : "transparent",
              }}
              onMouseEnter={(e) => { e.currentTarget.style.background = `${sec.color}08`; }}
              onMouseLeave={(e) => { if (!open) e.currentTarget.style.background = "transparent"; }}
            >
              <span style={{
                display: "flex", alignItems: "center", justifyContent: "center",
                width: 32, height: 32, borderRadius: C.radiusSm, fontSize: 16,
                background: `${sec.color}15`, color: sec.color,
              }}>{sec.icon}</span>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 14, fontWeight: 600, color: C.text }}>{sec.title}</div>
                <div style={{ fontSize: 12, color: C.textDim, marginTop: 2 }}>{sec.content}</div>
              </div>
              <span style={{
                fontSize: 14, color: C.textMuted, transition: "transform 0.3s",
                transform: open ? "rotate(180deg)" : "rotate(0deg)",
              }}>▾</span>
            </div>

            {/* Body */}
            <div style={{
              maxHeight: open ? "999px" : "0px",
              overflow: "hidden",
              transition: "max-height 0.4s ease, padding 0.3s",
              padding: open ? "2px 20px 18px 64px" : "0 20px 0 64px",
              opacity: open ? 1 : 0,
              transitionProperty: "max-height, padding, opacity",
              transitionDuration: "0.4s, 0.3s, 0.2s",
            }}>
              <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
                {sec.items.map(([label, desc], j) => (
                  <div key={j} style={{
                    display: "flex", gap: 14, padding: "10px 0",
                    borderBottom: j < sec.items.length - 1 ? `1px solid rgba(255,255,255,0.04)` : "none",
                  }}>
                    <div style={{
                      width: 5, height: 5, borderRadius: "50%", flexShrink: 0, marginTop: 7,
                      background: sec.color, boxShadow: `0 0 6px ${sec.color}66`,
                    }} />
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: 12, fontWeight: 600, color: C.text }}>{label}</div>
                      <div style={{ fontSize: 12, color: C.textDim, lineHeight: 1.7, marginTop: 2 }}>{desc}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        );
      })}

      {/* Footer badge */}
      <div style={{ textAlign: "center", padding: "24px 0 8px" }}>
        <div style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "6px 16px",
          borderRadius: 100, background: C.accentDim, border: `1px solid ${C.accent}20`,
          fontSize: 12, color: C.accent }}>
          <span style={s.dot(C.accent)} /> FastAPI + LangGraph + PostgreSQL/pgvector + Redis + React
        </div>
      </div>
    </div>
  );
}
