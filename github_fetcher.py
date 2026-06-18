import requests
import os
from dotenv import load_dotenv
from datetime import datetime, timezone

load_dotenv()

TOKEN = os.getenv("GITHUB_TOKEN")
REPO = "vercel/next.js"

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json"
}

BASE_URL = "https://api.github.com"

def days_old(date_string):
    created = datetime.fromisoformat(date_string.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    return (now - created).days

def get_open_prs():
    url = f"{BASE_URL}/repos/{REPO}/pulls"
    params = {"state": "open", "per_page": 20, "sort": "updated", "direction": "asc"}
    response = requests.get(url, headers=HEADERS, params=params)
    prs = response.json()
    
    result = []
    for pr in prs:
        result.append({
            "number": pr["number"],
            "title": pr["title"],
            "author": pr["user"]["login"],
            "created_at": pr["created_at"],
            "updated_at": pr["updated_at"],
            "draft": pr["draft"],
            "labels": [l["name"] for l in pr["labels"]]
        })
        # print(days_old(pr["created_at"]))

    # print(len(result))
    return result

def get_open_issues():
    url = f"{BASE_URL}/repos/{REPO}/issues"
    params = {
        "state": "open",
        "per_page": 20,
        "sort": "updated",
        "direction": "asc",
        "labels": "bug" 
    }
    response = requests.get(url, headers=HEADERS, params=params)
    issues = response.json()
    
    result = []
    for issue in issues:
        if "pull_request" not in issue:
            result.append({
                "number": issue["number"],
                "title": issue["title"],
                "author": issue["user"]["login"],
                "created_at": issue["created_at"],
                "comments": issue["comments"],
                "reactions": issue["reactions"]["+1"],
                "labels": [l["name"] for l in issue["labels"]]
            })

    # print(len(result))
    return result

def get_recent_workflow_runs():
    url = f"{BASE_URL}/repos/{REPO}/actions/runs"
    params = {"per_page": 10}
    response = requests.get(url, headers=HEADERS, params=params)
    runs = response.json().get("workflow_runs", [])
    
    result = []
    for run in runs:
        # filter to only PRs from the main repo not forks
        main_repo_prs = [
            pr for pr in run["pull_requests"]
            if pr["head"]["repo"]["id"] == pr["base"]["repo"]["id"]]
        
        result.append({
            "name": run["name"],
            "status": run["status"],
            "conclusion": run["conclusion"],
            "branch": run["head_branch"],
            "created_at": run["created_at"],
            "actor": run["actor"]["login"],
            "pr_number": main_repo_prs[0]["number"] if main_repo_prs else None,
            "commit_message": run["head_commit"]["message"].split("\n")[0] if run.get("head_commit") else None,
        })
    return result

if __name__ == "__main__":
    print("=== OPEN PRs (oldest updated first) ===")
    prs = get_open_prs()
    for pr in prs:
        print(f"  #{pr['number']} — {pr['title'][:100]} | {days_old(pr['created_at'])} days old | by {pr['author']} | draft: {pr['draft']}")

    print("\n=== OPEN ISSUES (oldest updated first) ===")
    issues = get_open_issues()
    for issue in issues:
        print(f"  #{issue['number']} — {issue['title'][:60]} | {days_old(issue['created_at'])} days old | 👍 {issue['reactions']} | 💬 {issue['comments']}")

    print("\n=== RECENT CI RUNS ===")
    runs = get_recent_workflow_runs()
    for run in runs:
        status = run["conclusion"] or run["status"]
        pr = f"PR #{run['pr_number']}" if run["pr_number"] else "branch merge"
        commit = run["commit_message"][:100] if run["commit_message"] else ""
        print(f"  {run['name']} | {status} | {pr} | {commit[:50]} | by @{run['actor']}")