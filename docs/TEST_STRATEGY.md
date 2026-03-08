# Test Strategy — PlanningTree Rebuild

Version: 0.1.0-scaffold
Last updated: 2026-03-07

---

## Philosophy

- Test behavior, not implementation
- Unit tests cover domain logic in isolation
- Integration tests cover route behavior end-to-end (with real storage on temp dirs)
- E2E tests cover complete user workflows in a real browser
- Do not test private functions or internal implementation details
- Do not mock what you can use directly (e.g., use real JSON storage in integration tests with temp dirs)

---

## Backend Testing

### Unit Tests (`backend/tests/unit/`)

**What to test:**
- Service methods with mocked storage
- Status transition logic (`node_service.py`)
- Sibling unlock logic (`tree_service.py`)
- Split prompt generation (`ai/split_prompt_builder.py`)
- Context builder output (`ai/context_builder.py`)
- Error class behavior (`errors/app_errors.py`)

**Tools:** `pytest`, `pytest-asyncio`, `unittest.mock`

**Pattern:**
```python
# backend/tests/unit/services/test_node_service.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from backend.services.node_service import NodeService

@pytest.fixture
def mock_storage():
    storage = MagicMock()
    storage.project_store = MagicMock()
    return storage

async def test_complete_node_sets_status_done(mock_storage):
    node_service = NodeService(mock_storage)
    # ...
```

**Do NOT unit test:**
- Routes (test those in integration)
- Storage file I/O (test those in integration with real temp dirs)
- OpenAI API calls (mock at the `ai/openai_client.py` boundary)

### Integration Tests (`backend/tests/integration/`)

**What to test:**
- Full route → service → storage roundtrip
- Error responses (404, 409, 412)
- SSE event format
- State persistence across requests (using temp dir)

**Tools:** `pytest`, `pytest-asyncio`, `httpx.AsyncClient`, `FastAPI TestClient`

**Pattern:**
```python
# backend/tests/integration/test_projects.py
import pytest
import tempfile
from pathlib import Path
from httpx import AsyncClient, ASGITransport
from backend.main import create_app

@pytest.fixture
async def client(tmp_path):
    app = create_app(data_root=tmp_path)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

async def test_create_project(client):
    resp = await client.post("/v1/projects", json={"name": "Test Project"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Test Project"
    assert "id" in data
```

**Mock boundaries for integration tests:**
- Mock `ai/openai_client.py` (do not call real OpenAI)
- Mock `ai/codex_client.py` (do not spawn real Codex subprocess)
- Use real storage with `tmp_path` (do not mock file I/O)

### Running Backend Tests

```bash
# From PlanningTreeMain root
pytest backend/tests/unit/           # fast, no external deps
pytest backend/tests/integration/    # requires mock AI clients
pytest backend/tests/               # all backend tests
```

---

## Frontend Testing

### Unit Tests (`frontend/tests/unit/`)

**What to test:**
- Zustand store logic (project-store, ui-store, chat-store)
- API client error handling
- SSE manager reconnection logic
- Utility functions

**Tools:** `Vitest`, `@testing-library/react`, `jsdom`

**Pattern:**
```typescript
// frontend/tests/unit/stores/project-store.test.ts
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { useProjectStore } from '../../../src/stores/project-store'

describe('project-store', () => {
  beforeEach(() => {
    useProjectStore.getState().reset()
  })

  it('sets selected node', () => {
    const { setSelectedNode, selectedNodeId } = useProjectStore.getState()
    setSelectedNode('node-1')
    expect(useProjectStore.getState().selectedNodeId).toBe('node-1')
  })
})
```

**Do NOT unit test:**
- Route components (test those in E2E)
- API client network calls (mock at the fetch boundary)

### E2E Tests (`frontend/tests/e2e/`)

**What to test:**
- Complete user workflows (happy path + critical error states)
- Graph rendering and interaction
- Split flow (mock AI response)
- Finish Task → Breadcrumb Chat flow
- Mark Done → sibling unlock

**Tools:** `Playwright`

**Pattern:**
```typescript
// frontend/tests/e2e/happy-path.spec.ts
import { test, expect } from '@playwright/test'

test('create project and split root node', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'New Project' }).click()
  await page.getByLabel('Project name').fill('My Project')
  await page.getByRole('button', { name: 'Create' }).click()
  await expect(page.getByTestId('graph-node-root')).toBeVisible()
  // ...
})
```

**Running E2E tests:**
```bash
cd frontend
npx playwright install   # first time only
npm run test:e2e
npm run test:e2e:headed  # visible browser
```

E2E tests require both backend and frontend running. Use the `webServer` config in `playwright.config.ts` to start them automatically.

---

## Test Coverage Targets

| Layer | Target | Priority |
|---|---|---|
| `backend/services/` | >80% line coverage | High |
| `backend/storage/` | >70% (covered by integration) | Medium |
| `backend/routes/` | Covered by integration tests | — |
| `backend/ai/` (prompt building) | >70% | Medium |
| `frontend/stores/` | >70% | High |
| `frontend/api/` | Error paths covered | Medium |
| E2E critical flows | 100% of acceptance criteria | High |

---

## Test Organization

```
backend/tests/
├── unit/
│   ├── services/
│   │   ├── test_node_service.py
│   │   ├── test_tree_service.py
│   │   └── test_split_service.py
│   └── ai/
│       ├── test_split_prompt_builder.py
│       └── test_context_builder.py
└── integration/
    ├── test_projects.py
    ├── test_nodes.py
    ├── test_split.py
    ├── test_complete.py
    └── test_chat.py

frontend/tests/
├── unit/
│   ├── setup.ts
│   ├── stores/
│   │   ├── project-store.test.ts
│   │   ├── ui-store.test.ts
│   │   └── chat-store.test.ts
│   └── api/
│       └── client.test.ts
└── e2e/
    ├── helpers.ts
    ├── happy-path.spec.ts
    ├── split.spec.ts
    ├── breadcrumb-chat.spec.ts
    └── mark-done.spec.ts
```

---

## CI Strategy (Phase 6)

GitHub Actions:
- On push to any branch: lint + unit tests (fast, < 2 min)
- On PR: lint + unit + integration tests (< 5 min)
- On release tag: full E2E + PyInstaller matrix build (Windows, macOS, Linux)
