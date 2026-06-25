import requests
import os
from dotenv import load_dotenv
from github_fetcher import get_open_prs, get_open_issues, get_recent_workflow_runs, days_old
from memory import store_briefing, retrieve_similar_briefings
from slack_sender import send_to_slack
from groq import Groq

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

    # Step 7: generate briefing using Groq
    print("Generating briefing with Groq (Llama 3.3 70B)...")
    from groq import Groq

    groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    briefing = response.choices[0].message.content

    # Step 8a: store each entity SEPARATELY for precise future retrieval
    print("Storing individual entities in memory...")

    for issue in top_issues:
        issue_raw = f"GitHub Issue #{issue['number']}: {issue['title']}"
        issue_text = f"Issue #{issue['number']} ({issue['title']}) has been open for {days_old(issue['created_at'])} days with {issue['reactions']} upvotes and {issue['comments']} comments. Status: still unresolved as of this briefing."
        store_briefing(issue_raw, issue_text, source_type="issue")

    for pr in top_prs:
        pr_raw = f"GitHub PR #{pr['number']}: {pr['title']}"
        pr_text = f"PR #{pr['number']} ({pr['title']}) by @{pr['author']} has been open for {days_old(pr['created_at'])} days with no merge. Status: still stale as of this briefing."
        store_briefing(pr_raw, pr_text, source_type="pr")

    for run in critical_ci:
        ci_raw = f"CI Failure: {run['name']} on {run['branch']}"
        ci_text = f"Workflow {run['name']} failed/blocked on branch {run['branch']}, PR #{run['pr_number']}, commit: {run['commit_message']}, triggered by @{run['actor']}."
        store_briefing(ci_raw, ci_text, source_type="ci_failure")

    # Step 8b: also store the FULL briefing for general context
    print("Storing full briefing in memory...")
    store_briefing(raw_summary, briefing, source_type="briefing")

    send_to_slack(briefing)

    return briefing

if __name__ == "__main__":
    briefing = generate_briefing()
    print("\n" + "="*50)
    print("DEVPULSE MORNING BRIEFING")
    print("="*50)
    print(briefing)