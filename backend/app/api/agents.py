"""
Agent configuration CRUD endpoints — enterprise design.
All operations use POST with JSON body. No IDs in URL paths.
"""
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import AgentConfig
from app.schemas import (
    AgentConfigCreate,
    AgentConfigUpdate,
    AgentConfigOut,
    AgentListRequest,
    AgentGetRequest,
    AgentDeleteRequest,
)
from app.agent.tools import ALL_TOOLS

router = APIRouter()


# ---- Tools ----

@router.post("/tools")
async def list_available_tools():
    """List all available tools (POST — no params exposed)."""
    tools = [{
        "name": "rag",
        "description": "知识库检索：搜索上传的文档进行精准问答",
        "type": "rag",
    }, {
        "name": "delegate_to_agent",
        "description": "Agent 委托：将子任务委托给其他专业 Agent 处理（如知识库助手）",
        "type": "meta",
    }]
    for name, tool_obj in ALL_TOOLS.items():
        tools.append({
            "name": name,
            "description": tool_obj.description or "",
            "type": "function",
        })
    return {"tools": tools}


# ---- List ----

@router.post("/list", response_model=list[AgentConfigOut])
async def list_agents(
    request: AgentListRequest,
    db: AsyncSession = Depends(get_db),
):
    """List all agent configurations (pagination in POST body)."""
    result = await db.execute(
        select(AgentConfig)
        .order_by(AgentConfig.created_at.desc())
        .offset(request.skip)
        .limit(request.limit)
    )
    return result.scalars().all()


# ---- Create ----

@router.post("/create", response_model=AgentConfigOut)
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
        allow_delegation=request.allow_delegation,
    )
    db.add(agent)
    await db.commit()

    result = await db.execute(select(AgentConfig).where(AgentConfig.id == agent.id))
    return result.scalar_one()


# ---- Get ----

@router.post("/get", response_model=AgentConfigOut)
async def get_agent(
    request: AgentGetRequest,
    db: AsyncSession = Depends(get_db),
):
    """Get a single agent (id in POST body)."""
    result = await db.execute(select(AgentConfig).where(AgentConfig.id == request.id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


# ---- Update ----

@router.post("/update", response_model=AgentConfigOut)
async def update_agent(
    request: AgentConfigUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update an agent (agent_id + fields in POST body)."""
    result = await db.execute(
        select(AgentConfig).where(AgentConfig.id == request.agent_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    update_data = request.model_dump(exclude_unset=True)
    update_data.pop("agent_id", None)  # Remove the lookup key

    if update_data.get("is_default") is True:
        all_agents = await db.execute(
            select(AgentConfig).where(AgentConfig.is_default == True)
        )
        for a in all_agents.scalars():
            a.is_default = False

    for key, value in update_data.items():
        setattr(agent, key, value)

    await db.commit()

    result = await db.execute(select(AgentConfig).where(AgentConfig.id == request.agent_id))
    return result.scalar_one()


# ---- Delete ----

@router.post("/delete")
async def delete_agent(
    request: AgentDeleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """Delete an agent (id in POST body)."""
    result = await db.execute(select(AgentConfig).where(AgentConfig.id == request.id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if agent.is_protected:
        raise HTTPException(status_code=400, detail="Cannot delete a protected system agent")

    if agent.is_default:
        raise HTTPException(status_code=400, detail="Cannot delete the default agent")

    await db.delete(agent)
    await db.commit()
    return {"detail": "Agent deleted successfully"}
