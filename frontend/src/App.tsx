import { useState, useEffect, useCallback, lazy, Suspense } from "react";
import { createBrowserRouter, RouterProvider, useNavigate, useParams, useLocation } from "react-router-dom";
import { Sidebar } from "./components/Sidebar";
import { ChatInterface } from "./components/ChatInterface";
import { useChat } from "./hooks/useChat";
import { api } from "./api/client";
import { Toaster } from "@/components/ui/sonner";
import type { Conversation, AgentConfig, Attachment } from "./types";

// Lazy-load non-critical pages — reduces initial bundle by ~350KB
const DocumentUpload = lazy(() =>
  import("./components/DocumentUpload").then(m => ({ default: m.DocumentUpload }))
);
const Settings = lazy(() =>
  import("./components/Settings").then(m => ({ default: m.Settings }))
);
const AdminPage = lazy(() =>
  import("./components/AdminPage").then(m => ({ default: m.AdminPage }))
);

/* ================================================================
   Main Chat Layout (handles all non-admin routes)
   ================================================================ */
function ChatLayout() {
  const navigate = useNavigate();
  const location = useLocation();

  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [agents, setAgents] = useState<AgentConfig[]>([]);
  const [showDocuments, setShowDocuments] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showSidebar, setShowSidebar] = useState(false);
  const [activeAgent, setActiveAgent] = useState<AgentConfig | null>(null);
  const [useRag, setUseRag] = useState(true);
  const [modelProvider, setModelProvider] = useState<string | null>(null);
  const [availableProviders, setAvailableProviders] = useState<any[]>([]);
  const [sandboxOnline, setSandboxOnline] = useState<boolean | null>(null); // null=checking, true=online, false=offline

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
    const hash = window.location.hash.slice(1);
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
    api.adminModels().then((r) => setAvailableProviders(r.providers)).catch(() => {});
    // Check sandbox health (non-blocking)
    api.sandboxHealth().then((h) => setSandboxOnline(h.reachable)).catch(() => setSandboxOnline(false));
  }, [loadConversations, loadAgents]);

  const handleCloseSettings = useCallback(() => {
    setShowSettings(false);
    loadAgents();
  }, [loadAgents]);

  const handleSwitchAgent = useCallback(
    (agent: AgentConfig) => {
      setActiveAgent(agent);
      setUseRag(agent.enabled_tools.includes("rag"));
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
          onOpenAdmin={() => navigate("/admin/dashboard")}
          sandboxOnline={sandboxOnline}
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
              onOpenAdmin={() => { navigate("/admin/dashboard"); setShowSidebar(false); }}
              onClose={() => setShowSidebar(false)}
              sandboxOnline={sandboxOnline}
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
          onOpenAdmin={() => navigate("/admin/dashboard")}
        />
      </div>

      {/* Modals */}
      <Toaster />
      <Suspense fallback={null}>
        {showDocuments && <DocumentUpload onClose={() => setShowDocuments(false)} />}
        {showSettings && (
          <Settings
            onClose={handleCloseSettings}
            onAgentChange={(agent: AgentConfig | null) => {
              if (agent) {
                setActiveAgent(agent);
                setUseRag(agent.enabled_tools.includes("rag"));
              }
            }}
          />
        )}
      </Suspense>
    </div>
  );
}

/* ================================================================
   Admin Layout (wraps AdminPage at /admin/*)
   ================================================================ */
function AdminLayout() {
  const navigate = useNavigate();

  return (
    <div className="fixed inset-0 z-[1000]">
      <AdminPageWrapper onClose={() => navigate("/")} />
    </div>
  );
}

// Thin wrapper to avoid React.lazy issues with route components
function AdminPageWrapper({ onClose }: { onClose: () => void }) {
  return (
    <Suspense fallback={
      <div className="fixed inset-0 z-[1000] bg-gray-50 flex items-center justify-center">
        <div className="text-ds-500 text-sm">加载中...</div>
      </div>
    }>
      <AdminPage onClose={onClose} />
    </Suspense>
  );
}

/* ================================================================
   Router
   ================================================================ */
const router = createBrowserRouter([
  {
    path: "/admin",
    element: <AdminLayout />,
    children: [
      { index: true, element: <AdminRedirect /> },
      { path: "dashboard", element: <AdminPageRoute /> },
      { path: "rag", element: <AdminPageRoute /> },
      { path: "llm", element: <AdminPageRoute /> },
      { path: "tech", element: <AdminPageRoute /> },
    ],
  },
  {
    path: "*",
    element: <ChatLayout />,
  },
]);

/** Redirect /admin → /admin/dashboard */
function AdminRedirect() {
  const navigate = useNavigate();
  useEffect(() => { navigate("/admin/dashboard", { replace: true }); }, [navigate]);
  return null;
}

/** Placeholder — AdminPage renders itself via the layout */
function AdminPageRoute() {
  return null;
}

export default function App() {
  return (
    <RouterProvider router={router} />
  );
}
