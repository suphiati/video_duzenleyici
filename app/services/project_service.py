import json
from pathlib import Path
from datetime import datetime

from app.config import PROJECTS_DIR
from app.models.project import Project


def save_project(project: Project) -> Project:
    project.updated_at = datetime.now().isoformat()
    path = PROJECTS_DIR / f"{project.id}.json"
    path.write_text(project.model_dump_json(indent=2), encoding="utf-8")
    return project


def load_project(project_id: str) -> Project | None:
    path = PROJECTS_DIR / f"{project_id}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return Project(**data)


def list_projects() -> list[dict]:
    results = []
    for f in PROJECTS_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            results.append({
                "id": data.get("id"),
                "name": data.get("name"),
                "updated_at": data.get("updated_at"),
                "clip_count": len(data.get("clips", [])),
            })
        except Exception:
            continue
    return sorted(results, key=lambda x: x.get("updated_at", ""), reverse=True)


def delete_project(project_id: str) -> bool:
    path = PROJECTS_DIR / f"{project_id}.json"
    if path.exists():
        path.unlink()
        return True
    return False
