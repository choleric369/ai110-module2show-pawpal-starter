"""JSON persistence — the ONLY module in the project that touches the disk.

No database by design: this is a prototype, so state is one JSON file.
Writes go to a temp file then rename, so a crash can't corrupt the save.
"""

import json
import os
from pathlib import Path

from pawpal.models.owner import Owner
from pawpal.models.plan import DailyPlan
from pawpal.utils.validation import StorageError

DATA_DIR = Path("data")
DEFAULT_PATH = DATA_DIR / "pawpal_data.json"
SAMPLE_PATH = DATA_DIR / "sample_data.json"
HISTORY_PATH = DATA_DIR / "history.json"
SCHEMA_VERSION = 1


def save_state(owner: Owner, path: Path = DEFAULT_PATH) -> Path:
    """Write the whole graph to JSON atomically; returns the path written.

    'Whole graph' = owner + contacts + pets + tasks + medical history +
    grooming sessions + bills + preferences. One file, one save.
    """
    path = Path(path)
    payload = {"schema_version": SCHEMA_VERSION, "owner": owner.to_dict()}
    _atomic_write(path, payload)
    return path


def load_state(path: Path = DEFAULT_PATH) -> Owner:
    """Read an Owner back from JSON; falls back to seed data if missing/corrupt."""
    from pawpal.services.seed import demo_owner

    path = Path(path)
    if not path.exists():
        return demo_owner()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return Owner.from_dict(_migrate(payload).get("owner", {}))
    except (json.JSONDecodeError, OSError, TypeError, AttributeError, KeyError):
        return demo_owner()


def _atomic_write(path: Path, payload: dict | list) -> None:
    """Dump JSON to '<path>.tmp' then os.replace, so the save is all-or-nothing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        raise StorageError(f"Could not write {path}: {exc}") from exc


def _migrate(payload: dict) -> dict:
    """Upgrade an older SCHEMA_VERSION payload so old save files still load."""
    version = payload.get("schema_version", 0)
    if version == 0 and "owner" not in payload:
        # Pre-versioning files stored the owner dict at the top level.
        return {"schema_version": SCHEMA_VERSION, "owner": payload}
    return payload


def export_plan(plan: DailyPlan, path: Path) -> Path:
    """Write a single generated plan to disk as .txt or .md, chosen by suffix."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = plan.to_markdown() if path.suffix.lower() == ".md" else plan.to_text()
    try:
        path.write_text(body, encoding="utf-8")
    except OSError as exc:
        raise StorageError(f"Could not export plan to {path}: {exc}") from exc
    return path


def append_history(plan: DailyPlan, path: Path = HISTORY_PATH) -> None:
    """Append a finished day to history.json, replacing any entry for that day."""
    path = Path(path)
    entries = [e for e in load_history(path) if e.get("day") != plan.to_dict()["day"]]
    entries.append(plan.to_dict())
    entries.sort(key=lambda e: e.get("day") or "")
    _atomic_write(path, entries)


def load_history(path: Path = HISTORY_PATH) -> list[dict]:
    """Read past days back as raw dicts; returns [] when there is no history yet."""
    path = Path(path)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []
