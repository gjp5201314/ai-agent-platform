/**
 * 应用主入口组件
 * 
 * 功能说明：
 * 1. 定义应用的路由结构（聊天页面 + 管理后台）
 * 2. 管理全局状态（会话列表、Agent配置、设置面板等）
 * 3. 实现会话持久化（通过URL hash）
 * 4. 懒加载非核心页面（文档上传、设置、管理后台）
 */

import { useState, useEffect, useCallback, lazy, Suspense } from "react";
import { createBrowserRouter, RouterProvider, useNavigate, useParams, useLocation } from "react-router-dom";
import { Sidebar } from "./components/Sidebar";
import { ChatInterface } from "./components/ChatInterface";
import { useChat } from "./hooks/useChat";
import { api } from "./api/client";
import { Toaster } from "@/components/ui/sonner";
import type { Conversation, AgentConfig, Attachment } from "./types";

/**
 * 懒加载非关键页面组件
 * 优势：减少初始包体积约350KB，提升首屏加载速度
 */
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
   聊天页面布局组件
   处理所有非管理后台的路由（聊天、设置、文档上传等）
   ================================================================ */
function ChatLayout() {
  const navigate = useNavigate();
  const location = useLocation();

  // ========== 状态管理 ==========
  
  /** 会话列表 */
  const [conversations, setConversations] = useState<Conversation[]>([]);
  
  /** Agent配置列表 */
  const [agents, setAgents] = useState<AgentConfig[]>([]);
  
  /** 文档上传弹窗显示状态 */
  const [showDocuments, setShowDocuments] = useState(false);
  
  /** 设置弹窗显示状态 */
  const [showSettings, setShowSettings] = useState(false);
  
  /** 移动端侧边栏显示状态 */
  const [showSidebar, setShowSidebar] = useState(false);
  
  /** 当前激活的Agent */
  const [activeAgent, setActiveAgent] = useState<AgentConfig | null>(null);
  
  /** 是否启用RAG（检索增强生成） */
  const [useRag, setUseRag] = useState(true);
  
  /** 当前选择的模型提供商 */
  const [modelProvider, setModelProvider] = useState<string | null>(null);
  
  /** 可用的模型提供商列表 */
  const [availableProviders, setAvailableProviders] = useState<any[]>([]);
  
  /** 沙箱服务状态（null=检测中, true=在线, false=离线） */
  const [sandboxOnline, setSandboxOnline] = useState<boolean | null>(null);

  /** Mock 模式开关 */
  const [mockMode, setMockMode] = useState(false);

  // ========== 聊天逻辑Hook ==========
  const {
    messages,           // 消息列表
    isStreaming,        // 是否正在流式输出
    conversationId,     // 当前会话ID
    activeAgentId,      // 当前Agent ID
    sendMessage,        // 发送消息方法
    stopStreaming,      // 停止流式输出
    loadConversation,   // 加载会话
    newConversation,    // 创建新会话
  } = useChat();

  // ========== 生命周期钩子 ==========

  /**
   * 页面刷新时从URL hash恢复选中的会话
   * 实现会话的持久化和书签功能
   */
  useEffect(() => {
    const hash = window.location.hash.slice(1);
    if (hash) {
      loadConversation(hash);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /**
   * 同步会话ID到URL hash
   * 使会话可收藏、可刷新恢复
   */
  useEffect(() => {
    if (conversationId) {
      window.location.hash = conversationId;
    } else {
      if (window.location.hash) {
        history.replaceState(null, "", window.location.pathname + window.location.search);
      }
    }
  }, [conversationId]);

  // ========== 数据加载方法 ==========

  /**
   * 加载会话列表
   */
  const loadConversations = useCallback(async () => {
    try {
      const convs = await api.listConversations();
      setConversations(convs);
    } catch (err) {
      console.error("Failed to load conversations:", err);
    }
  }, []);

  /**
   * 加载Agent配置列表
   * 自动选择默认Agent或第一个Agent
   */
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

  /**
   * 初始化加载：会话列表、Agent列表、模型提供商、沙箱健康检查
   */
  useEffect(() => {
    loadConversations();
    loadAgents();
    api.adminModels().then((r) => setAvailableProviders(r.providers)).catch(() => {});
    api.sandboxHealth().then((h) => setSandboxOnline(h.reachable)).catch(() => setSandboxOnline(false));
  }, [loadConversations, loadAgents]);

  // ========== 事件处理方法 ==========

  /**
   * 关闭设置弹窗并重新加载Agent配置
   */
  const handleCloseSettings = useCallback(() => {
    setShowSettings(false);
    loadAgents();
  }, [loadAgents]);

  /**
   * 切换Agent
   * 自动更新RAG启用状态并创建新会话
   */
  const handleSwitchAgent = useCallback(
    (agent: AgentConfig) => {
      setActiveAgent(agent);
      setUseRag(agent.enabled_tools.includes("rag"));
      newConversation();
    },
    [newConversation]
  );

  /**
   * 发送消息
   * @param message - 消息内容
   * @param attachments - 附件列表
   */
  const handleSend = useCallback(
    async (message: string, attachments: Attachment[] = []) => {
      await sendMessage(message, activeAgent?.id || null, useRag, modelProvider, attachments, mockMode);
      // Brief delay for backend post-stream DB persistence
      setTimeout(loadConversations, 300);
    },
    [sendMessage, activeAgent, useRag, modelProvider, loadConversations, mockMode]
  );

  /**
   * 选择会话
   */
  const handleSelectConversation = useCallback(
    (id: string) => {
      loadConversation(id);
      setShowSidebar(false);
    },
    [loadConversation]
  );

  /**
   * 删除会话
   */
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

  /**
   * 创建新会话
   */
  const handleNewConversation = useCallback(() => {
    newConversation();
    setShowSidebar(false);
  }, [newConversation]);

  // ========== 渲染 ==========
  return (
    <div className="flex h-screen overflow-hidden">
      {/* 桌面端侧边栏 - 固定显示 */}
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

      {/* 移动端侧边栏 - 弹窗覆盖层 */}
      {showSidebar && (
        <div className="fixed inset-0 z-40 lg:hidden">
          {/* 背景遮罩 */}
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setShowSidebar(false)} />
          {/* 侧边栏内容 */}
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

      {/* 主聊天区域 */}
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
          mockMode={mockMode}
          onToggleMockMode={() => setMockMode(!mockMode)}
        />
      </div>

      {/* 弹窗组件 */}
      <Toaster />
      <Suspense fallback={null}>
        {/* 文档上传弹窗 */}
        {showDocuments && <DocumentUpload onClose={() => setShowDocuments(false)} />}
        {/* 设置弹窗 */}
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
   管理后台布局组件
   处理 /admin/* 路由
   ================================================================ */
function AdminLayout() {
  const navigate = useNavigate();

  return (
    <div className="fixed inset-0 z-[1000]">
      <AdminPageWrapper onClose={() => navigate("/")} />
    </div>
  );
}

/**
 * AdminPage包装器
 * 避免React.lazy与路由组件的兼容性问题
 */
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
   路由配置
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

/**
 * 重定向组件：/admin → /admin/dashboard
 */
function AdminRedirect() {
  const navigate = useNavigate();
  useEffect(() => { navigate("/admin/dashboard", { replace: true }); }, [navigate]);
  return null;
}

/**
 * 占位组件：AdminPage通过AdminLayout自行渲染
 */
function AdminPageRoute() {
  return null;
}

/**
 * 应用根组件
 * 提供路由上下文
 */
export default function App() {
  return (
    <RouterProvider router={router} />
  );
}