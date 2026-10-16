# Copyright (c) 2026 Aditya-Sh4rma
# Licensed under the MIT License.
# This file is part of MikasaMusic


from pyrogram import enums

_admin_cache: dict[int, set[int]] = {}


def is_owner(user_id: int, owner_id: int) -> bool:
    return bool(user_id) and user_id == owner_id


async def reload_admins(client, chat_id: int) -> list[int]:
    try:
        members = [
            admin
            async for admin in client.get_chat_members(
                chat_id, filter=enums.ChatMembersFilter.ADMINISTRATORS
            )
        ]
    except Exception:
        return []
    ids = {
        admin.user.id
        for admin in members
        if not getattr(getattr(admin, 'user', None), 'is_bot', False)
    }
    _admin_cache[chat_id] = ids
    return sorted(ids)


def clear_admin_cache(chat_id: int | None = None) -> None:
    if chat_id is None:
        _admin_cache.clear()
    else:
        _admin_cache.pop(chat_id, None)


async def member_is_admin(client, chat_id: int, user_id: int) -> bool:
    cached = _admin_cache.get(chat_id)
    if cached is not None:
        return user_id in cached
    try:
        member = await client.get_chat_member(chat_id, user_id)
    except Exception:
        return False
    return member.status in (enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER)
