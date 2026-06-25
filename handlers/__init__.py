from aiogram import Router

from . import admin, browse, episodes, errors, payment, plan, refer, request, search, start, support, ui


def setup_routers() -> Router:
    root = Router()
    root.include_router(errors.router)
    root.include_router(start.router)
    root.include_router(ui.router)
    root.include_router(plan.router)
    root.include_router(refer.router)
    root.include_router(browse.router)
    root.include_router(payment.router)
    root.include_router(request.router)
    root.include_router(support.router)
    root.include_router(search.router)
    root.include_router(episodes.router)
    root.include_router(admin.router)
    return root
