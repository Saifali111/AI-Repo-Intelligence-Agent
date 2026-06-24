import os
from dotenv import load_dotenv
from typing import TypedDict, List, Annotated
import operator

from langgraph.graph import StateGraph, END
from langchain_groq import ChatGroq
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, ToolMessage, BaseMessage

from github_fetcher import get_issue_comments, get_issue_timeline, get_pr_reviews
from memory import retrieve_similar_briefings

load_dotenv()

# ---------------------------------------------------------------------------
# Tools (same as agent.py — the Investigator's capabilities)
# ---------------------------------------------------------------------------

@tool
def fetch_issue_comments(issue_number: int) -> str:
    """Get the comment history for a specific GitHub issue. Use this to understand discussion and root cause analysis."""
    comments = get_issue_comments(issue_number)
    if not comments:
        return "No comments found."
    return "\n".join([f"@{c['author']}: {c['body']}" for c in comments])

@tool
def fetch_issue_timeline(issue_number: int) -> str:
    """Get the event timeline for an issue — labels, cross-references, assignments."""
    events = get_issue_timeline(issue_number)
    if not events:
        return "No timeline events found."
    return "\n".join([f"{e['event']} at {e['created_at']}" for e in events])

@tool
def fetch_pr_reviews(pr_number: int) -> str:
    """Get review comments and approval status for a specific PR."""
    reviews = get_pr_reviews(pr_number)
    if not reviews:
        return "No reviews found."
    return "\n".join([f"@{r['author']} ({r['state']}): {r['body']}" for r in reviews])

@tool
def search_past_briefings(query: str) -> str:
    """Search memory for similar past situations or briefings."""
    results = retrieve_similar_briefings(query, limit=3)
    if not results:
        return "No similar past situations found."
    output = []
    for briefing_text, created_at, similarity in results:
        if similarity > 0.5:
            output.append(f"{created_at.strftime('%B %d')}: {briefing_text}")
    return "\n".join(output) if output else "No strongly relevant history found."

tools = [fetch_issue_comments, fetch_issue_timeline, fetch_pr_reviews, search_past_briefings]
tool_map = {t.name: t for t in tools}

llm = ChatGroq(model="llama-3.3-70b-versatile", api_key=os.getenv("GROQ_API_KEY"))
llm_with_tools = llm.bind_tools(tools)

# ---------------------------------------------------------------------------
# Shared state passed between graph nodes
# ---------------------------------------------------------------------------

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    investigation_prompt: str
    final_answer: str
    critic_feedback_history: Annotated[List[str], operator.add]  # episodic memory buffer
    approved: bool
    retry_count: int


INVESTIGATOR_SYSTEM_PROMPT = """You are investigating a GitHub issue using the ReAct framework.

For each step, follow this format:
Thought: explain your reasoning, including reflection on the previous observation if one exists.
Then call the appropriate tool if needed.

CRITICAL GROUNDING RULE: Before claiming a "recurring pattern," you must be
able to point to at least TWO separate, distinct historical occurrences in
your Observations. If you cannot cite two distinct pieces of evidence, you
MUST say "insufficient evidence for a recurring pattern" instead.

Only stop calling tools when your Thought concludes you have sufficient
evidence to answer."""


CRITIC_SYSTEM_PROMPT = """You are a strict evaluator. Check if the 
investigator's final answer is supported by the Observations in the 
transcript below.

Reject ONLY if a specific claim (e.g. "recurring pattern," "similar 
issue," "related to X") is NOT backed by at least two distinct, explicit 
pieces of evidence in the Observations.

A cautious conclusion like "insufficient evidence" or "isolated issue" 
is itself correct and should be APPROVED — do not reject for phrasing, 
style, or completeness.

Respond in this exact format:
VERDICT: APPROVED or REJECTED
REASON: [cite the specific Observation supporting or contradicting the claim]
FEEDBACK: [only if REJECTED — what specifically to fix]"""


