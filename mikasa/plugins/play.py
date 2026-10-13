from html import escape as html_escape
from pathlib import Path
from urllib.parse import urlparse

from pyrogram import enums, filters
from pyrogram.errors import ChatAdminRequired, UserNotParticipant
from pyrogram.handlers import MessageHandler
from pyrogram.types import InputMediaPhoto
from pytgcalls.exceptions import NoActiveGroupCall

from ..context import ctx
from ..exceptions import DownloadError
from ..helpers._dataclass import Media, Track
from ..helpers._inline import player_controls
from ..helpers._queue import AddResult
from ..core.telegram import extension_of, is_supported_url
from ..core.youtube import is_youtube, parse_video_id
from ..logging_config import get_logger
from .common import (
    VIDEO_EXTENSIONS,
    _arguments,
    _bot_name,
    _control_labels,
    _deny_blocked,
    _describe,
    _display_user,
    _fail,
    _is_group,
    _queue_buttons,
    _send_resolve_error,
    _support_chat,
    _t,
)

logger = get_logger('mikasa.plugins.play')


def _play_flags(command, text: str) -> tuple:
    name = (command or [''])[0]
    force = name.endswith('force')
    video = name.startswith('v')
    parts = text.split()
    flags, query = [], []
    for part in parts:
        if part in ('-f', '-v'):
            flags.append(part)
        else:
            query.append(part)
    if '-f' in flags:
        force = True
    if '-v' in flags:
        video = True
    return force, video, ' '.join(query)


async def _resolve_item(text: str, reply, message):
    if reply is not None:
        directory = ctx.controller.temp_dir(message.chat.id)
        return await ctx.downloader.from_message(reply, ctx.bot, directory)
    if is_youtube(text):
        results = await ctx.search.search(text, limit=1)
        if results:
            return results[0]
        video_id = parse_video_id(text)
        if video_id is None:
            raise DownloadError('unresolvable youtube url')
        return Track(
            video_id=video_id,
            title=video_id,
            duration_seconds=0,
            url=f'https://www.youtube.com/watch?v={video_id}',
        )
    if is_supported_url(text):
        extension = extension_of(text)
        stem = Path(urlparse(text).path).stem or 'media'
        return Media(
            file_id=text,
            title=stem,
            duration_seconds=0,
            file_path='',
            url=text,
            is_video=extension in VIDEO_EXTENSIONS,
        )
    results = await ctx.search.search(text, limit=1)
    if not results:
        raise DownloadError('search produced no results')
    return results[0]


def _unlink_temp(chat_id: int, item) -> None:
    path = getattr(item, 'file_path', None)
    if not path:
        return
    try:
        directory = ctx.controller.temp_dir(chat_id)
        Path(path).resolve().relative_to(directory.resolve())
    except (ValueError, AttributeError, OSError):
        return
    try:
        Path(path).unlink()
    except OSError:
        pass
    item.file_path = None


async def _ensure_assistant(chat_id: int) -> None:
    assistants = getattr(ctx, 'assistants', None)
    bot = getattr(ctx, 'bot', None)
    if assistants is None or bot is None:
        return
    get_member = getattr(bot, 'get_chat_member', None)
    export_link = getattr(bot, 'export_chat_invite_link', None)
    if get_member is None or export_link is None:
        return
    try:
        ready = assistants.ready()
    except Exception:
        return
    for state in ready:
        client = getattr(state, 'client', None)
        user_id = getattr(state, 'user_id', None)
        if client is None or not user_id:
            continue
        join_chat = getattr(client, 'join_chat', None)
        if join_chat is None:
            continue
        try:
            member = await get_member(chat_id, user_id)
        except UserNotParticipant:
            member = None
        except Exception:
            continue
        if member is not None and member.status not in (
            enums.ChatMemberStatus.LEFT,
            enums.ChatMemberStatus.BANNED,
        ):
            continue
        try:
            invite = await export_link(chat_id)
        except ChatAdminRequired:
            logger.warning('cannot invite assistant to %s: bot lacks permission', chat_id)
            return
        except Exception as exc:
            logger.warning('invite link failed for %s: %s', chat_id, type(exc).__name__)
            continue
        if not invite:
            continue
        try:
            await join_chat(invite)
        except Exception as exc:
            logger.warning('assistant join failed for %s: %s', chat_id, type(exc).__name__)


async def _announce_now_playing(sent, message, item, duration: str, user: str) -> None:
    chat_id = message.chat.id
    title = html_escape(item.title)
    url = getattr(item, 'url', '') or ''
    thumbs = getattr(ctx, 'thumbs', None)
    settings = ctx.settings
    thumb_enabled = bool(getattr(settings, 'thumbnails', True))
    card = None
    if thumbs is not None and thumb_enabled and isinstance(item, Track):
        try:
            card = await thumbs.generate(item, channel=item.channel or '', duration=duration)
        except Exception:
            card = None
    markup = player_controls(chat_id, paused=False, labels=_control_labels())
    caption = _t('play_media', url=url, title=title, duration=duration, user=user)
    if card:
        edit_media = getattr(sent, 'edit_media', None)
        if edit_media is not None:
            try:
                await edit_media(
                    InputMediaPhoto(media=card, caption=caption),
                    reply_markup=markup,
                )
                item.message_id = getattr(sent, 'id', 0) or 0
                return
            except Exception as exc:
                logger.warning('card edit failed: %s', type(exc).__name__)
        try:
            sent_msg = await message.reply_photo(
                photo=card, caption=caption, reply_markup=markup
            )
            item.message_id = getattr(sent_msg, 'id', 0) or 0
            return
        except Exception as exc:
            logger.warning('photo announce failed: %s', type(exc).__name__)
    text = _t('play_media', url=url, title=item.title, duration=duration, user=user)
    edit = getattr(sent, 'edit_text', None)
    if edit is not None:
        try:
            await edit(text, reply_markup=markup)
            item.message_id = getattr(sent, 'id', 0) or 0
            return
        except Exception as exc:
            logger.warning('announce edit failed: %s', type(exc).__name__)
    await message.reply_text(text, reply_markup=markup)


