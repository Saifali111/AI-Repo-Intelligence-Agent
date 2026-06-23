import time
from github_fetcher import BASE_URL, HEADERS
from memory import store_briefing
from datetime import datetime, timezone
import requests

def days_old(date_string):
    created = datetime.fromisoformat(date_string.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    return (now - created).days

def get_specific_issue(issue_number):
    url = f"{BASE_URL}/repos/vercel/next.js/issues/{issue_number}"
    response = requests.get(url, headers=HEADERS)
    issue = response.json()
    return {
        "number": issue["number"],
        "title": issue["title"],
        "author": issue["user"]["login"],
        "created_at": issue["created_at"],
        "comments": issue["comments"],
        "reactions": issue["reactions"]["+1"],
        "state": issue["state"],
        "labels": [l["name"] for l in issue["labels"]]
    }

def get_specific_pr(pr_number):
    url = f"{BASE_URL}/repos/vercel/next.js/pulls/{pr_number}"
    response = requests.get(url, headers=HEADERS)
    pr = response.json()
    return {
        "number": pr["number"],
        "title": pr["title"],
        "author": pr["user"]["login"],
        "created_at": pr["created_at"],
        "state": pr["state"],
        "draft": pr["draft"]
    }

# diverse real issues across different topic areas
ISSUE_NUMBERS = [95015, 94989, 94980, 94945, 94919, 94901, 94895, 94893, 94892]

# diverse real PRs across different topic areas
PR_NUMBERS = [95067, 95065, 95062, 95057, 95055, 95054, 95053, 95052]

def backfill():
    print("Backfilling issues...")
    for num in ISSUE_NUMBERS:
        try:
            issue = get_specific_issue(num)
            issue_raw = f"GitHub Issue #{issue['number']}: {issue['title']}"
            labels = ", ".join(issue['labels']) if issue['labels'] else "none"
            issue_text = (
                f"Issue #{issue['number']} ({issue['title']}) — "
                f"state: {issue['state']}, {issue['reactions']} upvotes, "
                f"{issue['comments']} comments, labels: {labels}, "
                f"opened {days_old(issue['created_at'])} days ago by @{issue['author']}."
            )
            store_briefing(issue_raw, issue_text, source_type="issue")
            print(f"  Stored issue #{num}")
            time.sleep(1)  # be polite to APIs
        except Exception as e:
            print(f"  Failed on issue #{num}: {e}")

    print("\nBackfilling PRs...")
    for num in PR_NUMBERS:
        try:
            pr = get_specific_pr(num)
            pr_raw = f"GitHub PR #{pr['number']}: {pr['title']}"
            pr_text = (
                f"PR #{pr['number']} ({pr['title']}) by @{pr['author']} — "
                f"state: {pr['state']}, draft: {pr['draft']}, "
                f"opened {days_old(pr['created_at'])} days ago."
            )
            store_briefing(pr_raw, pr_text, source_type="pr")
            print(f"  Stored PR #{num}")
            time.sleep(1)
        except Exception as e:
            print(f"  Failed on PR #{num}: {e}")

    print("\nBackfill complete.")

if __name__ == "__main__":
    backfill()