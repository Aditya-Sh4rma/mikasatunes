from contextvars import ContextVar
from functools import wraps
from html import escape as html_escape
from pathlib import Path

from pyrogram import enums

from ..context import ctx
from ..exceptions import MikasaError
from ..logging_config import get_logger
from ..tools.admins import is_owner
from ..tools.buttons import queue_actions, start_key
from ..tools.perms import _allowed_user
from ..tools.users import _display_user, _extract_user
from ..tools.utils import format_duration, format_uptime

logger = get_logger('mikasa.plugins.common')

_current_lang: ContextVar[str] = ContextVar('mikasa_lang', default='')

GROUP_TYPES = (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP, enums.ChatType.FORUM)
VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.mov', '.webm', '.m4v'}


def _t(key: str, **kwargs) -> str:
    language = ctx.language
    if language is None:
        return key
    settings = ctx.settings
    code = _current_lang.get() or getattr(settings, 'default_language', None) or 'en'
    return language.text(code, key, **kwargs)


def _tc(chat_id: int, key: str, **kwargs) -> str:
    language = ctx.language
    if language is None:
        return key
    settings = ctx.settings
    code = language.cached(chat_id) or getattr(settings, 'default_language', None) or 'en'
    return language.text(code, key, **kwargs)


async def _set_lang(update) -> str:
    chat_id = None
    message = getattr(update, 'message', None)
    if message is not None and getattr(message, 'chat', None) is not None:
        chat_id = getattr(message.chat, 'id', None)
    else:
        chat = getattr(update, 'chat', None)
        if chat is not None:
            chat_id = getattr(chat, 'id', None)
    settings = ctx.settings
    default = getattr(settings, 'default_language', None) or 'en'
    code = ''
    language = ctx.language
    if chat_id is not None and language is not None:
        try:
            code = await language.for_chat(chat_id, getattr(ctx, 'database', None))
        except Exception:
            code = ''
    _current_lang.set(code or default)
    return code or default


def _is_group(message) -> bool:
    chat = getattr(message, 'chat', None)
    return chat is not None and getattr(chat, 'type', None) in GROUP_TYPES


def _arguments(message) -> str:
    command = getattr(message, 'command', None) or []
    return ' '.join(command[1:]).strip()


def _duration_text(seconds: int) -> str:
    try:
        return format_duration(seconds)
    except (TypeError, ValueError):
        return '0:00'


def _describe(item) -> tuple[str, str]:
    user = getattr(item, 'requested_by', '') or 'anonymous'
    return _duration_text(getattr(item, 'duration_seconds', 0) or 0), user


def _control_labels() -> dict:
    return {
        'btn_pause': _t('btn_pause'),
        'btn_resume': _t('btn_resume'),
        'btn_skip': _t('btn_skip'),
        'btn_stop': _t('btn_stop'),
        'btn_close': _t('btn_close'),
    }


def _help_labels() -> dict:
    from ..tools.buttons import HELP_TOPICS

    labels = {f'help_{index}': _t(f'help_{index}') for index in range(len(HELP_TOPICS))}
    labels['back'] = _t('back')
    labels['btn_close'] = _t('btn_close')
    return labels


def _start_pm_caption(message) -> str:
    import time

    import psutil

    boot = getattr(ctx, 'started_at', None) or time.time()
    return _t(
        'start_pm',
        mention=_display_user(message),
        name=_bot_name(),
        uptime=format_uptime(time.time() - boot),
        storage=f'{psutil.disk_usage("/").percent}%',
        cpu=f'{psutil.cpu_percent(interval=0)}%',
        ram=f'{psutil.virtual_memory().percent}%',
    )


async def _track_served(chat_id=None, user_id=None) -> None:
    database = getattr(ctx, 'database', None)
    if database is None:
        return
    try:
        if chat_id is not None:
            await database.add_chat(chat_id)
        elif user_id is not None:
            await database.add_user(user_id)
    except Exception:
        pass


