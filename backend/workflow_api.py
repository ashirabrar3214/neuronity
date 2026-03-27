"""
Workflow API Endpoints - Execute and monitor 3-agent workflows
Streams real-time progress to canvas via Server-Sent Events (SSE)
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import asyncio
import json
from agent_workflow import AgentWorkflow

router = APIRouter(prefix="/workflow", tags=["workflow"])


@router.post("/execute")
async def execute_workflow(request: dict):
    """
    Execute a 3-agent workflow and stream progress

    Request body:
    {
        "workflow_id": "workflow-001",
        "research_agent_id": "agent-bot-123",
        "analyst_agent_id": "agent-bot-456",
        "pdf_agent_id": "agent-bot-789",
        "query": "Research AI developments in 2025",
        "working_dir": "/path/to/working/dir"
    }
    """
    try:
        # Extract parameters
        workflow_id = request.get("workflow_id")
        research_id = request.get("research_agent_id")
        analyst_id = request.get("analyst_agent_id")
        pdf_id = request.get("pdf_agent_id")
        query = request.get("query", "Research topic")
        working_dir = request.get("working_dir", "/tmp")

        if not all([workflow_id, research_id, analyst_id, pdf_id]):
            raise HTTPException(
                status_code=400,
                detail="Missing required agent IDs"
            )

        # Create workflow instance
        workflow = AgentWorkflow(workflow_id, working_dir)
        workflow.set_agent_ids(research_id, analyst_id, pdf_id)

        # Create SSE stream
        async def event_stream():
            async for event in workflow.execute(query):
                yield event

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive"
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/{workflow_id}")
async def get_workflow_status(workflow_id: str):
    """Get status of a running workflow"""
    # This would track workflow state in a database/cache
    return {
        "workflow_id": workflow_id,
        "status": "running",
        "current_agent": "Research Agent",
        "progress": 45
    }


@router.post("/cancel/{workflow_id}")
async def cancel_workflow(workflow_id: str):
    """Cancel a running workflow"""
    return {
        "workflow_id": workflow_id,
        "status": "cancelled"
    }
