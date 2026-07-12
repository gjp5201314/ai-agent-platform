// Type definitions

export interface Attachment {
  id: string;
  filename: string;
  url: string;
  type: string;
  size: number;
}

export interface Message {
  id?: number;
  role: "user" | "assistant" | "tool" | "system";
  content: string;
  metadata?: {
    sources?: Source[];
    attachments?: Attachment[];
    [key: string]: unknown;
  };
  created_at?: string;
}

export interface Source {
  chunk_id: string;
  document_id: string;
  filename: string;
  content: string;
  score: number;
}

export interface Conversation {
  id: string;
  title: string;
  agent_id?: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  messages?: Message[];
}

export interface Document {
  id: string;
  filename: string;
  file_type: string;
  file_size: number;
  chunk_count: number;
  status: string;
  created_at: string;
}

export interface AgentConfig {
  id: string;
  name: string;
  description: string;
  system_prompt: string;
  temperature: number;
  max_tokens: number;
  enabled_tools: string[];
  rag_top_k: number;
  rag_similarity_threshold: number;
  is_default?: boolean;
  allow_delegation?: boolean;
}

export interface ToolInfo {
  name: string;
  description: string;
  type: string;
}

// SSE event types from the backend
export type SSEEvent =
  | { type: "conversation_id"; conversation_id: string }
  | { type: "rag_context"; sources: Source[] }
  | { type: "token"; content: string }
  | { type: "tool_start"; name: string; args: Record<string, unknown> }
  | { type: "agent_switch"; to_agent: string; task: string }
  | { type: "done"; sources: Source[] }
  | { type: "error"; content: string };
