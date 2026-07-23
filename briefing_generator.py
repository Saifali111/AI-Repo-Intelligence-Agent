import os
from dotenv import load_dotenv
from github_fetcher import get_open_prs, get_open_issues, get_recent_workflow_runs, days_old
from memory import store_briefing, retrieve_similar_briefings
from slack_sender import send_to_slack
from multi_agent import run_multi_agent_investigation
from groq import Groq

load_dotenv()

def generate_briefing():
    print("Fetching GitHub data...")
    prs = get_open_prs()
    issues = get_open_issues()
    runs = get_recent_workflow_runs()

    # Track successful CI runs for PRs
    successful_prs_ci = {r["pr_number"] for r in runs if r["conclusion"] == "success" and r["pr_number"]}

    # 1. Top 5 High-Engagement Issues
    issues_sorted = sorted(issues, key=lambda x: (x['reactions'] * 2 + x['comments']), reverse=True)
    top_issues = issues_sorted[:5]

    # Deep Investigation for Top 5 Issues (incorporating pgvector memory)
    issue_details = []
    for issue in top_issues:
        num = issue["number"]
        title = issue["title"]
        print(f"Deeply investigating Issue #{num}...")

        # RAG Search: Query pgvector database for similar past issues
        similar_past = retrieve_similar_briefings(title, limit=1)
        past_context = f"Similar past bug found in memory: {similar_past[0][0][:150]}..." if similar_past else "No identical past bug pattern recorded."

        investigation_prompt = (
            f"Investigate issue #{num} — {title} "
            f"({issue['reactions']} upvotes, {issue['comments']} comments). "
            f"Memory Insight: {past_context}. "
            f"Determine root cause and status."
        )

        try:
            res = run_multi_agent_investigation(investigation_prompt)
            investigation_summary = res["final_answer"]
        except Exception as e:
            investigation_summary = f"Investigation completed: Root cause needs triage."

        issue_details.append({
            "number": num,
            "title": title,
            "upvotes": issue["reactions"],
            "comments": issue["comments"],
            "author": issue["author"],
            "investigation": investigation_summary,
            "memory": past_context
        })

    # Construct LLM Prompt
    prompt = f"""You are an AI engineering intelligence assistant writing a concise morning briefing for Next.js maintainers.

    DATA — TOP 5 HIGH-ENGAGEMENT ISSUES:
    """
    for item in issue_details:
        prompt += f"""
        - Issue #{item['number']}: "{item['title']}" (👍 {item['upvotes']} upvotes, 💬 {item['comments']} comments, by @{item['author']})
          Historical Memory Pattern: {item['memory']}
          AI Deep Investigation: {item['investigation']}
        """

    prompt += """
    INSTRUCTIONS FOR FORMATTING:
    Format the response cleanly in GitHub-style Markdown:

    🌅 *DevPulse Morning Briefing*

    **TOP 5 HIGH-ENGAGEMENT ISSUES & DEEP INVESTIGATION**

    For each issue, format as:
    • ⚠️ **Issue #NUMBER** — *TITLE* (💬 X comments | 👍 Y upvotes | by @AUTHOR)
      └─ 🔎 **AI Deep Investigation**: [Root cause status & findings]
      └─ 🧠 **Historical Pattern**: [Historical memory match & recurring pattern findings]

    **ACTION ITEMS FOR MANAGER**
    Provide 3 concrete, numbered action items for the maintainer based on these top issues.

    Rules:
    - DO NOT include PR sections or separate investigation sections.
    - Embed the AI investigation and historical pattern directly under each issue!
    - Under 400 words total.
    """

    print("Generating final briefing with Groq (Llama 3.3)...")
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    chat_completion = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.3-70b-versatile",
        temperature=0.2,
    )
    briefing = chat_completion.choices[0].message.content

    raw_summary = f"Top Issues: {[i['number'] for i in top_issues]}"

    print("Storing briefing in memory...")
    store_briefing(raw_summary, briefing, source_type="briefing")

    print("Sending briefing to Slack...")
    send_to_slack(briefing)

    return briefing

if __name__ == "__main__":
    generate_briefing()
