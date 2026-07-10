"""
Agent configuration CRUD endpoints.
"""
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import AgentConfig
from app.schemas import (
    AgentConfigCreate,
    AgentConfigUpdate,
    AgentConfigOut,
)
from app.agent.tools import ALL_TOOLS

router = APIRouter()


@router.get("/tools")
async def list_available_tools():
    """List all available tools that can be enabled on an agent."""
    tools = []
    # RAG is a special "tool" handled by the graph, not a LangChain tool
    tools.append({
        "name": "rag",
        "description": "知识库检索：搜索上传的文档进行精准问答",
        "type": "rag",
    })
    for name, tool_obj in ALL_TOOLS.items():
        tools.append({
            "name": name,
            "description": tool_obj.description or "",
            "type": "function",
        })
    return {"tools": tools}


@router.get("", response_model=list[AgentConfigOut])
@router.get("/", response_model=list[AgentConfigOut])
async def list_agents(db: AsyncSession = Depends(get_db)):
    """List all agent configurations."""
    result = await db.execute(
        select(AgentConfig).order_by(AgentConfig.created_at.desc())
    )
    return result.scalars().all()


@router.post("", response_model=AgentConfigOut)
@router.post("/", response_model=AgentConfigOut)
async def create_agent(
    request: AgentConfigCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new agent configuration."""
    agent = AgentConfig(
        id=str(uuid4()),
        name=request.name,
        description=request.description,
        system_prompt=request.system_prompt,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        enabled_tools=request.enabled_tools,
        rag_top_k=request.rag_top_k,
        rag_similarity_threshold=request.rag_similarity_threshold,
    )
    db.add(agent)
    await db.commit()

    result = await db.execute(select(AgentConfig).where(AgentConfig.id == agent.id))
    return result.scalar_one()


@router.get("/{agent_id}", response_model=AgentConfigOut)
async def get_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    """Get a single agent configuration."""
    result = await db.execute(select(AgentConfig).where(AgentConfig.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.put("/{agent_id}", response_model=AgentConfigOut)
async def update_agent(
    agent_id: str,
    request: AgentConfigUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update an agent configuration."""
    result = await db.execute(select(AgentConfig).where(AgentConfig.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    update_data = request.model_dump(exclude_unset=True)

    # Handle is_default: only one agent can be default
    if update_data.get("is_default") is True:
        # Unset all other defaults
        all_agents = await db.execute(select(AgentConfig).where(AgentConfig.is_default == True))
        for a in all_agents.scalars():
            a.is_default = False

    for key, value in update_data.items():
        setattr(agent, key, value)

    await db.commit()

    result = await db.execute(select(AgentConfig).where(AgentConfig.id == agent_id))
    return result.scalar_one()


@router.delete("/{agent_id}")
async def delete_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    """Delete an agent configuration."""
    result = await db.execute(select(AgentConfig).where(AgentConfig.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if agent.is_default:
        raise HTTPException(status_code=400, detail="Cannot delete the default agent")

    await db.delete(agent)
    await db.commit()
    return {"detail": "Agent deleted successfully"}
