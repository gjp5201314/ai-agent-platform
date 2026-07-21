"""
================================================================================
AgentState — LangGraph 状态定义（前端必读）
================================================================================

这个文件定义了在整个 Agent 流程中流转的核心状态对象。
可以把它理解为"整个 Agent 对话会话的上下文快照"——就像 Redux 的 store，
每个节点(node)都会读取它、更新它，然后传递给下一个节点。

对前端开发者来说，关键概念：
-------------------------------------
LangGraph 的工作方式类似于"状态机 + 流水线"：
  1. 用户输入 → 创建初始 AgentState（包含消息、配置、工具列表等）
  2. 状态对象依次流过各个节点（rag_node → agent_node → tools_node → ...）
  3. 每个节点只返回它想要更新的字段（部分更新），LangGraph 自动合并
  4. 最终状态中的 messages 字段包含完整的 AI 回复

TypedDict 是 Python 的类型提示方式，定义了字典中必须有哪些键以及各自的类型。
"""
from typing import Annotated, TypedDict, List, Optional, Any
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """
    LangGraph 节点之间流转的状态对象。

    前端关注点：
    - messages: 对话历史，最终一条 AIMessage 就是给用户展示的回复
    - retrieved_context: 知识库检索结果，前端可用来展示"参考来源"
    - tools_enabled: 当前轮次启用的工具，决定了 API 发给 LLM 的工具列表
    - use_rag: 是否需要先检索知识库再回答
    - agent_config: 从管理后台配置的 Agent 参数（系统提示词、温度等）
    - iteration: 安全计数器，防止无限循环（最多 10 轮）

    Attributes:
        messages:           对话历史（LangGraph 的消息 reducer 自动追加新消息）
        retrieved_context:  与当前问题相关的知识库文档片段（RAG 检索结果）
        tools_enabled:      当前轮次 Agent 可使用的工具名称列表
        use_rag:            是否启用知识库检索
        agent_config:       AgentConfig 的配置字段（system_prompt, temperature 等）
        iteration:          安全计数器，防止 Agent 陷入无限工具调用循环
    """
    messages: Annotated[list, add_messages]
    retrieved_context: List[dict]
    tools_enabled: List[str]
    use_rag: bool
    agent_config: dict
    iteration: int
