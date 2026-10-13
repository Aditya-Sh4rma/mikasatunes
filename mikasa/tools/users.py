from html import escape as html_escape
from types import SimpleNamespace


def _display_user(message) -> str:
    user = getattr(message, 'from_user', None)
    if user is None:
        return 'anonymous'
    mention = getattr(user, 'mention', None)
    if mention:
        return mention
    name = ' '.join(str(getattr(user, 'first_name', '') or '').split())
    return name or 'anonymous'


def _mention_of(user) -> str:
    if user is None:
        return 'unknown'
    mention = getattr(user, 'mention', None)
    if mention:
        return mention
    user_id = getattr(user, 'id', '')
    name = ' '.join(str(getattr(user, 'first_name', '') or user_id).split())
    if user_id:
        return f'<a href="tg://user?id={user_id}">{html_escape(name)}</a>'
    return html_escape(name) or 'unknown'


async def _extract_user(client, message):
    reply = getattr(message, 'reply_to_message', None)
    reply_user = getattr(reply, 'from_user', None) if reply is not None else None
    if reply_user is not None and getattr(reply_user, 'id', None):
        return reply_user
    command = getattr(message, 'command', None) or []
    if len(command) < 2:
        return None
    raw = str(command[1]).strip().lstrip('@')
    if not raw:
        return None
    if raw.isdigit():
        return SimpleNamespace(id=int(raw), first_name=raw, mention=None)
    get_users = getattr(client, 'get_users', None)
    if get_users is None:
        return None
    try:
        return await get_users(raw)
    except Exception:
        return None
