import requests
import os
from dotenv import load_dotenv
from github_fetcher import get_open_prs, get_open_issues, get_recent_workflow_runs, days_old
from memory import store_briefing, retrieve_similar_briefings
from slack_sender import send_to_slack

load_dotenv()

def generate_briefing():
    # Step 1: collect all the data
    print("Fetching GitHub data...")
    prs = get_open_prs()
    issues = get_open_issues()
    runs = get_recent_workflow_runs()

    # Step 2: rank in Python BEFORE sending to LLM
    issues_sorted = sorted(issues, key=lambda x: (x['reactions'], x['comments']), reverse=True)
    prs_sorted = sorted(prs, key=lambda x: days_old(x['created_at']), reverse=True)
    ci_critical = [r for r in runs if r['conclusion'] in ['failure', 'action_required'] or r['status'] == 'action_required']

    top_issues = issues_sorted[:5]
    top_prs = prs_sorted[:5]
    critical_ci = ci_critical[:5]

    # Step 3: format pre-ranked data
    pr_summary = "\n".join([
        f"PR #{pr['number']} — {pr['title']} | {days_old(pr['created_at'])} days old | by @{pr['author']}"
        for pr in top_prs
    ])

    issue_summary = "\n".join([
        f"Issue #{issue['number']} — {issue['title']} | {days_old(issue['created_at'])} days old | 👍 {issue['reactions']} upvotes | 💬 {issue['comments']} comments"
        for issue in top_issues
    ])

    ci_summary = "\n".join([
        f"{run['name']} | {run['conclusion'] or run['status']} | PR #{run['pr_number']} | by @{run['actor']}"
        for run in critical_ci
    ]) if critical_ci else "No critical CI failures right now."

    # Step 4: build raw summary for embedding
    raw_summary = f"{pr_summary}\n{issue_summary}\n{ci_summary}"

    # Step 5: retrieve similar past situations BEFORE generating
    print("Searching memory for similar past situations...")
    similar = retrieve_similar_briefings(raw_summary, limit=3)

    if similar:
        memory_context = "\n\n".join([
            f"Past situation ({created_at.strftime('%B %d, %Y')}, similarity: {similarity:.2f}):\n{briefing_text}"
            for briefing_text, created_at, similarity in similar
            if similarity > 0.5
        ])
        if not memory_context:
            memory_context = "No strongly similar past situations found."
    else:
        memory_context = "No past briefings found. This is the first briefing."

    # Step 6: build prompt WITH memory
    prompt = f"""You are an engineering intelligence assistant writing a morning briefing for vercel/next.js maintainers.

        --- HISTORICAL CONTEXT (similar past situations) ---
        {memory_context}

        --- TODAY'S DATA ---

        TOP BUG ISSUES (pre-ranked, do not reorder):
        {issue_summary}

        STALEST OPEN PRs (pre-ranked, do not reorder):
        {pr_summary}

        CRITICAL CI (failures and blocked runs only):
        {ci_summary}

        Write a morning briefing with these sections:
        1. CRITICAL — CI failures only. Say "All clear" if none.
        2. NEEDS ATTENTION — top 3 issues and top 2 PRs in exact order given.
        3. ACTION ITEMS — 3 specific actions, most impactful first.
        4. HISTORICAL PATTERNS — only if past situations show a recurring pattern worth noting. Skip if nothing relevant.

        Rules:
        - Under 300 words total
        - Use PR numbers and issue numbers
        - No fluff
        - Present items in EXACTLY the order given"""

    # Step 7: generate briefing
    print("Generating briefing with llama3.2...")
    response = requests.post(
        "http://localhost:11434/api/chat",
        json={
            "model": "llama3.2",
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "stream": False
        }
    )

    result = response.json()
    briefing = result["message"]["content"]

    # Step 8: store today's briefing in memory for future retrieval
    print("Storing briefing in memory...")
    store_briefing(raw_summary, briefing)

    return briefing

if __name__ == "__main__":
    briefing = generate_briefing()
    print("\n" + "="*50)
    print("DEVPULSE MORNING BRIEFING")
    print("="*50)
    # print(briefing)

    send_to_slack(briefing)