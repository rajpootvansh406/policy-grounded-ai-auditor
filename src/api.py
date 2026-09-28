"""
api.py

This turns your target chatbot into a web API — a program that other
programs (like a web page) can send questions to and get answers back from,
over HTTP (the same protocol your browser uses to load websites).

We reuse everything from target_bot.py — we're not rewriting the chatbot
logic, just wrapping it so a web page can talk to it.

Usage:
    uvicorn src.api:app --reload

Then open http://127.0.0.1:8000/docs in your browser — FastAPI
automatically generates an interactive page there where you can test your
API before we even build the frontend.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from target_bot import (
    check_setup,
    build_vectorstore,
    load_vectorstore,
    get_chat_model,
    ask_bot,
    CHROMA_DIR,
)

# --- One-time setup, runs when the server starts ---
check_setup()

if not CHROMA_DIR.exists():
    print("No existing vector store found — building one now...")
    vectorstore = build_vectorstore()
else:
    print("Loading existing vector store...")
    vectorstore = load_vectorstore()

llm = get_chat_model()

# --- The actual web application ---
app = FastAPI(title="Policy Bot API")

# CORS = Cross-Origin Resource Sharing. Without this, browsers block a web
# page from calling an API running on a different port, as a security
# measure. Since our frontend and backend run on different ports during
# development, we need to explicitly allow it.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In a real product you'd restrict this to your actual frontend's address
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic model: this defines the "shape" of data we expect to receive.
# FastAPI uses this to automatically validate incoming requests — if someone
# sends a request without a "question" field, FastAPI rejects it
# automatically, before our code even runs.
class QuestionRequest(BaseModel):
    question: str


@app.get("/")
def health_check():
    """A simple endpoint to confirm the server is running."""
    return {"status": "Policy Bot API is running"}


@app.post("/ask")
def ask(request: QuestionRequest):
    """
    The main endpoint. The frontend will send a question here, and get
    back the bot's answer plus which source documents it used.
    """
    result = ask_bot(request.question, vectorstore, llm)
    sources = sorted(set(
        s["source_file"].split("\\")[-1].split("/")[-1]
        for s in result["sources"]
    ))
    return {
        "answer": result["answer"],
        "sources": sources,
    }
