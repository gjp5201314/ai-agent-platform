/**
 * API客户端模块
 * 
 * 功能说明：
 * 1. 封装所有与后端API的通信逻辑
 * 2. 实现SSE流式聊天接口
 * 3. 提供会话、文档、Agent、沙箱等API调用方法
 * 
 * 安全特性：
 * - 所有操作使用POST方法 + JSON请求体
 * - 不在URL中暴露ID、令牌或查询参数
 */

import type {
  Conversation,
  Document,
  AgentConfig,
  ToolInfo,
  SSEEvent,
  Attachment,
} from "../types";

/** API基础路径 */
const API_BASE = "/api/v1";

// ============================================================
//  安全策略：所有操作使用POST + JSON请求体
//  URL中不出现ID、令牌或查询参数
// ============================================================

/**
 * 通用JSON请求方法
 * 
 * @param url - 请求URL
 * @param body - 请求体（可选）
 * @returns 解析后的JSON响应
 */
async function fetchJSON<T>(url: string, body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body !== undefined ? JSON.stringify(body) : "{}",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

// ---- 聊天接口（SSE流式输出）----

/**
 * 流式聊天接口（Server-Sent Events）
 * 
 * @param message - 用户消息
 * @param conversationId - 会话ID（可选）
 * @param agentId - Agent ID（可选）
 * @param useRag - 是否启用RAG检索
 * @param attachments - 附件列表
 * @param modelProvider - 模型提供商（可选）
 * @returns SSE事件异步生成器
 */
export async function* streamChat(
  message: string,
  conversationId: string | null,
  agentId: string | null,
  useRag: boolean,
  attachments: Attachment[] = [],
  modelProvider?: string,
): AsyncGenerator<SSEEvent> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      conversation_id: conversationId,
      agent_id: agentId,
      stream: true,
      use_rag: useRag,
      attachments,
      model_provider: modelProvider || null,
    }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }

  // 读取流式响应
  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const data = line.slice(6).trim();
        if (data === "[DONE]") return;
        try {
          const event: SSEEvent = JSON.parse(data);
          yield event;
        } catch {
          // 忽略格式错误的行
        }
      }
    }
  }
}

// ============================================================
//  API接口定义 - 全部使用POST + JSON请求体
// ============================================================

