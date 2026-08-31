# Policy-Grounded AI Auditor

A continuous compliance-auditing system for internal enterprise AI chatbots (HR bots, policy assistants, internal copilots).

## The Problem

Companies are rapidly deploying internal RAG-based AI agents (HR assistants, policy bots) on private company data. Existing red-teaming tools (DeepTeam, Mindgard, etc.) test for generic vulnerabilities — jailbreaks, prompt injection, PII leakage — but none of them:

1. Check whether a chatbot's answer actually matches the **company's own specific policy documents** (vs. an outdated or contradicted version)
2. Report how much to **trust their own judge/evaluator** over time

Real-world consequence: in a widely cited case, Air Canada's chatbot confidently quoted a bereavement-discount policy the airline had already deprecated — and a tribunal held the airline liable.

## What This Project Does

- Builds a synthetic internal HR/policy RAG chatbot as a test target
- Runs baseline generic red-teaming via DeepTeam
- Adds a **policy contradiction checker**: verifies chatbot answers against the actual source policy documents
- Adds a **judge reliability layer**: runs the same checks through multiple LLM judges and reports their agreement rate as a first-class metric
- Surfaces findings in a compliance dashboard

## Project Status

🚧 Phase 0 — environment setup and synthetic data generation (Week 1)

## Setup

```bash
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env       # then fill in your API key
```

## Project Structure

```
policy-grounded-ai-auditor/
├── data/
│   └── policies/          # synthetic company policy documents
├── src/
│   ├── target_bot.py       # the RAG chatbot being audited
│   ├── contradiction_checker.py
│   └── judge_ensemble.py
├── tests/
├── results/                # judge-agreement CSVs, audit logs
├── requirements.txt
├── .env.example
└── README.md
```

## Roadmap

See `/docs/roadmap.md` for the full 2-year phased plan.
