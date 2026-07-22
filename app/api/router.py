from fastapi import APIRouter

from app.modules.auth.routes import router as auth_router
from app.modules.opportunities.routes import router as opportunities_router
from app.modules.profiles.routes import router as profiles_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(opportunities_router)
api_router.include_router(profiles_router)
