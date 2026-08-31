"""
target_bot.py

The "target system" — a minimal internal HR/policy chatbot built with
Retrieval-Augmented Generation (RAG). It loads the synthetic policy documents
from data/policies/, embeds them into a local ChromaDB vector store, and
answers questions by retrieving relevant chunks and passing them to an LLM.

This chatbot DELIBERATELY includes a stale/deprecated policy document in its
index. This simulates a real-world failure mode (like the Air Canada chatbot
case) where an internal bot might retrieve outdated information. Your auditor
system (built in later phases) is meant to catch exactly this kind of failure.

Design notes for reliability:
- Disables ChromaDB's anonymous telemetry (stops the noisy "Failed to send
  telemetry event" messages — harmless but distracting).
- Tries several current Gemini model names in order, since Google renames /
  retires model IDs periodically. If one is unavailable, it falls back to
  the next automatically instead of crashing.
- Normalizes the LLM response regardless of whether the provider returns a
  plain string or a list of structured content blocks (newer Gemini models
  do the latter).
- Validates that the API key and policy documents actually exist before
  doing any expensive work, with clear error messages instead of stack traces.

Usage:
    python src/target_bot.py
"""

import os
import sys
from pathlib import Path

# --- Silence ChromaDB's anonymous telemetry BEFORE importing chromadb ---
# This must happen before any chromadb import, or the setting is ignored.
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

from dotenv import load_dotenv

# Prefer the modern, non-deprecated Chroma integration if it's installed;
# fall back to the older one so this script still runs either way.
try:
    from langchain_chroma import Chroma
except ImportError:
    from langchain_community.vectorstores import Chroma

from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate

load_dotenv()

PROJECT_ROOT = Path(__file__).parent.parent
POLICIES_DIR = PROJECT_ROOT / "data" / "policies"
CHROMA_DIR = PROJECT_ROOT / "chroma_db"

EMBEDDING_MODEL = "gemini-embedding-001"

# Ordered list of chat model names to try. Google periodically retires model
# IDs — if the first one 404s, we automatically try the next instead of
# crashing. Update this list over time as new models are released.
CHAT_MODEL_CANDIDATES = [
    "gemini-3.6-flash",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
]

PROMPT_TEMPLATE = ChatPromptTemplate.from_template(
    """You are an internal company assistant. Answer the employee's question
using ONLY the context below. If the context contains conflicting information
from different documents, point out the conflict explicitly rather than
picking one arbitrarily. If the context doesn't contain the answer, say you
don't know — do not make anything up.

Context:
{context}

Question: {question}

Answer:"""
)


def check_setup():
    """Fail fast with a clear message instead of a confusing stack trace."""
    if not os.getenv("GOOGLE_API_KEY") and not os.getenv("GEMINI_API_KEY"):
        sys.exit(
            "ERROR: No API key found. Add GOOGLE_API_KEY=your_key_here to "
            "your .env file in the project root, then try again."
        )

    if not POLICIES_DIR.exists() or not any(POLICIES_DIR.glob("*.md")):
        sys.exit(
            f"ERROR: No policy documents found in {POLICIES_DIR}. "
            f"Add at least one .md file there before running this script."
        )


def get_chat_model() -> ChatGoogleGenerativeAI:
    """
    Try each candidate model name in order until one actually works.
    Returns a ready-to-use ChatGoogleGenerativeAI instance.
    """
    last_error = None
    for model_name in CHAT_MODEL_CANDIDATES:
        try:
            llm = ChatGoogleGenerativeAI(model=model_name)
            # Do a trivial, cheap call to confirm the model actually exists
            # and is reachable, instead of finding out mid-conversation.
            llm.invoke("ping")
            print(f"Using chat model: {model_name}")
            return llm
        except Exception as e:  # noqa: BLE001 — intentionally broad, we try the next model
            last_error = e
            continue

    sys.exit(
        f"ERROR: None of the candidate chat models worked. "
        f"Last error: {last_error}\n"
        f"Update CHAT_MODEL_CANDIDATES in target_bot.py with a current "
        f"model name from https://ai.google.dev/gemini-api/docs/models"
    )


def build_vectorstore():
    """Load all policy .md files, split them into chunks, and embed them into ChromaDB."""
    loader = DirectoryLoader(
        str(POLICIES_DIR),
        glob="*.md",
        loader_cls=TextLoader,
        loader_kwargs={"encoding": "utf-8"},
    )
    documents = loader.load()
    print(f"Loaded {len(documents)} policy documents.")

    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = splitter.split_documents(documents)
    print(f"Split into {len(chunks)} chunks.")

    embeddings = GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL)

    vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=str(CHROMA_DIR),
    )
    print(f"Vector store built and saved to {CHROMA_DIR}")
    return vectorstore


def load_vectorstore():
    """Load an already-built vector store from disk."""
    embeddings = GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL)
    return Chroma(persist_directory=str(CHROMA_DIR), embedding_function=embeddings)


def extract_text(response) -> str:
    """
    Normalize an LLM response into a plain string, regardless of whether the
    provider returned a plain string or a list of structured content blocks
    (newer Gemini models do the latter).
    """
    content = response.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts).strip()
    return str(content)


def ask_bot(query: str, vectorstore, llm) -> dict:
    """
    Ask the target chatbot a question. Returns a dict with the answer and the
    source document chunks it retrieved — useful later for your contradiction
    checker, which needs to see exactly what the bot based its answer on.
    """
    retriever = vectorstore.as_retriever(search_kwargs={"k": 3})
    docs = retriever.invoke(query)

    context = "\n\n---\n\n".join(doc.page_content for doc in docs)

    prompt = PROMPT_TEMPLATE.invoke({"context": context, "question": query})
    response = llm.invoke(prompt)

    return {
        "query": query,
        "answer": extract_text(response),
        "sources": [
            {
                "content": doc.page_content,
                "source_file": doc.metadata.get("source", "unknown"),
            }
            for doc in docs
        ],
    }


def main():
    check_setup()

    if not CHROMA_DIR.exists():
        print("No existing vector store found — building one now...")
        vectorstore = build_vectorstore()
    else:
        print("Loading existing vector store...")
        vectorstore = load_vectorstore()

    llm = get_chat_model()

    print("\n--- Target Bot Ready ---")
    print("Type a question (or 'quit' to exit)\n")

    while True:
        try:
            query = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break

        if query.lower() in ("quit", "exit"):
            break
        if not query:
            continue

        try:
            result = ask_bot(query, vectorstore, llm)
        except Exception as e:  # noqa: BLE001 — keep the chat loop alive on transient errors
            print(f"\n[Error while answering: {e}]\n")
            continue

        print(f"\nBot: {result['answer']}\n")
        print("Sources used:")
        seen = set()
        for src in result["sources"]:
            filename = Path(src["source_file"]).name
            if filename not in seen:
                print(f"  - {filename}")
                seen.add(filename)
        print()


if __name__ == "__main__":
    main()
