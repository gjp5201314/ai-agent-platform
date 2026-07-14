import type {
  Conversation,
  Document,
  AgentConfig,
  ToolInfo,
  SSEEvent,
  Attachment,
} from "../types";

const API_BASE = "/api/v1";

// ============================================================
//  Security: all operations use POST with JSON body.
//  No IDs, tokens, or query params ever appear in URLs.
// ============================================================

// ---- Generic fetch helper ----

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

// ---- Chat (SSE streaming) ----

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
          // Ignore malformed lines
        }
      }
    }
  }
}

// ============================================================
//  API surface — all POST, all JSON body
// ============================================================

export const api = {
  // Chat
  streamChat,

  // File upload for chat attachments (multipart — required for file binary)
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

  // ---- Conversations (all POST body) ----

  listConversations: (skip = 0, limit = 50) =>
    fetchJSON<Conversation[]>(`${API_BASE}/conversations/list`, { skip, limit }),

  getConversation: (id: string) =>
    fetchJSON<Conversation>(`${API_BASE}/conversations/get`, { id }),

  createConversation: (title: string, agentId?: string) =>
    fetchJSON<Conversation>(`${API_BASE}/conversations/create`, {
      title,
      agent_id: agentId ?? null,
    }),

  deleteConversation: (id: string) =>
    fetchJSON<{ detail: string }>(`${API_BASE}/conversations/delete`, { id }),

  updateTitle: (conversationId: string, title: string) =>
    fetchJSON<{ detail: string }>(`${API_BASE}/conversations/update-title`, {
      conversation_id: conversationId,
      title,
    }),

  // ---- Documents / RAG (all POST body) ----

  listDocuments: (skip = 0, limit = 50) =>
    fetchJSON<Document[]>(`${API_BASE}/rag/documents/list`, { skip, limit }),

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

  getDocument: (id: string) =>
    fetchJSON<Document>(`${API_BASE}/rag/documents/get`, { id }),

  deleteDocument: (id: string) =>
    fetchJSON<{ detail: string }>(`${API_BASE}/rag/documents/delete`, { id }),

  searchRag: (query: string, topK = 4) =>
    fetchJSON(`${API_BASE}/rag/search`, { query, top_k: topK }),

  getRagStats: () =>
    fetchJSON<{
      document_count: number;
      chunk_count: number;
      total_size_mb: number;
    }>(`${API_BASE}/rag/stats`),

  // ---- Agents (all POST body) ----

  listAgents: (skip = 0, limit = 50) =>
    fetchJSON<AgentConfig[]>(`${API_BASE}/agents/list`, { skip, limit }),

  getAgent: (id: string) =>
    fetchJSON<AgentConfig>(`${API_BASE}/agents/get`, { id }),

  createAgent: (data: Partial<AgentConfig>) =>
    fetchJSON<AgentConfig>(`${API_BASE}/agents/create`, data),

  updateAgent: (agentId: string, data: Partial<AgentConfig>) =>
    fetchJSON<AgentConfig>(`${API_BASE}/agents/update`, {
      agent_id: agentId,
      ...data,
    }),

  deleteAgent: (id: string) =>
    fetchJSON<{ detail: string }>(`${API_BASE}/agents/delete`, { id }),

  listTools: () =>
    fetchJSON<{ tools: ToolInfo[] }>(`${API_BASE}/agents/tools`),

  // ---- Health ----

  healthCheck: () => fetchJSON<any>(`${API_BASE}/health`),

  // ---- Admin ----

  adminDashboard: () => fetchJSON<any>(`${API_BASE}/admin/dashboard`),

  adminLlmList: () =>
    fetchJSON<{ providers: any[]; default_provider: string; active_model: string }>(`${API_BASE}/admin/llm/list`),

  adminLlmUpdate: (provider: string, data: Record<string, any>) =>
    fetchJSON<any>(`${API_BASE}/admin/llm/update`, { provider, ...data }),

  adminModels: () =>
    fetchJSON<{ providers: any[]; default_provider: string; active_model: string }>(`${API_BASE}/admin/models`),

  adminRagDocuments: (skip = 0, limit = 50) =>
    fetchJSON<any[]>(`${API_BASE}/admin/rag/documents`, { skip, limit }),

  adminRagUpload: (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return fetch(`${API_BASE}/admin/rag/upload`, { method: "POST", body: formData }).then((r) => {
      if (!r.ok) return r.json().then((e) => { throw new Error(e.detail || "Upload failed"); });
      return r.json();
    });
  },

  adminRagDelete: (id: string) =>
    fetchJSON<{ detail: string }>(`${API_BASE}/admin/rag/delete`, { doc_id: id }),

  adminRagStats: () =>
    fetchJSON<{ document_count: number; chunk_count: number }>(`${API_BASE}/admin/rag/stats`),
};
