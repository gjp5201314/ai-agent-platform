import { useState, useCallback, useRef } from "react";
import { api } from "../api/client";
import type { Message, Source, Attachment, SSEEvent } from "../types";

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [sources, setSources] = useState<Source[]>([]);
  const abortRef = useRef<AbortController | null>(null);

  const sendMessage = useCallback(
    async (content: string, agentId: string | null, useRag: boolean, modelProvider?: string | null, attachments: Attachment[] = []) => {
      // Add user message
      const userMsg: Message = {
        role: "user",
        content,
        metadata: attachments.length ? { attachments } : undefined,
      };
      setMessages((prev) => [...prev, userMsg]);
      setIsStreaming(true);
      setSources([]);

      // Add empty assistant message for streaming
      const assistantMsg: Message = { role: "assistant", content: "" };
      setMessages((prev) => [...prev, assistantMsg]);

      try {
        let fullResponse = "";
        let receivedSources: Source[] = [];

        for await (const event of api.streamChat(content, conversationId, agentId, useRag, attachments, modelProvider || undefined)) {
          switch (event.type) {
            case "conversation_id":
              if (event.conversation_id) {
                setConversationId(event.conversation_id);
              }
              break;
            case "rag_context":
              receivedSources = event.sources;
              setSources(event.sources);
              break;
            case "token":
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
            case "done":
              if (event.sources.length) {
                receivedSources = event.sources;
                setSources(event.sources);
              }
              break;
            case "error":
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

  const stopStreaming = useCallback(() => {
    abortRef.current?.abort();
    setIsStreaming(false);
  }, []);

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

  const newConversation = useCallback(() => {
    setMessages([]);
    setConversationId(null);
    setSources([]);
  }, []);

  return {
    messages,
    isStreaming,
    conversationId,
    sources,
    sendMessage,
    stopStreaming,
    loadConversation,
    newConversation,
  };
}
