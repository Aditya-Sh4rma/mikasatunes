# Copyright (c) 2026 Aditya-Sh4rma
# Licensed under the MIT License.
# This file is part of MikasaMusic


from ..context import ctx
from .admins import is_owner, member_is_admin


async def _allowed_user(client, chat_id: int, user_id: int, allow_auth: bool = True) -> tuple:
    settings = ctx.settings
    owner_id = getattr(settings, 'owner_id', 0)
    database = getattr(ctx, 'database', None)
    if is_owner(user_id, owner_id):
        return True, ''
    if database is not None:
        try:
            if user_id in await database.sudo_users():
                return True, ''
        except Exception:
            pass
        try:
            if user_id in await database.blocked_users():
                return False, 'bl_user_notify'
        except Exception:
            pass
    if await member_is_admin(client, chat_id, user_id):
        return True, ''
    if allow_auth and database is not None:
        try:
            if await database.is_auth(chat_id, user_id):
                return True, ''
        except Exception:
            pass
    return False, 'not_admin'
