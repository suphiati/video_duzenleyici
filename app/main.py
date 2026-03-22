from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import STATIC_DIR, DATA_DIR
from app.api import media, projects, timeline, subtitles, export, slideshow

app = FastAPI(title="Video Duzenleyici")

app.include_router(media.router, prefix="/api/media", tags=["media"])
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(timeline.router, prefix="/api/timeline", tags=["timeline"])
app.include_router(subtitles.router, prefix="/api/subtitles", tags=["subtitles"])
app.include_router(export.router, prefix="/api/export", tags=["export"])
app.include_router(slideshow.router, prefix="/api/slideshow", tags=["slideshow"])

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))
