import type {
  Conversation,
  Document,
  AgentConfig,
  ToolInfo,
  SSEEvent,
  Attachment,
} from "../types";

const API_BASE = "/api";

// ---- Generic fetch helper ----

async function fetchJSON<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
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
  attachments: Attachment[] = []
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

// ---- Conversations ----

export const api = {
  // Chat
  streamChat,

  // File upload for chat attachments
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

  // Conversations
  listConversations: () =>
    fetchJSON<Conversation[]>(`${API_BASE}/conversations`),

  getConversation: (id: string) =>
    fetchJSON<Conversation>(`${API_BASE}/conversations/${id}`),

  createConversation: (title: string, agentId?: string) =>
    fetchJSON<Conversation>(`${API_BASE}/conversations`, {
      method: "POST",
      body: JSON.stringify({ title, agent_id: agentId }),
    }),

  deleteConversation: (id: string) =>
    fetchJSON<{ detail: string }>(`${API_BASE}/conversations/${id}`, {
      method: "DELETE",
    }),

  updateTitle: (id: string, title: string) =>
    fetchJSON<{ detail: string }>(
      `${API_BASE}/conversations/${id}/title?title=${encodeURIComponent(title)}`,
      { method: "PATCH" }
    ),

  // Documents / RAG
  listDocuments: () =>
    fetchJSON<Document[]>(`${API_BASE}/rag/documents`),

  uploadDocument: (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return fetch(`${API_BASE}/rag/upload`, {
      method: "POST",
      body: formData,
    }).then((r) => {
      if (!r.ok) return r.json().then((e) => { throw new Error(e.detail || "Upload failed"); });
      return r.json();
    });
  },

  deleteDocument: (id: string) =>
    fetchJSON<{ detail: string }>(`${API_BASE}/rag/documents/${id}`, {
      method: "DELETE",
    }),

  getRagStats: () =>
    fetchJSON<{
      document_count: number;
      chunk_count: number;
      total_size_mb: number;
    }>(`${API_BASE}/rag/stats`),

  // Agents
  listAgents: () => fetchJSON<AgentConfig[]>(`${API_BASE}/agents`),

  getAgent: (id: string) =>
    fetchJSON<AgentConfig>(`${API_BASE}/agents/${id}`),

  createAgent: (data: Partial<AgentConfig>) =>
    fetchJSON<AgentConfig>(`${API_BASE}/agents`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  updateAgent: (id: string, data: Partial<AgentConfig>) =>
    fetchJSON<AgentConfig>(`${API_BASE}/agents/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  deleteAgent: (id: string) =>
    fetchJSON<{ detail: string }>(`${API_BASE}/agents/${id}`, {
      method: "DELETE",
    }),

  listTools: () =>
    fetchJSON<{ tools: ToolInfo[] }>(`${API_BASE}/agents/tools`),

  // Health
  healthCheck: () => fetchJSON<any>(`${API_BASE}/health`),
};
