# PROJECT_BRIEF.md
# Finance Agent — Living Context Document

> This document is the single source of truth for all planning and development sessions.

---

## 1. Project overview

An AI-assisted financial analysis system — not autonomous trading, but a decision-support tool that augments human judgment. Three core agents work together to screen stocks, assist with portfolio decisions, and surface market intelligence.

**Repository:** https://github.com/rmalachowsky16/finance-agent  
**Local path:** E:\Finance Agent Project  
**Status:** Project initialized, repo created. Development not yet started.

---

## 2. The three agents

### Stock screener
- Fetches fundamentals for a batch of tickers via yfinance
- Applies quantitative filters (P/E, revenue growth, margins, debt ratios)
- Passes top candidates to Claude API for ranking with written reasoning
- Output: ranked list with AI commentary per stock

### Portfolio assistant
- Takes user holdings + risk tolerance as input
- Suggests rebalancing, flags concentration risk
- Models hypothetical allocations
- Output: structured allocation suggestions with reasoning

### Market intelligence agent
- Downloads earnings call transcripts from SEC EDGAR
- Chunks transcripts to fit context limits
- Summarizes via Claude API: key themes, management tone, guidance revisions
- Output: structured JSON + human-readable summary
- **Start here — simplest to build, highest immediate value**

---

## 3. Agreed tech stack

| Layer | Technology | Notes |
|---|---|---|
| Backend | FastAPI (Python) | Async-native, plays well with Claude SDK |
| Frontend | Streamlit (MVP) → Next.js (v2) | Streamlit first for speed |
| Database | Supabase (PostgreSQL) | Free tier to start |
| Cache | Upstash (Redis) | Free tier, prevents API rate limit hits |
| Vector DB | Chroma (local) → Pinecone (prod) | For semantic search on filings |
| Hosting — backend | Render | Free tier (spins down) → $7/mo always-on |
| Hosting — frontend | Vercel | Free tier sufficient for MVP |
| AI reasoning | Anthropic Claude API (Sonnet) | claude-sonnet-4-6 |
| Market data | yfinance | Free, covers most needs |
| Filings | SEC EDGAR + sec-edgar-downloader | Free |
| Macro data | FRED API | Free |
| News | NewsAPI | Free dev plan (100 req/day) |

---

## 4. Architecture summary

```
Data Sources (yfinance, SEC EDGAR, FRED, NewsAPI)
        ↓
Core Agents (Screener, Portfolio Assistant, Market Intelligence)
        ↓
Claude API — reasoning layer (structured outputs, tool use)
        ↓
Frontend (Streamlit dashboard + chat interface)
        ↓
Storage (Supabase + Redis + Chroma)
```

---

## 5. Cost baseline

| Tier | Est. monthly cost |
|---|---|
| Personal / solo (current) | ~$25–40/mo |
| Small team | ~$116–200/mo |
| SaaS product | ~$625–1870+/mo |

**Current plan:** Personal tier. Claude Code Max plan ($20/mo) + Claude API calls (~$5–20/mo). All hosting on free tiers.

---

## 6. Build sequence (agreed order)

1. **Market intelligence agent** — earnings call summarization (start here)
2. **Stock screener agent** — fundamentals + Claude ranking layer
3. **Portfolio assistant** — allocation suggestions + risk modeling
4. **Streamlit dashboard** — unified UI across all three agents
5. **Deploy** — Render + Vercel + GitHub Actions CI/CD

---

## 7. Claude Code session plan

### Session 1 — scaffold + data layer
Scaffold the FastAPI project, set up yfinance and SEC EDGAR fetchers with async support and Redis caching. Define Pydantic models for `Stock`, `Fundamental`, `NewsItem`, `Transcript`.

### Session 2 — market intelligence agent
Build the agent that downloads earnings transcripts from SEC EDGAR, chunks them for context limits, calls Claude API with a structured prompt, and returns JSON with themes, sentiment, and guidance changes.

### Session 3 — stock screener agent
Build the screener: fetch fundamentals for a ticker list, apply filters, send top candidates to Claude API for ranked reasoning output.

### Session 4 — portfolio assistant
Build the allocation agent: accept holdings + risk tolerance, call Claude API for rebalancing suggestions and concentration risk flags.

### Session 5 — Streamlit UI
Three-page dashboard: Screener, Earnings Intelligence, Portfolio. Connect to FastAPI backend.

### Session 6 — deploy
Render config, Vercel config, GitHub Actions CI/CD pipeline.

---

## 8. Key decisions log

| Decision | Choice | Reason |
|---|---|---|
| Autonomous vs assisted | AI-assisted only | Realistic, valuable, avoids regulatory complexity |
| First agent to build | Market intelligence | Clearest value, no real-time data needed, demonstrable fast |
| MVP frontend | Streamlit | Fastest path to working UI, upgrade to Next.js later |
| Data source | yfinance (free) | Covers 90% of needs; Polygon.io only if going commercial |
| News data | NewsAPI free tier | $449/mo business plan only needed at scale |
| Vector DB | Chroma locally first | Pinecone when deploying to production |

---

## 9. Open questions / to decide

- [ ] What tickers / watchlist will the screener default to?
- [ ] What specific fundamental filters to apply in the screener?
- [ ] Risk tolerance model for portfolio assistant (simple 1–10 scale, or multi-factor?)
- [ ] Authentication needed? (Single user = no, multi-user = Supabase Auth)
- [ ] Paid data APIs needed later? (Polygon.io for real-time, Alpha Vantage for options)

---

## 10. Session log

| Date | Session | What was done | Next step |
|---|---|---|---|
| 2026-04-07 | Planning (Claude.ai chat) | Full architecture designed, stack chosen, costs modeled, build sequence agreed, repo initialized | Start Session 1 in Claude Code |

| 2026-04-07 | Session 1 (Claude Code) | Scaffolded FastAPI project structure, set up SEC EDGAR and yfinance fetchers, defined Pydantic models, configured Redis caching, created .gitignore, confirmed API health check | Add Anthropic credits and test /analyze endpoint, then begin Session 2 |

---

*Last updated: 2026-04-07*  
*Update this doc at the end of every planning or build session.*
