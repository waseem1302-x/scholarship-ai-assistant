from fastapi import APIRouter

from app.modules.applications.command_routes import (
    router as command_centre_router,
)
from app.modules.applications.routes import router as applications_router
from app.modules.assistant.routes import router as assistant_router
from app.modules.auth.routes import router as auth_router
from app.modules.beta.routes import router as beta_router
from app.modules.community.routes import router as community_router
from app.modules.document_lab.routes import router as document_lab_router
from app.modules.matching.routes import router as matching_router
from app.modules.opportunities.routes import router as opportunities_router
from app.modules.profiles.routes import router as profiles_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(beta_router)
api_router.include_router(opportunities_router)
api_router.include_router(profiles_router)
api_router.include_router(matching_router)
api_router.include_router(applications_router)
api_router.include_router(command_centre_router)
api_router.include_router(assistant_router)
api_router.include_router(community_router)
api_router.include_router(document_lab_router)