def investigator_node(state: AgentState) -> dict:
    """Runs one full ReAct loop (multi-iteration) and produces a final answer.

    On retry, reads the FULL episodic memory buffer (every past rejection
    reason, not just the most recent one) so earlier lessons are never
    silently forgotten.
    """
    print("\n[INVESTIGATOR] Starting investigation...")

    feedback_history = state.get("critic_feedback_history", [])

    if feedback_history:
        numbered_feedback = "\n".join(
            [f"- Attempt {i + 1} was rejected because: {fb}" for i, fb in enumerate(feedback_history)]
        )
        retry_prompt = (
            f"{state['investigation_prompt']}\n\n"
            f"NOTE: Previous attempts were rejected for these reasons. "
            f"You must avoid repeating ANY of these mistakes, not just the most recent one:\n"
            f"{numbered_feedback}\n\n"
            f"Revise your investigation taking ALL of the above into account."
        )
        messages = [HumanMessage(content=INVESTIGATOR_SYSTEM_PROMPT + "\n\n" + retry_prompt)]
    else:
        messages = [HumanMessage(content=INVESTIGATOR_SYSTEM_PROMPT + "\n\n" + state["investigation_prompt"])]

    max_tool_iterations = 6
    for i in range(max_tool_iterations):
        try:
            response = llm_with_tools.invoke(messages)
        except Exception as e:
            print(f"[INVESTIGATOR] LLM call failed: {e}")
            continue

        messages.append(response)

        if response.content:
            print(f"[INVESTIGATOR] Thought: {response.content[:200]}")

        if not response.tool_calls:
            print("[INVESTIGATOR] Finished investigating.")
            return {
                "messages": messages,
                "final_answer": response.content,
                "retry_count": state.get("retry_count", 0) + 1
            }

        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            print(f"[INVESTIGATOR] Action: {tool_name}({tool_args})")
            try:
                result = tool_map[tool_name].invoke(tool_args)
            except Exception as e:
                result = f"Tool execution failed: {e}"
            print(f"[INVESTIGATOR] Observation: {str(result)[:150]}")
            messages.append(ToolMessage(content=str(result), tool_call_id=tool_call["id"]))

    return {
        "messages": messages,
        "final_answer": "Investigation incomplete — max tool iterations reached.",
        "retry_count": state.get("retry_count", 0) + 1
    }


def critic_node(state: AgentState) -> dict:
    """Reviews the investigator's final_answer against the gathered Observations.

    Appends its feedback (if rejected) to the episodic memory buffer via
    operator.add, so it accumulates across retries instead of overwriting.
    """
    print("\n[CRITIC] Reviewing investigator's claim...")

    transcript_parts = []
    for msg in state["messages"]:
        if isinstance(msg, HumanMessage):
            continue
        if isinstance(msg, ToolMessage):
            transcript_parts.append(f"Observation: {msg.content}")
        elif hasattr(msg, "content") and msg.content:
            transcript_parts.append(f"Thought/Answer: {msg.content}")

    transcript = "\n".join(transcript_parts)

    critic_prompt = (
        f"{CRITIC_SYSTEM_PROMPT}\n\n"
        f"--- INVESTIGATION TRANSCRIPT ---\n{transcript}\n\n"
        f"--- FINAL ANSWER TO EVALUATE ---\n{state['final_answer']}"
    )

    try:
        response = llm.invoke(critic_prompt)
        verdict_text = response.content
    except Exception as e:
        print(f"[CRITIC] LLM call failed: {e}")
        # fail safe: approve rather than loop forever on a critic failure
        return {"approved": True, "critic_feedback_history": []}

    print(f"[CRITIC] {verdict_text}")

    approved = "VERDICT: APPROVED" in verdict_text.upper()
    feedback = ""
    if not approved and "FEEDBACK:" in verdict_text:
        feedback = verdict_text.split("FEEDBACK:")[-1].strip()

    return {
        "approved": approved,
        "critic_feedback_history": [feedback] if feedback else []  # appends via operator.add
    }


def should_continue(state: AgentState) -> str:
    """Conditional edge: route back to investigator, or end."""
    if state.get("approved"):
        return "end"
    if state.get("retry_count", 0) >= 3:
        print("\n[GRAPH] Max retries reached. Ending with current answer.")
        return "end"
    return "retry"


# ---------------------------------------------------------------------------
# Build the graph
# ---------------------------------------------------------------------------

graph = StateGraph(AgentState)
graph.add_node("investigator", investigator_node)
graph.add_node("critic", critic_node)

graph.set_entry_point("investigator")
graph.add_edge("investigator", "critic")
graph.add_conditional_edges(
    "critic",
    should_continue,
    {
        "retry": "investigator",
        "end": END
    }
)

app = graph.compile()


def run_multi_agent_investigation(prompt: str) -> dict:
    initial_state = {
        "messages": [],
        "investigation_prompt": prompt,
        "final_answer": "",
        "critic_feedback_history": [],
        "approved": False,
        "retry_count": 0
    }
    result = app.invoke(initial_state)
    return result


if __name__ == "__main__":
    test_prompt = """Investigate GitHub issue #95015 — Turbopack windows 
Dev server crashes. Determine the root cause status and whether this is 
part of a recurring pattern with other Turbopack issues."""

    result = run_multi_agent_investigation(test_prompt)

    print("\n" + "=" * 50)
    print("FINAL APPROVED ANSWER")
    print("=" * 50)
    print(result["final_answer"])
    print(f"\nApproved: {result['approved']}")
    print(f"Retry count: {result['retry_count']}")
    print(f"\nEpisodic memory buffer (all rejection reasons accumulated):")
    for i, fb in enumerate(result["critic_feedback_history"]):
        print(f"  {i + 1}. {fb}")