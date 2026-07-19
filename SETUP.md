# Flight Recorder — Setup Guide

## Environment Setup

### Prerequisites
- Node.js 18+ (for Vite/React frontend)
- Python 3.9+ (for FastAPI backend)
- npm or yarn

### Quick Start

```bash
# Install all dependencies
npm run install:all

# Start viewer (React + Vite)
npm run dev:viewer
# Opens: http://localhost:5173

# In a separate terminal, start the FastAPI backend
npm run dev:store
# Serves at: http://localhost:7878
```

### Project Structure

```
flight-recorder/
├── viewer/                 # React + Vite + Tailwind SPA
│   ├── src/
│   │   ├── components/    # Timeline, DetailDrawer, etc.
│   │   ├── hooks/         # useTimeline, useSearch, etc.
│   │   ├── lib/           # API client, types
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── index.html
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   └── package.json
│
├── services/
│   ├── daemon/            # fr-hook event capture
│   │   ├── fr_hook.py     # Main hook handler
│   │   └── requirements.txt
│   │
│   └── store/             # FastAPI + SQLite viewer API
│       ├── main.py        # FastAPI app
│       ├── schema.py      # SQLite models
│       ├── api/           # REST endpoints
│       └── requirements.txt
│
└── package.json           # Monorepo root
```

### Frontend Development

```bash
# Start dev server with hot reload
cd viewer && npm run dev

# Run linter
npm run lint

# Build for production
npm run build
```

### Backend Development (Team member A)

```bash
cd services/store
pip install -r requirements.txt
uvicorn main:app --reload --port 7878

cd services/daemon
pip install -r requirements.txt
python -m fr_hook --dry-run  # Test hook locally
```

### Database

The store service creates:
- `~/.flight-recorder/recorder.db` — SQLite WAL mode
- `~/.flight-recorder/events/` — JSONL daily mirrors

### Branch Strategy

- `main` — stable, shared
- `feature/viewer-frontend` — UI/UX development (you are here)
- `feature/daemon-hooks` — Event capture (team member A)
- `feature/store-api` — FastAPI endpoints (shared)

**Team rule:** Each feature branch owns its service. Shared code (schema, types) goes through PR review.

---

## Next Steps

1. **Frontend**: Start with `npm run dev:viewer` and build out the Timeline component
2. **Backend**: Partner is building `fr-hook.py` and the SQLite schema
3. **API**: Sync on REST contract via the spec

The timeline + detail drawer are the product. Everything else is secondary.
