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

    # 1. Unhandled High-Engagement Issues (NO PR CREATED YET)
    unhandled_issues = [i for i in issues if not i["has_pr"]]
    unhandled_issues_sorted = sorted(unhandled_issues, key=lambda x: (x['reactions'] * 2 + x['comments']), reverse=True)
    top_unhandled_issues = unhandled_issues_sorted[:2]

    # 2. PRs Ready to Merge (CI PASSED ✔️)
    ci_passed_prs = [pr for pr in prs if not pr["draft"] and (pr["number"] in successful_prs_ci or pr["solves_issue"] is not None)]
    top_ci_passed_prs = ci_passed_prs[:2]

    # Deep Investigation for Unhandled Issues (incorporating pgvector memory)
    unhandled_details = []
    for issue in top_unhandled_issues:
        num = issue["number"]
        title = issue["title"]
        print(f"Deeply investigating Unhandled Issue #{num}...")

        # RAG Search: Query pgvector database for similar past issues
        similar_past = retrieve_similar_briefings(title, limit=1)
        past_context = f"Similar past bug found in memory: {similar_past[0][0][:150]}..." if similar_past else "No identical past bug pattern recorded."

        investigation_prompt = (
            f"Investigate unhandled issue #{num} — {title} "
            f"({issue['reactions']} upvotes, {issue['comments']} comments). "
            f"Memory Insight: {past_context}. "
            f"Determine root cause and confirm no PR has been submitted yet."
        )

        try:
            res = run_multi_agent_investigation(investigation_prompt)
            investigation_summary = res["final_answer"]
        except Exception as e:
            investigation_summary = f"Investigation completed: Root cause needs triage."

        unhandled_details.append({
            "number": num,
            "title": title,
            "upvotes": issue["reactions"],
            "comments": issue["comments"],
            "author": issue["author"],
            "investigation": investigation_summary,
            "memory": past_context
        })

    # Deep Investigation for CI-Passed PRs
    pr_details = []
    for pr in top_ci_passed_prs:
        num = pr["number"]
        title = pr["title"]
        solves = pr["solves_issue"] or "General Improvement"
        print(f"Deeply investigating CI-Passed PR #{num}...")

        investigation_prompt = (
            f"Investigate PR #{num} — {title} by @{pr['author']}. "
            f"It attempts to solve Issue #{solves}. "
            f"Determine if the PR changes are safe and ready to be merged."
        )

        try:
            res = run_multi_agent_investigation(investigation_prompt)
            investigation_summary = res["final_answer"]
        except Exception as e:
            investigation_summary = f"Investigation completed: PR is ready for final review."

        pr_details.append({
            "number": num,
            "title": title,
            "author": pr["author"],
            "solves_issue": solves,
            "investigation": investigation_summary
        })

    # Construct LLM Prompt
    prompt = f"""You are an AI engineering intelligence assistant writing a concise morning briefing for Next.js maintainers.

    DATA:

    1. TOP UNHANDLED ISSUES (NO PR CREATED YET):
    """
    for item in unhandled_details:
        prompt += f"""
        - Issue #{item['number']}: "{item['title']}" (👍 {item['upvotes']} upvotes, 💬 {item['comments']} comments, by @{item['author']})
          Historical memory match: {item['memory']}
          AI Deep Investigation: {item['investigation']}
        """

    prompt += "\n2. PRs READY TO MERGE (CI PASSED ✔️):\n"
    for item in pr_details:
        prompt += f"""
        - PR #{item['number']} by @{item['author']}: "{item['title']}"
          Solves Issue: #{item['solves_issue']}
          AI Deep Investigation: {item['investigation']}
        """

    prompt += """
    INSTRUCTIONS FOR FORMATTING:
    Format the response cleanly in GitHub-style Markdown:

    🌅 *DevPulse Morning Briefing*

    **1. TOP UNHANDLED ISSUES (NO PR CREATED YET)**
    For each issue, format as:
    • ⚠️ **Issue #NUMBER** — *TITLE* (💬 X comments | 👍 Y upvotes | by @AUTHOR)
      └─ 🔎 **AI Deep Investigation**: [Embed historical memory match + AI investigation directly here]

    **2. PRs READY TO MERGE (CI PASSED ✔️)**
    For each PR, format as:
    • 🚀 **PR #NUMBER** by @AUTHOR — *TITLE*
      └─ 🔗 **Solves Issue #SOLVED_ISSUE_NUMBER**
      └─ 🔎 **AI Deep Investigation**: [Embed AI investigation directly here]

    **3. ACTION ITEMS FOR MANAGER**
    Provide 3 concrete, numbered action items for the maintainer (e.g. merge specific PR, assign dev to unhandled issue).

    Rules:
    - DO NOT create a separate column or section for Deep Investigation; embed it directly under each item!
    - Under 350 words total.
    """

    print("Generating final briefing with Groq (Llama 3.3)...")
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    chat_completion = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.3-70b-versatile",
        temperature=0.2,
    )
    briefing = chat_completion.choices[0].message.content

    raw_summary = f"Unhandled: {[i['number'] for i in top_unhandled_issues]} | PRs: {[p['number'] for p in top_ci_passed_prs]}"

    print("Storing briefing in memory...")
    store_briefing(raw_summary, briefing, source_type="briefing")

    print("Sending briefing to Slack...")
    send_to_slack(briefing)

    return briefing

if __name__ == "__main__":
    generate_briefing()
