import os
import psycopg2
import requests
import json
from datetime import datetime
from dotenv import load_dotenv
from langchain_google_vertexai import VertexAIEmbeddings

load_dotenv()

# Read from environment variables with safe local defaults.
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_NAME = os.getenv("DB_NAME", "devpulse")
DB_USER = os.getenv("DB_USER", "saifali")
DB_PASSWORD = os.getenv("DB_PASSWORD")

DB_CONFIG = {
    "dbname": DB_NAME,
    "user": DB_USER,
    "password": DB_PASSWORD,
    "host": DB_HOST,
    "port": DB_PORT
}

# Initialize Vertex AI Embeddings (Text-Embedding-004 returns 768 dimensions)
embedding_service = VertexAIEmbeddings(model_name="text-embedding-004")

def get_connection():
    return psycopg2.connect(**DB_CONFIG)

def generate_embedding(text):
    # Generate embeddings natively via Google Vertex AI
    return embedding_service.embed_query(text)

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
    # Test local connection
    print("Testing memory system...")
    print(f"Connecting to DB at {DB_HOST}:{DB_PORT}")
