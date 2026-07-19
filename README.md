# 🚨 DevPulse: AI Engineering Intelligence Agent
A production-ready AI agent that helps engineering teams automate repository monitoring, PR stale reviews, and critical CI failure tracking by generating a morning briefing using LangGraph orchestration, pgvector semantic memory, and automated Slack delivery.

🌟 Why this project exists
Engineering teams waste valuable time every morning checking dashboards, scrolling through active GitHub issues, tracking down stalest PRs, and checking which workflow runs failed.

This system acts as an AI-powered repository monitor, gathering data daily and analyzing the most critical issues.

The agent can:
• Fetch and rank open issues, PRs, and CI workflow runs
• Retrieve semantically similar past briefings and context using vector search
• Run a deep multi-agent investigation (Investigator + Critic) on top items to analyze root causes
• Generate a summarized, clean morning briefing using Groq (Llama 3.3)
• Deliver the structured report directly to a Slack channel
• Run securely on the cloud with automated triggers

🏗️ Architecture Overview
High-level workflow:

GitHub Cron schedule (GitHub Actions)
➡️ Secure API request with GCP OIDC Authentication
➡️ FastAPI endpoint wakes up on GCP Cloud Run
➡️ Vector search retrieves historical context from Cloud SQL (pgvector + Vertex AI)
➡️ LangGraph multi-agent workflow (Investigator ReAct loop + Critic validation)
➡️ Groq Llama 3.3 briefing generation
➡️ Deliver formatted briefing to Slack

Core stack:
• **FastAPI** for HTTP API endpoints
• **LangGraph** for multi-agent coordination
• **PostgreSQL + pgvector** for database semantic memory
• **Google Vertex AI** (`text-embedding-004`) for serverless embeddings
• **Groq** (`llama-3.3-70b-versatile`) for quick, high-quality reasoning
• **GitHub Actions** for secure scheduled triggering
• **Docker + GCP Cloud Run** for containerized serverless hosting

🤖 Key Features
🔎 LangGraph Multi-Agent Deep Investigator
• **Investigator Node**: Operates as a ReAct agent using tools to fetch issue timelines, comments, and PR reviews.
• **Critic Node**: Evaluates the investigator's reasoning. If it lacks sufficient evidence (e.g., claiming a "recurring pattern" without at least 2 distinct historical examples), it rejects the answer.
• **Episodic Memory Buffer**: On rejection, the critic's feedback is saved in a retry history list. The investigator uses this memory in the next iteration to avoid repeating mistakes.

🧠 Semantic Memory Database
• Ingests daily briefings, PR details, issues, and CI failures.
• Generates embeddings using Google's serverless Vertex AI API.
• Queries the Postgres database using the pgvector cosine distance operator (`<=>`) to fetch similar past situations.

🛡️ Secure Serverless API
• FastAPI backend built for production.
• Access to the daily briefing trigger endpoint is restricted using IAM and token authorization.
• Configuration is fully externalized to environment variables and secured via GCP Secret Manager.

💡 Example Use Cases
Automated briefings highlight:
• **Critical CI Failures**: Highlighting blocked runs, branch name, commit message, and author.
• **Stalest Open PRs**: Highlighting how many days they have been open and unmerged.
• **Root Cause Deep Investigation**: E.g., *"Investigate issue #95015 (Turbopack crashes on Windows). Determine root cause status and check if this is part of a recurring pattern."*

📂 Project Structure
devpulse/
 ├── .github/workflows/
 │     └── daily_briefing.yml   # GitHub Actions scheduler workflow
 ├── Dockerfile                 # Docker container instructions
 ├── main.py                    # FastAPI web server and route configurations
 ├── briefing_generator.py      # Core morning briefing generation pipeline
 ├── multi_agent.py             # LangGraph Investigator + Critic workflow
 ├── github_fetcher.py          # GitHub API retrieval functions
 ├── memory.py                  # PostgreSQL + pgvector + Vertex AI embeddings
 ├── slack_sender.py            # Slack webhook sender
 ├── agent.py                   # Local single-agent script (prototype)
 ├── backfill.py                # Backfill utility to populate DB memory with past issues
 └── requirements.txt           # Application Python packages

🚀 Getting Started
Prerequisites
• Python 3.12+
• PostgreSQL with `pgvector` extension installed
• Groq API Key
• GitHub Personal Access Token (PAT)
• Slack Webhook URL
• Google Cloud Platform account (with Vertex AI enabled)

🔧 Local Setup
1. **Clone the repository**:
   ```bash
   git clone https://github.com/Saifali111/AI-Repo-Intelligence-Agent.git
   cd AI-Repo-Intelligence-Agent
   ```
2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Create local environment file** (`.env`):
   ```env
   GITHUB_TOKEN=your_github_token
   SLACK_WEBHOOK_URL=your_slack_webhook
   GROQ_API_KEY=your_groq_key
   LANGSMITH_API_KEY=your_langsmith_key
   LANGSMITH_TRACING=true
   LANGSMITH_PROJECT=devpulse
   DB_HOST=localhost
   DB_PORT=5432
   DB_NAME=devpulse
   DB_USER=postgres
   DB_PASSWORD=your_db_password
   ```
4. **Run the FastAPI server locally**:
   ```bash
   uvicorn main:app --reload --port 8080
   ```
   *Swagger documentation is available locally at: `http://localhost:8080/docs`*

🐳 Run with Docker
1. **Build the container locally**:
   ```bash
   docker build -t devpulse:latest .
   ```
2. **Run the container**:
   ```bash
   docker run -p 8080:8080 --env-file .env devpulse:latest
   ```

🔮 Future Improvements
• Slack interactive Slash Commands (e.g. `/devpulse-investigate [issue_number]`).
• Support for multiple repository monitoring configurations (Multi-tenancy).
• A lightweight frontend dashboard to visualize historic briefings.

🙌 Acknowledgements
Built using LangGraph and FastAPI, powered by Groq, and deployed on Google Cloud Platform.
