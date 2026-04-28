from __future__ import annotations

from pathlib import Path

import uvicorn

from trace_agent_server.config import Settings
from trace_agent_server.main import create_app


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    state_dir = root / "frontend" / ".e2e"
    state_dir.mkdir(parents=True, exist_ok=True)
    database_path = state_dir / "e2e.db"
    if database_path.exists():
        database_path.unlink()

    settings = Settings(
        database_url=f"sqlite:///{database_path}",
        cors_origins=["http://127.0.0.1:4173"],
    )
    app = create_app(settings)
    uvicorn.run(app, host="127.0.0.1", port=8010, log_level="warning")


if __name__ == "__main__":
    main()
