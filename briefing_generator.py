import requests
import os
from dotenv import load_dotenv
from github_fetcher import get_open_prs, get_open_issues, get_recent_workflow_runs, days_old
from memory import store_briefing, retrieve_similar_briefings
from slack_sender import send_to_slack
from multi_agent import run_multi_agent_investigation
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

    # Step 5b: THIS IS THE MISSING CONNECTION
    # Run the multi-agent (Investigator + Critic) deep investigation
    # on the TOP issue AND the top PR — not all 10 items, because each
    # investigation can take up to ~36 Groq calls (3 retries x 6 tool
    # iterations x 2 agents), and Groq's free tier caps at 30 requests
    # per minute / 1000 per day. Investigating everything risks hitting
    # that limit inside a single pipeline run.
    deep_investigations = []

    items_to_investigate = []
    if top_issues:
        items_to_investigate.append(("issue", top_issues[0]))
    if top_prs:
        items_to_investigate.append(("pr", top_prs[0]))

    for item_type, item in items_to_investigate:
        number = item["number"]
        title = item["title"]
        print(f"Running multi-agent deep investigation on {item_type} #{number}...")

        if item_type == "issue":
            investigation_prompt = (
                f"Investigate GitHub issue #{number} — {title} "
                f"({item['reactions']} upvotes, {days_old(item['created_at'])} days old). "
                f"Determine the root cause status and whether this is part of a recurring pattern."
            )
        else:
            investigation_prompt = (
                f"Investigate GitHub PR #{number} — {title} "
                f"({days_old(item['created_at'])} days old, by @{item['author']}). "
                f"Determine why it is still unmerged and whether review feedback explains the delay."
            )

        try:
            agent_result = run_multi_agent_investigation(investigation_prompt)
            deep_investigations.append(
                f"{item_type.upper()} #{number} (critic-verified, "
                f"{agent_result['retry_count']} attempt(s)):\n{agent_result['final_answer']}"
            )
        except Exception as e:
            print(f"Multi-agent investigation failed for {item_type} #{number}: {e}")
            deep_investigations.append(f"{item_type.upper()} #{number} investigation failed: {e}")

    deep_investigation_text = "\n\n".join(deep_investigations) if deep_investigations else "No deep investigation performed this run."

    # Step 6: build prompt WITH memory AND the verified deep investigation
    prompt = f"""You are an engineering intelligence assistant writing a morning briefing for vercel/next.js maintainers.

        --- HISTORICAL CONTEXT (similar past situations) ---
        {memory_context}

        --- VERIFIED DEEP INVESTIGATION (multi-agent, critic-approved) ---
        {deep_investigation_text}

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
        3. DEEP INVESTIGATION — summarize EACH verified deep investigation above 
           separately (one for the issue, one for the PR). These are the most 
           trustworthy, fact-checked insights in this briefing — present each clearly.
        4. ACTION ITEMS — 3 specific actions, most impactful first.
        5. HISTORICAL PATTERNS — only if past situations show a recurring pattern worth noting. Skip if nothing relevant.

        Rules:
        - Under 350 words total
        - Use PR numbers and issue numbers
        - No fluff
        - Present items in EXACTLY the order given"""

    # Step 7: generate briefing using Groq
    print("Generating briefing with Groq (Llama 3.3 70B)...")

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

    # Step 9: send to Slack — runs every time, whether called via CLI or FastAPI
    print("Sending briefing to Slack...")
    send_to_slack(briefing)

    return briefing

if __name__ == "__main__":
    briefing = generate_briefing()
    print("\n" + "="*50)
    print("DEVPULSE MORNING BRIEFING")
    print("="*50)
    print(briefing)