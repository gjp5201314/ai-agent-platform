/**
 * 聊天逻辑自定义Hook
 * 
 * 功能说明：
 * 1. 管理聊天消息列表状态
 * 2. 处理流式响应（SSE）
 * 3. 管理会话ID和Agent切换
 * 4. 提供发送消息、停止生成、加载会话等方法
 */

import { useState, useCallback, useRef } from "react";
import { api } from "../api/client";
import type { Message, Source, Attachment, SSEEvent } from "../types";

export function useChat() {
  // ========== 状态管理 ==========
  
  /** 消息列表 */
  const [messages, setMessages] = useState<Message[]>([]);
  
  /** 是否正在流式输出 */
  const [isStreaming, setIsStreaming] = useState(false);
  
  /** 当前会话ID */
  const [conversationId, setConversationId] = useState<string | null>(null);
  
  /** RAG检索来源列表 */
  const [sources, setSources] = useState<Source[]>([]);
  
  /** 当前激活的Agent ID */
  const [activeAgentId, setActiveAgentId] = useState<string | null>(null);
  
  /** 用于取消请求的AbortController */
  const abortRef = useRef<AbortController | null>(null);

  /**
   * 发送消息
   * 
   * @param content - 消息内容
   * @param agentId - Agent ID（可选）
   * @param useRag - 是否启用RAG
   * @param modelProvider - 模型提供商（可选）
   * @param attachments - 附件列表
   */
  const sendMessage = useCallback(
    async (content: string, agentId: string | null, useRag: boolean, modelProvider?: string | null, attachments: Attachment[] = [], mockMode: boolean = false) => {
      // 添加用户消息到列表
      const userMsg: Message = {
        role: "user",
        content,
        metadata: attachments.length ? { attachments } : undefined,
      };
      setMessages((prev) => [...prev, userMsg]);
      setIsStreaming(true);
      setSources([]);

      // 添加空的AI消息占位符（用于流式输出）
      const assistantMsg: Message = { role: "assistant", content: "" };
      setMessages((prev) => [...prev, assistantMsg]);

      try {
        let fullResponse = "";
        let receivedSources: Source[] = [];

        // 处理SSE流式事件
        for await (const event of api.streamChat(content, conversationId, agentId, useRag, attachments, modelProvider || undefined, mockMode)) {
          switch (event.type) {
            case "conversation_id":
              // 接收到会话ID
              if (event.conversation_id) {
                setConversationId(event.conversation_id);
              }
              break;
            case "rag_context":
              // 接收到RAG检索上下文
              receivedSources = event.sources;
              setSources(event.sources);
              break;
            case "token":
              // 接收到文本片段，追加到AI消息
              fullResponse += event.content;
              setMessages((prev) => {
                const updated = [...prev];
                updated[updated.length - 1] = {
                  role: "assistant",
                  content: fullResponse,
                  metadata: receivedSources.length ? { sources: receivedSources } : {},
                };
                return updated;
              });
              break;
            case "tool_start":
              // 工具调用开始
              setMessages((prev) => {
                const updated = [...prev];
                updated[updated.length - 1] = {
                  ...updated[updated.length - 1],
                  content: fullResponse || "",
                  metadata: {
                    ...updated[updated.length - 1].metadata,
                    toolCall: event.name,
                  },
                };
                return updated;
              });
              break;
            case "agent_switch":
              // Agent切换
              setActiveAgentId(event.to_agent);
              break;
            case "done":
              // 响应完成
              if (event.sources.length) {
                receivedSources = event.sources;
                setSources(event.sources);
              }
              break;
            case "error":
              // 错误处理
              fullResponse = `\u26a0\ufe0f ${event.content}`;
              setMessages((prev) => {
                const updated = [...prev];
                updated[updated.length - 1] = {
                  role: "assistant",
                  content: fullResponse,
                };
                return updated;
              });
              break;
          }
        }
      } catch (err) {
        // 异常处理
        setMessages((prev) => {
          const updated = [...prev];
          if (updated.length > 0 && updated[updated.length - 1].role === "assistant") {
            updated[updated.length - 1] = {
              role: "assistant",
              content: `\u26a0\ufe0f 发送失败: ${(err as Error).message}`,
            };
          }
          return updated;
        });
      } finally {
        setIsStreaming(false);
      }
    },
    [conversationId]
  );

  /**
   * 停止流式生成
   */
  const stopStreaming = useCallback(() => {
    abortRef.current?.abort();
    setIsStreaming(false);
  }, []);

  /**
   * 加载指定会话
   * @param id - 会话ID
   */
  const loadConversation = useCallback(async (id: string) => {
    try {
      const conv = await api.getConversation(id);
      setConversationId(conv.id);
      setMessages(conv.messages || []);
      setSources([]);
    } catch (err) {
      console.error("Failed to load conversation:", err);
    }
  }, []);

  /**
   * 创建新会话
   */
  const newConversation = useCallback(() => {
    setMessages([]);
    setConversationId(null);
    setSources([]);
    setActiveAgentId(null);
  }, []);

  // 返回Hook接口
  return {
    messages,           // 消息列表
    isStreaming,        // 是否正在流式输出
    conversationId,     // 当前会话ID
    sources,            // RAG来源列表
    activeAgentId,      // 当前Agent ID
    sendMessage,        // 发送消息方法
    stopStreaming,      // 停止生成方法
    loadConversation,   // 加载会话方法
    newConversation,    // 创建新会话方法
  };
}