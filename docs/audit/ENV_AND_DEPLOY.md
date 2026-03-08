# Environment and Deployment — PlanningTreeCodex (Legacy Audit)

Source: `C:\Users\Thong\PlanningTree\PlanningTreeCodex`
Audit date: 2026-03-07

---

## Runtime Environment (Current)

### Backend

| Concern | Current Setup |
|---|---|
| Language runtime | Python 3.9+ |
| Server | Uvicorn (ASGI) |
| Port | 8000 (hardcoded in scripts) |
| Reload mode | `--reload` flag in dev scripts |
| CORS | Allow all origins (no auth, local only) |
| Data root | `%APPDATA%\PlanningTree\users\local\projects` (Windows default) |
| Config | Environment variables only (no config files) |

### Frontend

| Concern | Current Setup |
|---|---|
| Dev server | Vite on port 5173 |
| API target | `http://localhost:8000` (via `VITE_API_BASE` env var) |
| Build output | `frontend/dist/` |
| Asset serving | Vite dev server in dev; static files in prod (no serving infra defined) |

---

## Environment Variables

| Variable | Default | Required | Description |
|---|---|---|---|
| `OPENAI_API_KEY` | — | Yes (for AI features) | OpenAI API key passed through to Codex subprocess |
| `PLANNINGTREE_DATA_ROOT` | `%APPDATA%\PlanningTree\users\local\projects` | No | Override data storage directory |
| `PLANNINGTREE_CODEX_CMD` | auto-discovered | No | Path to Codex binary; if unset, searches PATH then VSCode extensions |
| `PLANNINGTREE_PLAN_TIMEOUT_SEC` | `60` | No | Timeout in seconds for plan-gates operations |
| `PLANNINGTREE_SPLIT_TIMEOUT_SEC` | `120` | No | Timeout in seconds for split operations |
| `PLANNINGTREE_NODE_TITLE_TIMEOUT_SEC` | `20` | No | Timeout in seconds for AI title generation |
| `PLANNINGTREE_INTERPRETER_MODE` | (default) | No | Codex interpreter execution mode |
| `VITE_API_BASE` | `http://localhost:8000` | No | Frontend API base URL (Vite build-time var) |

---

## Local Setup (Current — from `runbook.md`)

### Backend

```bash
cd PlanningTreeCodex/backend
python -m venv .venv
.venv/Scripts/activate          # Windows
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000
```

### Frontend

```bash
cd PlanningTreeCodex/frontend
npm install
npm run dev
```

### Combined (recommended)

```bash
python scripts/dev.py           # starts both servers cross-platform
# or
powershell scripts/dev.ps1      # Windows only
```

### Prerequisites for Setup

1. Python 3.9+ installed and in PATH
2. Node.js (version unspecified in docs)
3. npm
4. Codex app server binary installed (via VSCode Codex extension or separately)
5. `OPENAI_API_KEY` set in environment

**Gap:** No `.env` file, no `env.example`, no automated prerequisite checking. Developer must manually ensure all prerequisites.

---

## Testing (Current)

### Backend Tests

```bash
cd PlanningTreeCodex
python -m unittest discover -s backend/tests -p "test_*.py"
# or
pytest backend/tests/
```

### Frontend Unit Tests

```bash
cd PlanningTreeCodex/frontend
npm run test:unit               # runs vitest
npm run test:unit:watch         # watch mode
```

### Frontend E2E Tests

```bash
cd PlanningTreeCodex/frontend
npx playwright install          # install browsers
# ensure both servers are running
npm run test:e2e
npm run test:e2e:headed         # visible browser
npm run test:e2e:debug          # debug mode
```

E2E test helper scripts: `python scripts/test_e2e.py` (starts servers + runs tests)

### Test Coverage

- Backend: unittest with some coverage of orchestrator and storage operations
- Frontend unit: Vitest covering sseManager, ChatPanel, WorkflowGraph actions, selection, ReconfirmationPanel
- Frontend E2E: Playwright covering happy-path, chat, error-states, rollback-cleanup, scope-shift-replan

**Gap:** No CI configuration found. Tests run manually only.

---

## Deployment (Current)

**There is no production deployment configuration.** This is a local-only prototype.

- No Docker, no docker-compose
- No CI/CD pipeline
- No build scripts for production
- No npm packaging or distribution
- No environment separation (dev/staging/prod)
- Backend served by Uvicorn directly (not behind a reverse proxy)
- Frontend built by Vite but no serving infrastructure defined for the built output

---

## Deployment (Rebuild Target)

| Concern | Target |
|---|---|
| Distribution | npm package (`planningtree`) published to npm registry |
| Entry point | `npx planningtree` via `bin` field in package.json |
| Backend bundling | PyInstaller — produces platform-specific executables |
| Binary distribution | Downloaded by npm postinstall script from GitHub Releases (per-platform) |
| Frontend | Bundled into npm package as pre-built `dist/` static files |
| Serving | Backend executable serves both API and static frontend on same localhost port |
| Port selection | Dynamic: find free port on startup |
| Browser open | Automatic on launch |
| Auth | Cloud identity flow (browser redirect, OAuth2) |

---

## Platform Considerations

| Platform | Current State | Notes |
|---|---|---|
| Windows | Primary dev environment | Data root uses `%APPDATA%`, scripts use PowerShell |
| macOS | Untested but likely functional | Would need data root at `~/Library/Application Support/PlanningTree` |
| Linux | Untested | Would need data root at `~/.local/share/PlanningTree` |

**Rebuild target:** All three platforms, with PyInstaller producing separate binaries per platform via GitHub Actions CI matrix build.