async def _maybe_play_log(message, item) -> None:
    database = getattr(ctx, 'database', None)
    bot = getattr(ctx, 'bot', None)
    settings = ctx.settings
    if database is None or bot is None:
        return
    try:
        enabled = await database.logger_enabled()
    except Exception:
        return
    if not enabled:
        return
    log_chat = getattr(settings, 'log_chat_id', 0) if settings is not None else 0
    if not log_chat:
        return
    send = getattr(bot, 'send_message', None)
    if send is None:
        return
    try:
        await send(
            log_chat,
            _t(
                'play_log',
                name=_bot_name(),
                chat=message.chat.id,
                title=html_escape(item.title),
                user=_display_user(message),
            ),
        )
    except Exception:
        pass


async def play(client, message) -> None:
    await _play_impl(client, message, video=False)


async def vplay(client, message) -> None:
    await _play_impl(client, message, video=True)


async def playforce(client, message) -> None:
    await _play_impl(client, message, video=False, force=True)


async def vplayforce(client, message) -> None:
    await _play_impl(client, message, video=True, force=True)


async def _play_impl(client, message, video: bool = False, force: bool = False) -> None:
    if not _is_group(message):
        await message.reply_text(_t('unsupported'))
        return
    chat_id = message.chat.id
    if await _deny_blocked(message):
        return
    settings = ctx.settings
    video_enabled = bool(getattr(settings, 'video_enabled', True))
    text = _arguments(message)
    reply = getattr(message, 'reply_to_message', None)
    flag_force, flag_video, text = _play_flags(
        getattr(message, 'command', None), text
    )
    force = force or flag_force
    video = (video or flag_video) and video_enabled
    if not text and reply is None:
        await message.reply_text(_t('play_usage'))
        return
    sent = await message.reply_text(_t('play_searching'))
    try:
        item = await _resolve_item(text, reply, message)
    except Exception as exc:
        await _send_resolve_error(sent, message, exc)
        return
    if video and isinstance(item, Track):
        item.is_video = True
    item.requested_by = _display_user(message)
    await _play_item(client, message, sent, item, chat_id, force=force)


async def _play_item(client, message, sent, item, chat_id: int, force: bool = False) -> None:
    settings = ctx.settings
    limit = getattr(settings, 'duration_limit', 0) if settings is not None else 0
    if limit and (getattr(item, 'duration_seconds', 0) or 0) > limit:
        _unlink_temp(chat_id, item)
        await _fail(sent, message, 'play_duration_limit', minutes=limit // 60)
        return
    controller = ctx.controller
    if force:
        await controller.stop(chat_id)
    result = await controller.enqueue(chat_id, item)
    if result is AddResult.DUPLICATE:
        _unlink_temp(chat_id, item)
        await _fail(sent, message, 'duplicate')
        return
    if result is AddResult.FULL:
        queue_limit = getattr(settings, 'queue_limit', 0) if settings is not None else 0
        _unlink_temp(chat_id, item)
        await _fail(sent, message, 'play_queue_full', limit=queue_limit)
        return
    controller.own(chat_id, item)
    duration, user = _describe(item)
    if await controller.current(chat_id) is not None:
        position = await ctx.queue.size(chat_id)
        await _fail(
            sent,
            message,
            'play_queued',
            _queue_buttons(chat_id),
            position=position,
            url=item.url or '',
            title=html_escape(item.title),
            duration=duration,
            user=user,
        )
        return
    await _ensure_assistant(chat_id)
    try:
        started = await controller.start(chat_id)
    except NoActiveGroupCall:
        await _fail(sent, message, 'error_no_call')
        return
    current = await controller.current(chat_id)
    if started or current is not None:
        playing = current if current is not None else item
        playing_duration, playing_user = _describe(playing)
        await _announce_now_playing(sent, message, playing, playing_duration, playing_user)
        await _maybe_play_log(message, playing)
    elif getattr(ctx, 'assistants', None) is not None and not ctx.assistants.ready():
        await _fail(sent, message, 'no_assistant', title=item.title)
    else:
        await _fail(sent, message, 'error_no_file', support=_support_chat())


HANDLERS = (
    (play, 'play'),
    (vplay, 'vplay'),
    (playforce, 'playforce'),
    (vplayforce, 'vplayforce'),
)


def register(app) -> None:
    for handler, command in HANDLERS:
        app.add_handler(MessageHandler(handler, filters.command(command)))