export const api = {
  // ========== 聊天相关 ==========

  /** 流式聊天接口 */
  streamChat,

  /**
   * 上传聊天附件
   * 使用multipart/form-data格式（文件二进制上传必需）
   */
  uploadAttachment: async (file: File): Promise<Attachment> => {
    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch(`${API_BASE}/chat/upload`, {
      method: "POST",
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Upload failed" }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
  },

  // ========== 会话管理 ==========

  /** 获取会话列表 */
  listConversations: (skip = 0, limit = 50) =>
    fetchJSON<Conversation[]>(`${API_BASE}/conversations/list`, { skip, limit }),

  /** 获取单个会话详情 */
  getConversation: (id: string) =>
    fetchJSON<Conversation>(`${API_BASE}/conversations/get`, { id }),

  /** 创建新会话 */
  createConversation: (title: string, agentId?: string) =>
    fetchJSON<Conversation>(`${API_BASE}/conversations/create`, {
      title,
      agent_id: agentId ?? null,
    }),

  /** 删除会话 */
  deleteConversation: (id: string) =>
    fetchJSON<{ detail: string }>(`${API_BASE}/conversations/delete`, { id }),

  /** 更新会话标题 */
  updateTitle: (conversationId: string, title: string) =>
    fetchJSON<{ detail: string }>(`${API_BASE}/conversations/update-title`, {
      conversation_id: conversationId,
      title,
    }),

  // ========== 文档管理 / RAG ==========

  /** 获取文档列表 */
  listDocuments: (skip = 0, limit = 50) =>
    fetchJSON<Document[]>(`${API_BASE}/rag/documents/list`, { skip, limit }),

  /**
   * 上传文档到RAG知识库
   * 使用multipart/form-data格式
   */
  uploadDocument: (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return fetch(`${API_BASE}/rag/documents/upload`, {
      method: "POST",
      body: formData,
    }).then((r) => {
      if (!r.ok)
        return r
          .json()
          .then((e) => {
            throw new Error(e.detail || "Upload failed");
          });
      return r.json();
    });
  },

  /** 获取单个文档详情 */
  getDocument: (id: string) =>
    fetchJSON<Document>(`${API_BASE}/rag/documents/get`, { id }),

  /** 删除文档 */
  deleteDocument: (id: string) =>
    fetchJSON<{ detail: string }>(`${API_BASE}/rag/documents/delete`, { id }),

  /** RAG检索 */
  searchRag: (query: string, topK = 4) =>
    fetchJSON(`${API_BASE}/rag/search`, { query, top_k: topK }),

  /** 获取RAG统计信息 */
  getRagStats: () =>
    fetchJSON<{
      document_count: number;
      chunk_count: number;
      total_size_mb: number;
    }>(`${API_BASE}/rag/stats`),

  // ========== Agent管理 ==========

  /** 获取Agent列表 */
  listAgents: (skip = 0, limit = 50) =>
    fetchJSON<AgentConfig[]>(`${API_BASE}/agents/list`, { skip, limit }),

  /** 获取单个Agent详情 */
  getAgent: (id: string) =>
    fetchJSON<AgentConfig>(`${API_BASE}/agents/get`, { id }),

  /** 创建Agent */
  createAgent: (data: Partial<AgentConfig>) =>
    fetchJSON<AgentConfig>(`${API_BASE}/agents/create`, data),

  /** 更新Agent配置 */
  updateAgent: (agentId: string, data: Partial<AgentConfig>) =>
    fetchJSON<AgentConfig>(`${API_BASE}/agents/update`, {
      agent_id: agentId,
      ...data,
    }),

  /** 删除Agent */
  deleteAgent: (id: string) =>
    fetchJSON<{ detail: string }>(`${API_BASE}/agents/delete`, { id }),

  /** 获取可用工具列表 */
  listTools: () =>
    fetchJSON<{ tools: ToolInfo[] }>(`${API_BASE}/agents/tools`),

  // ========== 健康检查 ==========

  /** API健康检查 */
  healthCheck: () => fetchJSON<any>(`${API_BASE}/health`),

  // ========== 沙箱服务 ==========

  /** 沙箱健康检查 */
  sandboxHealth: () =>
    fetchJSON<{ status: string; reachable: boolean; latency_ms: number; error?: string }>(`${API_BASE}/sandbox/health`),

  /** 获取沙箱统计信息 */
  sandboxStats: () =>
    fetchJSON<{
      health: { reachable: boolean; latency_ms: number };
      dependencies: { count: number; packages: string[] };
      files: { count: number; names: string[] };
    }>(`${API_BASE}/sandbox/stats`),

  /**
   * 在沙箱中执行代码
   * @param code - 要执行的代码
   * @param language - 编程语言（默认Python3）
   */
  sandboxRun: (code: string, language?: string) =>
    fetchJSON<{ success: boolean; stdout: string; stderr: string; exit_code: number; elapsed_ms: number }>(
      `${API_BASE}/sandbox/run`,
      { code, language: language || "python3" }
    ),

  /** 获取沙箱已安装的依赖包列表 */
  sandboxListDeps: () =>
    fetchJSON<{ packages: string[]; count: number }>(`${API_BASE}/sandbox/dependencies/list`),

  /**
   * 在沙箱中安装依赖包
   * @param packages - 要安装的包名列表
   */
  sandboxInstallDeps: (packages: string[]) =>
    fetchJSON<{ message: string; requested: string[] }>(`${API_BASE}/sandbox/dependencies/install`, { packages }),

  // ========== 管理后台 ==========

  /** 获取管理后台仪表盘数据 */
  adminDashboard: () => fetchJSON<any>(`${API_BASE}/admin/dashboard`),

  /** 获取LLM配置列表 */
  adminLlmList: () =>
    fetchJSON<{ providers: any[]; default_provider: string; active_model: string }>(`${API_BASE}/admin/llm/list`),

  /** 更新LLM配置 */
  adminLlmUpdate: (provider: string, data: Record<string, any>) =>
    fetchJSON<any>(`${API_BASE}/admin/llm/update`, { provider, ...data }),

  /** 获取可用模型列表 */
  adminModels: () =>
    fetchJSON<{ providers: any[]; default_provider: string; active_model: string }>(`${API_BASE}/admin/models`),

  /** 获取管理后台文档列表 */
  adminRagDocuments: (skip = 0, limit = 50) =>
    fetchJSON<any[]>(`${API_BASE}/admin/rag/documents`, { skip, limit }),

  /**
   * 管理后台上传文档
   * 使用multipart/form-data格式
   */
  adminRagUpload: (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return fetch(`${API_BASE}/admin/rag/upload`, { method: "POST", body: formData }).then((r) => {
      if (!r.ok) return r.json().then((e) => { throw new Error(e.detail || "Upload failed"); });
      return r.json();
    });
  },

  /** 管理后台删除文档 */
  adminRagDelete: (id: string) =>
    fetchJSON<{ detail: string }>(`${API_BASE}/admin/rag/delete`, { doc_id: id }),

  /** 获取管理后台RAG统计信息 */
  adminRagStats: () =>
    fetchJSON<{ document_count: number; chunk_count: number }>(`${API_BASE}/admin/rag/stats`),
};