import os
import psycopg2
import requests
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Read from environment variables with safe local defaults.
# This means:
#   - running normally on your Mac (python memory.py) -> unchanged behavior
#   - running inside Docker -> set DB_HOST / OLLAMA_HOST to host.docker.internal
#   - running on Cloud Run later -> set these to wherever the DB/Ollama actually live
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_NAME = os.getenv("DB_NAME", "devpulse")
DB_USER = os.getenv("DB_USER", "saifali")

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

DB_CONFIG = {
    "dbname": DB_NAME,
    "user": DB_USER,
    "host": DB_HOST,
    "port": DB_PORT
}

def get_connection():
    return psycopg2.connect(**DB_CONFIG)

def generate_embedding(text):
    response = requests.post(
        f"{OLLAMA_HOST}/api/embeddings",
        json={
            "model": "nomic-embed-text",
            "prompt": text
        }
    )
    result = response.json()
    return result["embedding"]

def store_briefing(raw_summary, briefing_text, source_type=None):
    print(f"Generating embedding for {source_type or 'briefing'}...")
    embedding = generate_embedding(raw_summary)
    
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("""
        INSERT INTO briefings (raw_summary, briefing_text, embedding, source_type)
        VALUES (%s, %s, %s, %s)
    """, (raw_summary, briefing_text, embedding, source_type))
    
    conn.commit()
    cur.close()
    conn.close()
    print("Briefing stored in memory.")


def retrieve_similar_briefings(query_text, limit=3):
    embedding = generate_embedding(query_text)
    
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT briefing_text, created_at,
               1 - (embedding <=> %s::vector) AS similarity
        FROM briefings
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """, (embedding, embedding, limit))
    
    results = cur.fetchall()
    cur.close()
    conn.close()
    return results

if __name__ == "__main__":
    # test storing a briefing
    print("Testing memory system...")
    print(f"Connecting to DB at {DB_HOST}:{DB_PORT}, Ollama at {OLLAMA_HOST}")
    
    test_raw = "PR #28818 symlink pages 1745 days old. Issue #65512 14 upvotes concat performance bug."
    test_briefing = "NEEDS ATTENTION: PR #28818 is 1745 days old. Issue #65512 has 14 upvotes."
    
    store_briefing(test_raw, test_briefing)
    print("Stored test briefing.")
    
    # test retrieving
    print("\nRetrieving similar briefings...")
    results = retrieve_similar_briefings("stale PR performance bug")
    
    for briefing_text, created_at, similarity in results:
        print(f"\nSimilarity: {similarity:.3f} | Date: {created_at}")
        print(f"Briefing: {briefing_text}")
