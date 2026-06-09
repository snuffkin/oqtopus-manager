"""Routes for the backend .env file editor (view, lock, save, download)."""

from oqtopus_manager.routers._dotenv_routes import make_dotenv_router

router = make_dotenv_router(url_prefix="/backend", tags=["backend"])
