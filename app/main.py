from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import create_api_router
from app.services.analytics import EventRecorder
from app.services.llm import SlotParser, build_slot_parser
from app.services.sessions import SessionStore


WEB_ROOT = Path(__file__).parent / "web"


def create_app(slot_parser: SlotParser | None = None) -> FastAPI:
    application = FastAPI(title="循迹健康分诊助手", version="0.1.0")

    @application.exception_handler(RequestValidationError)
    async def private_validation_error(
        _request: Request,
        _exc: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"detail": "Invalid request payload"},
        )

    application.state.session_store = SessionStore()
    application.state.analytics = EventRecorder()
    application.state.slot_parser = (
        slot_parser if slot_parser is not None else build_slot_parser()
    )
    application.include_router(
        create_api_router(
            application.state.session_store,
            application.state.analytics,
            application.state.slot_parser,
        )
    )

    @application.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "mode": "demo"}

    application.mount(
        "/static",
        StaticFiles(directory=WEB_ROOT),
        name="static",
    )

    @application.get("/", response_class=FileResponse)
    def home() -> FileResponse:
        return FileResponse(WEB_ROOT / "index.html")

    return application


app = create_app()
