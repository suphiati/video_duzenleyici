from fastapi import APIRouter, HTTPException

from app.models.project import Project
from app.services.project_service import save_project, load_project, list_projects, delete_project

router = APIRouter()


@router.get("/list")
async def get_projects():
    return {"projects": list_projects()}


@router.post("/create")
async def create_project(name: str = "Yeni Proje"):
    project = Project(name=name)
    save_project(project)
    return project.model_dump()


@router.get("/{project_id}")
async def get_project(project_id: str):
    p = load_project(project_id)
    if not p:
        raise HTTPException(404, "Proje bulunamadi")
    return p.model_dump()


@router.put("/{project_id}")
async def update_project(project_id: str, project: Project):
    project.id = project_id
    save_project(project)
    return project.model_dump()


@router.delete("/{project_id}")
async def remove_project(project_id: str):
    if delete_project(project_id):
        return {"ok": True}
    raise HTTPException(404, "Proje bulunamadi")
