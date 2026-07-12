import { useState, useEffect, useCallback } from "react";
import { Sidebar } from "./components/Sidebar";
import { ChatInterface } from "./components/ChatInterface";
import { DocumentUpload } from "./components/DocumentUpload";
import { Settings } from "./components/Settings";
import { AdminPage } from "./components/AdminPage";
import { useChat } from "./hooks/useChat";
import { api } from "./api/client";
import { Toaster } from "@/components/ui/sonner";
import type { Conversation, AgentConfig, Attachment } from "./types";

export default function App() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [agents, setAgents] = useState<AgentConfig[]>([]);
  const [showDocuments, setShowDocuments] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showAdmin, setShowAdmin] = useState(false);
  const [showSidebar, setShowSidebar] = useState(false);
  const [activeAgent, setActiveAgent] = useState<AgentConfig | null>(null);
  const [useRag, setUseRag] = useState(true);
  const [modelProvider, setModelProvider] = useState<string | null>(null);
  const [availableProviders, setAvailableProviders] = useState<any[]>([]);

  const {
    messages,
    isStreaming,
    conversationId,
    activeAgentId,
    sendMessage,
    stopStreaming,
    loadConversation,
    newConversation,
  } = useChat();

  // ---- Restore selected conversation from URL hash on refresh ----
  useEffect(() => {
    const hash = window.location.hash.slice(1); // strip leading #
    if (hash) {
      loadConversation(hash);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---- Sync conversationId → URL hash (bookmarkable, refresh-safe) ----
  useEffect(() => {
    if (conversationId) {
      window.location.hash = conversationId;
    } else {
      // Clear hash when starting a fresh conversation
      if (window.location.hash) {
        history.replaceState(null, "", window.location.pathname + window.location.search);
      }
    }
  }, [conversationId]);

  const loadConversations = useCallback(async () => {
    try {
      const convs = await api.listConversations();
      setConversations(convs);
    } catch (err) {
      console.error("Failed to load conversations:", err);
    }
  }, []);

  const loadAgents = useCallback(async () => {
    try {
      const agentList = await api.listAgents();
      setAgents(agentList);
      const def = agentList.find((a) => a.is_default) || agentList[0];
      if (def && !activeAgent) {
        setActiveAgent(def);
        setUseRag(def.enabled_tools.includes("rag"));
      }
    } catch (err) {
      console.error("Failed to load agents:", err);
    }
  }, []);

  useEffect(() => {
    loadConversations();
    loadAgents();
    // Load available LLM models for the model selector
    api.adminModels().then((r) => setAvailableProviders(r.providers)).catch(() => {});
  }, [loadConversations, loadAgents]);

  // Refresh agents when Settings closes (user may have created/deleted agents)
  const handleCloseSettings = useCallback(() => {
    setShowSettings(false);
    loadAgents();
  }, [loadAgents]);

  const handleSwitchAgent = useCallback(
    (agent: AgentConfig) => {
      setActiveAgent(agent);
      setUseRag(agent.enabled_tools.includes("rag"));
      // Start a fresh conversation when switching agent
      newConversation();
    },
    [newConversation]
  );

  const handleSend = useCallback(
    (message: string, attachments: Attachment[] = []) => {
      sendMessage(message, activeAgent?.id || null, useRag, modelProvider, attachments);
      setTimeout(loadConversations, 500);
    },
    [sendMessage, activeAgent, useRag, modelProvider, loadConversations]
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
          agents={agents}
          activeAgent={activeAgent}
          activeId={conversationId}
          onSelect={handleSelectConversation}
          onNew={handleNewConversation}
          onDelete={handleDeleteConversation}
          onSwitchAgent={handleSwitchAgent}
          onOpenDocuments={() => setShowDocuments(true)}
          onOpenSettings={() => setShowSettings(true)}
          onOpenAdmin={() => setShowAdmin(true)}
        />
      </div>

      {/* Sidebar - mobile overlay */}
      {showSidebar && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setShowSidebar(false)} />
          <div className="absolute left-0 top-0 bottom-0">
            <Sidebar
              conversations={conversations}
              agents={agents}
              activeAgent={activeAgent}
              activeId={conversationId}
              onSelect={handleSelectConversation}
              onNew={handleNewConversation}
              onDelete={handleDeleteConversation}
              onSwitchAgent={handleSwitchAgent}
              onOpenDocuments={() => { setShowDocuments(true); setShowSidebar(false); }}
              onOpenSettings={() => { setShowSettings(true); setShowSidebar(false); }}
              onOpenAdmin={() => { setShowAdmin(true); setShowSidebar(false); }}
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
          activeAgent={activeAgent}
          activeAgentId={activeAgentId}
          agents={agents.map(a => ({ id: a.id, name: a.name }))}
          onSend={handleSend}
          onStop={stopStreaming}
          useRag={useRag}
          onToggleRag={() => setUseRag(!useRag)}
          onOpenSidebar={() => setShowSidebar(true)}
          modelProvider={modelProvider}
          onModelProviderChange={setModelProvider}
          onOpenAdmin={() => setShowAdmin(true)}
        />
      </div>

      {/* Modals */}
      <Toaster />
      {showDocuments && <DocumentUpload onClose={() => setShowDocuments(false)} />}
      {showAdmin && <AdminPage onClose={() => setShowAdmin(false)} />}
      {showSettings && (
        <Settings
          onClose={handleCloseSettings}
          onAgentChange={(agent) => {
            if (agent) {
              setActiveAgent(agent);
              setUseRag(agent.enabled_tools.includes("rag"));
            }
          }}
        />
      )}
    </div>
  );
}
