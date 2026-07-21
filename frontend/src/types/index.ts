/**
 * 全局类型定义文件
 * 
 * 说明：
 * - 定义应用中使用的所有TypeScript接口和类型
 * - 与后端API数据结构保持一致
 */

/**
 * 附件类型
 * 用于消息中的文件附件
 */
export interface Attachment {
  id: string;
  filename: string;
  url: string;
  type: string;
  size: number;
}

/**
 * 消息类型
 * 聊天消息的数据结构
 */
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

/**
 * 来源类型
 * RAG检索的文档片段信息
 */
export interface Source {
  chunk_id: string;
  document_id: string;
  filename: string;
  content: string;
  score: number;
}

/**
 * 会话类型
 * 对话会话的数据结构
 */
export interface Conversation {
  id: string;
  title: string;
  agent_id?: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  messages?: Message[];
}

/**
 * 文档类型
 * RAG知识库中的文档信息
 */
export interface Document {
  id: string;
  filename: string;
  file_type: string;
  file_size: number;
  chunk_count: number;
  status: string;
  created_at: string;
}

/**
 * Agent配置类型
 * AI助手的配置信息
 */
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

/**
 * 工具信息类型
 * Agent可使用的工具描述
 */
export interface ToolInfo {
  name: string;
  description: string;
  type: string;
}

/**
 * SSE事件类型（联合类型）
 * 后端推送的事件类型定义
 * 
 * 事件类型说明：
 * - conversation_id: 会话ID
 * - rag_context: RAG检索上下文
 * - token: 流式输出的文本片段
 * - tool_start: 工具调用开始
 * - agent_switch: Agent切换
 * - done: 响应完成
 * - error: 错误信息
 */
export type SSEEvent =
  | { type: "conversation_id"; conversation_id: string }
  | { type: "rag_context"; sources: Source[] }
  | { type: "token"; content: string }
  | { type: "tool_start"; name: string; args: Record<string, unknown> }
  | { type: "agent_switch"; to_agent: string; task: string }
  | { type: "done"; sources: Source[] }
  | { type: "error"; content: string };