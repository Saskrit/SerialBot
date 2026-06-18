from aiogram import Router

from . import admin, episodes, payment, plan, request, search, start, support


def setup_routers() -> Router:
    root = Router()
    root.include_router(start.router)
    root.include_router(plan.router)
    root.include_router(payment.router)
    root.include_router(request.router)
    root.include_router(support.router)
    root.include_router(search.router)
    root.include_router(episodes.router)
    root.include_router(admin.router)
    return root
