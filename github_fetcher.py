import requests
import os
import re
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

def get_issue_comments(issue_number):
    url = f"{BASE_URL}/repos/{REPO}/issues/{issue_number}/comments"
    response = requests.get(url, headers=HEADERS, params={"per_page": 10})
    comments = response.json() if response.status_code == 200 else []
    
    result = []
    for comment in comments:
        result.append({
            "author": comment["user"]["login"],
            "body": comment["body"][:200],
            "created_at": comment["created_at"]
        })
    return result

def get_issue_timeline(issue_number):
    url = f"{BASE_URL}/repos/{REPO}/issues/{issue_number}/timeline"
    response = requests.get(url, headers=HEADERS, params={"per_page": 20})
    events = response.json() if response.status_code == 200 else []
    
    result = []
    if isinstance(events, list):
        for event in events:
            if isinstance(event, dict):
                event_type = event.get("event", "unknown")
                if event_type in ["labeled", "unlabeled", "assigned", "closed", "reopened", "cross-referenced"]:
                    source_info = ""
                    if event_type == "cross-referenced":
                        source = event.get("source", {}).get("issue", {})
                        source_info = f"PR #{source.get('number')}" if source else ""
                    result.append({
                        "event": event_type,
                        "info": source_info,
                        "created_at": event.get("created_at", "")
                    })
    return result

def get_pr_reviews(pr_number):
    url = f"{BASE_URL}/repos/{REPO}/pulls/{pr_number}/reviews"
    response = requests.get(url, headers=HEADERS, params={"per_page": 10})
    reviews = response.json() if response.status_code == 200 else []
    
    result = []
    for review in reviews:
        result.append({
            "author": review["user"]["login"],
            "state": review["state"],
            "body": review["body"][:200] if review.get("body") else ""
        })
    return result

def extract_linked_issue(text):
    if not text:
        return None
    match = re.search(r'(?:fix|fixes|close|closes|resolve|resolves|refs)?\s*#(\d+)', text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None

def get_open_prs():
    """Fetch 30 newest updated open PRs with issue mapping."""
    url = f"{BASE_URL}/repos/{REPO}/pulls"
    params = {"state": "open", "per_page": 30, "sort": "updated", "direction": "desc"}
    response = requests.get(url, headers=HEADERS, params=params)
    prs = response.json() if response.status_code == 200 else []
    
    result = []
    for pr in prs:
        body_text = pr.get("body") or ""
        solves_issue = extract_linked_issue(f"{pr['title']} {body_text}")
        
        result.append({
            "number": pr["number"],
            "title": pr["title"],
            "author": pr["user"]["login"],
            "created_at": pr["created_at"],
            "updated_at": pr["updated_at"],
            "draft": pr.get("draft", False),
            "solves_issue": solves_issue,
            "labels": [l["name"] for l in pr.get("labels", [])]
        })
    return result

def get_open_issues():
    """Fetch 30 newest updated open bug issues and detect PR presence."""
    url = f"{BASE_URL}/repos/{REPO}/issues"
    params = {
        "state": "open",
        "per_page": 30,
        "sort": "updated",
        "direction": "desc",
        "labels": "bug" 
    }
    response = requests.get(url, headers=HEADERS, params=params)
    issues = response.json() if response.status_code == 200 else []
    
    result = []
    for issue in issues:
        if "pull_request" not in issue:
            timeline = get_issue_timeline(issue["number"])
            linked_prs = [t["info"] for t in timeline if t["event"] == "cross-referenced" and t["info"]]
            
            result.append({
                "number": issue["number"],
                "title": issue["title"],
                "author": issue["user"]["login"],
                "created_at": issue["created_at"],
                "comments": issue["comments"],
                "reactions": issue["reactions"]["+1"] if "reactions" in issue else 0,
                "has_pr": len(linked_prs) > 0,
                "linked_pr": linked_prs[0] if linked_prs else None,
                "labels": [l["name"] for l in issue.get("labels", [])]
            })
    return result

def get_recent_workflow_runs():
    """Fetch recent CI workflow runs."""
    url = f"{BASE_URL}/repos/{REPO}/actions/runs"
    params = {"per_page": 15}
    response = requests.get(url, headers=HEADERS, params=params)
    runs = response.json().get("workflow_runs", []) if response.status_code == 200 else []
    
    result = []
    for run in runs:
        main_repo_prs = [
            pr for pr in run.get("pull_requests", [])
            if pr.get("head", {}).get("repo", {}).get("id") == pr.get("base", {}).get("repo", {}).get("id")
        ]
        
        result.append({
            "name": run["name"],
            "status": run["status"],
            "conclusion": run.get("conclusion"),
            "branch": run["head_branch"],
            "created_at": run["created_at"],
            "actor": run["actor"]["login"] if run.get("actor") else "unknown",
            "pr_number": main_repo_prs[0]["number"] if main_repo_prs else None,
            "commit_message": run["head_commit"]["message"].split("\n")[0] if run.get("head_commit") else None,
        })
    return result


if __name__ == "__main__":
    print("=== RECENT OPEN PRs (Newest First) ===")
    prs = get_open_prs()
    for pr in prs[:5]:
        solves = f" [Solves #{pr['solves_issue']}]" if pr['solves_issue'] else " [No Linked Issue]"
        print(f"  PR #{pr['number']} — {pr['title'][:60]} | by @{pr['author']}{solves}")
    print("\n=== RECENT OPEN BUG ISSUES (Newest First) ===")
    issues = get_open_issues()
    for issue in issues[:5]:
        status = f" [PR Created: {issue['linked_pr']}]" if issue['has_pr'] else " [NO PR CREATED YET ⚠️]"
        print(f"  Issue #{issue['number']} — {issue['title'][:60]} | 👍 {issue['reactions']} | 💬 {issue['comments']} | {status}")
    print("\n=== RECENT CI WORKFLOW RUNS ===")
    runs = get_recent_workflow_runs()
    for run in runs[:5]:
        status = run["conclusion"] or run["status"]
        pr_str = f"PR #{run['pr_number']}" if run["pr_number"] else "branch"
        print(f"  {run['name']} | {status} | {pr_str} | by @{run['actor']}")