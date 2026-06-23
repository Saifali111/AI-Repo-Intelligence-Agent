import os
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from langchain_groq import ChatGroq
from langchain_core.tools import tool
from typing import TypedDict, Annotated
import operator

from github_fetcher import (
    get_issue_comments, 
    get_issue_timeline, 
    get_pr_reviews,
    get_open_prs,
    get_open_issues,
    get_recent_workflow_runs,
    days_old
)
from memory import retrieve_similar_briefings, store_briefing
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage

load_dotenv()

# Define the tools the agent can call
@tool
def fetch_issue_comments(issue_number: int) -> str:
    """Get the comment history for a specific GitHub issue. Use this to understand discussion and root cause analysis."""
    comments = get_issue_comments(issue_number)
    if not comments:
        return "No comments found."
    return "\n".join([f"@{c['author']}: {c['body']}" for c in comments])

@tool
def fetch_issue_timeline(issue_number: int) -> str:
    """Get the event timeline for an issue — labels, cross-references, assignments. Use this to see if other PRs reference this issue."""
    events = get_issue_timeline(issue_number)
    if not events:
        return "No timeline events found."
    return "\n".join([f"{e['event']} at {e['created_at']}" for e in events])

@tool
def fetch_pr_reviews(pr_number: int) -> str:
    """Get review comments and approval status for a specific PR. Use this to understand why a PR may be stalled."""
    reviews = get_pr_reviews(pr_number)
    if not reviews:
        return "No reviews found."
    return "\n".join([f"@{r['author']} ({r['state']}): {r['body']}" for r in reviews])

@tool
def search_past_briefings(query: str) -> str:
    """Search memory for similar past situations or briefings. Use this to find historical patterns."""
    results = retrieve_similar_briefings(query, limit=3)
    if not results:
        return "No similar past situations found."
    output = []
    for briefing_text, created_at, similarity in results:
        if similarity > 0.5:
            output.append(f"{created_at.strftime('%B %d')}: {briefing_text}")
    return "\n".join(output) if output else "No strongly relevant history found."

tools = [fetch_issue_comments, fetch_issue_timeline, fetch_pr_reviews, search_past_briefings]

tool_map = {
    "fetch_issue_comments": fetch_issue_comments,
    "fetch_issue_timeline": fetch_issue_timeline,
    "fetch_pr_reviews": fetch_pr_reviews,
    "search_past_briefings": search_past_briefings
}

# Set up the LLM with tools bound
llm = ChatGroq(model="llama-3.3-70b-versatile", api_key=os.getenv("GROQ_API_KEY"))
llm_with_tools = llm.bind_tools(tools)

SYSTEM_PROMPT = """You are investigating a GitHub issue using the ReAct framework.

        For each step, you must follow this exact format:
        Thought: [explain your reasoning about what to do next, 
                including reflection on the previous observation if any]
        Then call the appropriate tool.

        After receiving a tool result (Observation), you MUST explicitly 
        reflect on it in your next Thought before deciding the next action.
        Only stop when your Thought concludes you have sufficient evidence 
        to answer, then provide your final answer instead of calling a tool.

        Grounding Rule: Verify that your thoughts are strictly supported by 
        the actual observations. Do not claim a recurring pattern unless you 
        see multiple separate historical occurrences of the problem.

        Avoid repeating a tool call with a nearly identical query if 
        you've already received that information. If a search returns 
        the same result as before, move to a different tool or conclude 
        your investigation instead of searching again.
        """

def run_agentic_investigation(prompt, max_iterations=10, max_retries=2):
    messages = [
        HumanMessage(content=SYSTEM_PROMPT + "\n\n" + prompt)
    ]
    iteration = 0

    while iteration < max_iterations:
        iteration += 1
        print(f"\n--- Iteration {iteration} ---")

        response = None
        for retry in range(max_retries):
            try:
                response = llm_with_tools.invoke(messages)
                break
            except Exception as e:
                print(f"LLM call failed (attempt {retry+1}/{max_retries}): {e}")
                if retry == max_retries - 1:
                    return "Investigation incomplete after retries."

        # print the model's reasoning text (the "Thought") if present
        if response.content:
            print(f"Thought: {response.content}")

        messages.append(response)

        if not response.tool_calls:
            print("Agent finished investigating.")
            return response.content

        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            print(f"Action: {tool_name}({tool_args})")

            try:
                result = tool_map[tool_name].invoke(tool_args)
            except Exception as e:
                result = f"Tool execution failed: {e}"

            print(f"Observation: {str(result)[:150]}...")

            messages.append(ToolMessage(
                content=str(result),
                tool_call_id=tool_call["id"]
            ))

    return "Investigation stopped after max iterations."

if __name__ == "__main__":
    test_prompt = """Investigate GitHub issue #94919 — App Router RSC render 
        tree retained per request causing a server memory leak. Determine the 
        root cause status and check if this is part of a recurring pattern."""

    final_answer = run_agentic_investigation(test_prompt)
    print("\n=== FINAL AGENT ANALYSIS ===")
    print(final_answer)