def _bot_username() -> str:
    bot = getattr(ctx, 'bot', None)
    me = getattr(bot, 'me', None)
    return getattr(me, 'username', '') or ''


def _bot_name() -> str:
    bot = getattr(ctx, 'bot', None)
    me = getattr(bot, 'me', None)
    name = ' '.join(str(getattr(me, 'first_name', '') or '').split())
    return html_escape(name) or 'MikasaMusic'


def _support_chat() -> str:
    settings = ctx.settings
    url = getattr(settings, 'support_chat', '') if settings is not None else ''
    return url or 'https://t.me/'


def _drop_card(path) -> None:
    if not path:
        return
    try:
        Path(path).unlink()
    except OSError:
        pass


async def _fail(sent, message, key: str, markup=None, **kwargs) -> None:
    text = _t(key, **kwargs)
    edit = getattr(sent, 'edit_text', None)
    if edit is not None:
        try:
            if markup is None:
                await edit(text)
            else:
                await edit(text, reply_markup=markup)
            return
        except Exception:
            pass
    try:
        if markup is None:
            await message.reply_text(text)
        else:
            await message.reply_text(text, reply_markup=markup)
    except Exception:
        pass


def _start_labels() -> dict:
    return {
        'add_me': _t('add_me'),
        'btn_help': _t('btn_help'),
        'owner': _t('owner'),
        'support': _t('support'),
        'channel': _t('channel'),
    }


def _start_keyboard():
    settings = ctx.settings
    return start_key(
        bot_username=_bot_username(),
        owner_username=getattr(settings, 'owner_username', '') or '',
        support_chat=getattr(settings, 'support_chat', '') or '',
        support_channel=getattr(settings, 'support_channel', '') or '',
        labels=_start_labels(),
    )


def _queue_buttons(chat_id: int):
    return queue_actions(
        chat_id,
        bot_username=_bot_username(),
        close_label=_t('btn_close'),
    )


async def _allowed(client, message, allow_auth: bool = True) -> bool:
    user = getattr(message, 'from_user', None)
    if user is None:
        return False
    allowed, key = await _allowed_user(client, message.chat.id, user.id, allow_auth)
    if not allowed:
        if key == 'bl_user_notify':
            await message.reply_text(_t('bl_user_notify', support=_support_chat()))
        else:
            await message.reply_text(_t('not_admin'))
    return allowed


async def _deny_blocked(message) -> bool:
    user = getattr(message, 'from_user', None)
    if user is None:
        return False
    database = getattr(ctx, 'database', None)
    if database is None:
        return False
    try:
        blocked = await database.blocked_users()
    except Exception:
        return False
    if user.id in blocked:
        await message.reply_text(_t('bl_user_notify', support=_support_chat()))
        return True
    return False


async def _owner_only(client, message) -> bool:
    user = getattr(message, 'from_user', None)
    settings = ctx.settings
    owner_id = getattr(settings, 'owner_id', 0) if settings is not None else 0
    if user is not None and is_owner(user.id, owner_id):
        return True
    await message.reply_text(_t('not_admin'))
    return False


def require_group(func):
    @wraps(func)
    async def wrapper(client, message):
        await _set_lang(message)
        if not _is_group(message):
            await message.reply_text(_t('unsupported'))
            return None
        return await func(client, message)

    return wrapper


def require_control(func):
    @wraps(func)
    async def wrapper(client, message):
        await _set_lang(message)
        if not await _allowed(client, message):
            return None
        return await func(client, message)

    return wrapper


async def _need_database(message):
    database = getattr(ctx, 'database', None)
    if database is None:
        await message.reply_text(_t('error'))
        return None
    return database


async def _need_target(client, message):
    target = await _extract_user(client, message)
    if target is None:
        await message.reply_text(_t('user_not_found'))
    return target


async def _send_resolve_error(sent, message, exc: Exception) -> None:
    if isinstance(exc, MikasaError):
        await _fail(sent, message, 'play_not_found', support=_support_chat())
    else:
        await _fail(sent, message, 'error')
