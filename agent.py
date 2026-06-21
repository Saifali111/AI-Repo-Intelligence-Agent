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
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

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

def run_agentic_investigation(prompt, max_iterations=5, max_retries=2):
    messages = [HumanMessage(content=prompt)]

    for i in range(max_iterations):
        print(f"\n--- Iteration {i+1} ---")

        response = None
        for retry in range(max_retries):
            try:
                response = llm_with_tools.invoke(messages)
                break
            except Exception as e:
                print(f"LLM call failed (attempt {retry+1}/{max_retries}): {e}")
                if retry == max_retries - 1:
                    return "Investigation incomplete after retries — generation error persisted."

        messages.append(response)

        if not response.tool_calls:
            print("Agent finished investigating.")
            return response.content
        else:
            print(len(response.tool_calls))

        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            print(f"Calling: {tool_name}({tool_args})")

            try:
                result = tool_map[tool_name].invoke(tool_args)
            except Exception as e:
                result = f"Tool execution failed: {e}"

            print(f"Result: {str(result)[:150]}...")

            messages.append(ToolMessage(
                content=str(result),
                tool_call_id=tool_call["id"]
            ))

    return "Investigation stopped after max iterations — agent did not converge."

if __name__ == "__main__":
    test_prompt = """Investigate GitHub issue #65512 (14 upvotes, open 771 days).
        Check the comments first. Based on what you learn, decide whether to check 
        the timeline, search past briefings, or check a specific PR's reviews if 
        a PR number is mentioned. Stop when you have enough to give a clear final answer."""

    final_answer = run_agentic_investigation(test_prompt)
    print("\n=== FINAL AGENT ANALYSIS ===")
    print(final_answer)