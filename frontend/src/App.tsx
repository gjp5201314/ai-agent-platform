import { useState, useEffect, useCallback } from "react";
import { Sidebar } from "./components/Sidebar";
import { ChatInterface } from "./components/ChatInterface";
import { DocumentUpload } from "./components/DocumentUpload";
import { Settings } from "./components/Settings";
import { useChat } from "./hooks/useChat";
import { api } from "./api/client";
import type { Conversation, AgentConfig } from "./types";

export default function App() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [showDocuments, setShowDocuments] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showSidebar, setShowSidebar] = useState(false);
  const [activeAgent, setActiveAgent] = useState<AgentConfig | null>(null);
  const [useRag, setUseRag] = useState(true);

  const {
    messages,
    isStreaming,
    conversationId,
    sendMessage,
    stopStreaming,
    loadConversation,
    newConversation,
  } = useChat();

  const loadConversations = useCallback(async () => {
    try {
      const convs = await api.listConversations();
      setConversations(convs);
    } catch (err) {
      console.error("Failed to load conversations:", err);
    }
  }, []);

  const loadDefaultAgent = useCallback(async () => {
    try {
      const agents = await api.listAgents();
      const def = agents.find((a) => a.is_default) || agents[0];
      if (def) {
        setActiveAgent(def);
        // Default to using RAG if the agent has it enabled
        setUseRag(def.enabled_tools.includes("rag"));
      }
    } catch (err) {
      console.error("Failed to load agent:", err);
    }
  }, []);

  useEffect(() => {
    loadConversations();
    loadDefaultAgent();
  }, [loadConversations, loadDefaultAgent]);

  const handleSend = useCallback(
    (message: string) => {
      sendMessage(message, activeAgent?.id || null, useRag);
      // Refresh conversation list after sending
      setTimeout(loadConversations, 500);
    },
    [sendMessage, activeAgent, useRag, loadConversations]
  );

  const handleSelectConversation = useCallback(
    (id: string) => {
      loadConversation(id);
      setShowSidebar(false);
    },
    [loadConversation]
  );

  const handleDeleteConversation = useCallback(
    async (id: string) => {
      try {
        await api.deleteConversation(id);
        await loadConversations();
        if (conversationId === id) {
          newConversation();
        }
      } catch (err) {
        alert(`删除失败: ${(err as Error).message}`);
      }
    },
    [conversationId, loadConversations, newConversation]
  );

  const handleNewConversation = useCallback(() => {
    newConversation();
    setShowSidebar(false);
  }, [newConversation]);

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar - desktop */}
      <div className="hidden lg:block flex-shrink-0">
        <Sidebar
          conversations={conversations}
          activeId={conversationId}
          onSelect={handleSelectConversation}
          onNew={handleNewConversation}
          onDelete={handleDeleteConversation}
          onOpenDocuments={() => setShowDocuments(true)}
          onOpenSettings={() => setShowSettings(true)}
        />
      </div>

      {/* Sidebar - mobile overlay */}
      {showSidebar && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/30" onClick={() => setShowSidebar(false)} />
          <div className="absolute left-0 top-0 bottom-0">
            <Sidebar
              conversations={conversations}
              activeId={conversationId}
              onSelect={handleSelectConversation}
              onNew={handleNewConversation}
              onDelete={handleDeleteConversation}
              onOpenDocuments={() => { setShowDocuments(true); setShowSidebar(false); }}
              onOpenSettings={() => { setShowSettings(true); setShowSidebar(false); }}
              onClose={() => setShowSidebar(false)}
            />
          </div>
        </div>
      )}

      {/* Main chat area */}
      <div className="flex-1 flex flex-col">
        <ChatInterface
          messages={messages}
          isStreaming={isStreaming}
          onSend={handleSend}
          onStop={stopStreaming}
          useRag={useRag}
          onToggleRag={() => setUseRag(!useRag)}
          onOpenSidebar={() => setShowSidebar(true)}
        />
      </div>

      {/* Modals */}
      {showDocuments && <DocumentUpload onClose={() => setShowDocuments(false)} />}
      {showSettings && (
        <Settings
          onClose={() => setShowSettings(false)}
          onAgentChange={(agent) => {
            setActiveAgent(agent);
            setUseRag(agent?.enabled_tools.includes("rag") ?? true);
          }}
        />
      )}
    </div>
  );
}
