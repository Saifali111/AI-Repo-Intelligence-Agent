import requests
import os
from dotenv import load_dotenv
from github_fetcher import get_open_prs, get_open_issues, get_recent_workflow_runs, days_old

load_dotenv()

def generate_briefing():
    # Step 1: collect all the data
    print("Fetching GitHub data...")
    prs = get_open_prs()
    issues = get_open_issues()
    runs = get_recent_workflow_runs()

    # Step 2: rank in Python BEFORE sending to LLM
    
    # sort issues by upvotes first, then comments
    issues_sorted = sorted(issues, key=lambda x: (x['reactions'], x['comments']), reverse=True)
    
    # sort PRs by age — oldest first
    prs_sorted = sorted(prs, key=lambda x: days_old(x['created_at']), reverse=True)
    
    # filter CI runs — only show failures and action_required
    ci_critical = [r for r in runs if r['conclusion'] in ['failure', 'action_required'] or r['status'] == 'action_required']
    ci_healthy = [r for r in runs if r['conclusion'] == 'success']
    
    # take only top items — pre-ranked
    top_issues = issues_sorted[:5]      # top 5 most upvoted bugs
    top_prs = prs_sorted[:5]            # top 5 oldest stale PRs
    critical_ci = ci_critical[:5]       # all failures/blocked runs

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

    # Step 4: prompt — LLM just writes, no ranking needed
    prompt = f"""You are an engineering intelligence assistant writing a morning briefing for the vercel/next.js maintainers.

The data below is ALREADY ranked by importance. Top of each list = highest priority.
Your job is only to write clearly. Do not reorder anything. Do not add items not in the list.

--- TOP BUG ISSUES (ranked by upvotes + comments, highest first) ---
{issue_summary}

--- STALEST OPEN PRs (ranked by age, oldest first) ---
{pr_summary}

--- CRITICAL CI (failures and blocked runs only) ---
{ci_summary}

Write a morning briefing with these sections:
1. CRITICAL — from the CI section only
2. NEEDS ATTENTION — top 3 issues and top 2 PRs from the lists above
3. ACTION ITEMS — 3 specific actions, most impactful first

Rules:
- Under 300 words total
- Use PR numbers and issue numbers
- No fluff, no filler sentences
- If CI section says no failures, skip CRITICAL or say all clear"""

    # Step 5: call Ollama
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
    return briefing

def generate_embedding(text):
    response = requests.post(
        "http://localhost:11434/api/embeddings",
        json={
            "model": "nomic-embed-text",
            "prompt": text
        }
    )
    result = response.json()
    return result["embedding"]

if __name__ == "__main__":
    # test embedding is working
    print("Testing embedding model...")
    test_embedding = generate_embedding("test briefing content")
    # print(test_embedding)
    print(f"Embedding works — vector size: {len(test_embedding)}")

    # generate briefing
    briefing = generate_briefing()
    print("\n" + "="*50)
    print("DEVPULSE MORNING BRIEFING")
    print("="*50)
    print(briefing)