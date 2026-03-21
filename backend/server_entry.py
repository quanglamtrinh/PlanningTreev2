"""PyInstaller entry point for the PlanningTree backend.

Uses direct imports (not string-based uvicorn import) to avoid
frozen module resolution issues.
"""

from __future__ import annotations

import uvicorn

from backend.config.app_config import get_port
from backend.main import create_app

app = create_app()

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=get_port(), log_level="info")
