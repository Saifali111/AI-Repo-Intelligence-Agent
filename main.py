"""
FastAPI wrapper around the DevPulse pipeline.

This turns your existing scripts (briefing_generator.py, multi_agent.py)
into HTTP endpoints that Cloud Run (or any server) can call — either
manually, or triggered by Cloud Scheduler for daily automation.

Run locally first to confirm everything works before containerizing:
    uvicorn main:app --reload --port 8080
"""

import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from briefing_generator import generate_briefing
from multi_agent import run_multi_agent_investigation

app = FastAPI(title="DevPulse API", version="1.0")


@app.get("/")
def root():
    """Basic health check — confirms the service is up."""
    return {"status": "ok", "service": "devpulse"}


@app.get("/health")
def health():
    """
    Health check endpoint for Cloud Run / monitoring.
    Cloud Run pings this periodically to confirm the container is alive.
    """
    return {"status": "healthy"}


@app.post("/briefing/generate")
def trigger_briefing():
    """
    Runs the full daily pipeline: fetch GitHub data, rank, retrieve
    memory, generate briefing, store in memory, send to Slack.

    This is the endpoint Cloud Scheduler will call once a day.
    """
    try:
        briefing = generate_briefing()
        return {"status": "success", "briefing": briefing}
    except Exception as e:
        # surfaced as a real HTTP error so Cloud Scheduler/logs show failures clearly
        raise HTTPException(status_code=500, detail=f"Briefing generation failed: {e}")


class InvestigationRequest(BaseModel):
    prompt: str


@app.post("/investigate")
def trigger_investigation(request: InvestigationRequest):
    """
    Runs the multi-agent (Investigator + Critic) ReAct/Reflexion
    investigation on a specific prompt, e.g. a specific issue number.
    """
    try:
        result = run_multi_agent_investigation(request.prompt)
        return {
            "status": "success",
            "final_answer": result["final_answer"],
            "approved": result["approved"],
            "retry_count": result["retry_count"],
            "episodic_memory_buffer": result["critic_feedback_history"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Investigation failed: {e}")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))  # Cloud Run injects PORT env var
    uvicorn.run(app, host="0.0.0.0", port=port)
