from pyrogram import enums, filters
from pyrogram.handlers import MessageHandler

from ..context import ctx
from ..tools.buttons import help_markup
from .common import (
    GROUP_TYPES,
    _bot_name,
    _help_labels,
    _set_lang,
    _start_keyboard,
    _start_pm_caption,
    _t,
    _track_served,
)

async def start_cmd(client, message) -> None:
    await _set_lang(message)
    user = getattr(message, 'from_user', None)
    chat = getattr(message, 'chat', None)
    chat_type = getattr(chat, 'type', None) if chat is not None else None
    if chat is not None and chat_type == enums.ChatType.PRIVATE:
        caption = _start_pm_caption(message)
        markup = _start_keyboard()
        photo = getattr(ctx.settings, 'start_image', '') or ''
        if photo:
            try:
                await message.reply_photo(photo=photo, caption=caption, reply_markup=markup)
            except Exception:
                await message.reply_text(caption, reply_markup=markup)
        else:
            await message.reply_text(caption, reply_markup=markup)
        if user is not None and getattr(user, 'id', None):
            await _track_served(user_id=user.id)
        return
    await message.reply_text(_t('start_gp', name=_bot_name()))
    if chat is not None and chat_type in GROUP_TYPES:
        await _track_served(chat_id=chat.id)
    elif user is not None and getattr(user, 'id', None):
        await _track_served(user_id=user.id)


async def help_cmd(client, message) -> None:
    await _set_lang(message)
    await message.reply_text(_t('help_menu'), reply_markup=help_markup(_help_labels()))


async def member_joined(client, message) -> None:
    bot = getattr(ctx, 'bot', None)
    bot_id = getattr(getattr(bot, 'me', None), 'id', None)
    if bot_id is None:
        return
    members = getattr(message, 'new_chat_members', None) or []
    if any(getattr(member, 'id', None) == bot_id for member in members):
        await _track_served(chat_id=message.chat.id)


async def member_left(client, message) -> None:
    bot = getattr(ctx, 'bot', None)
    bot_id = getattr(getattr(bot, 'me', None), 'id', None)
    if bot_id is None:
        return
    left = getattr(message, 'left_chat_member', None)
    if left is not None and getattr(left, 'id', None) == bot_id:
        database = getattr(ctx, 'database', None)
        if database is None:
            return
        try:
            await database.remove_chat(message.chat.id)
        except Exception:
            pass


HANDLERS = (
    (start_cmd, 'start'),
    (help_cmd, 'help'),
)


def register(app) -> None:
    for handler, command in HANDLERS:
        app.add_handler(MessageHandler(handler, filters.command(command)))
    app.add_handler(MessageHandler(member_joined, filters.new_chat_members))
    app.add_handler(MessageHandler(member_left, filters.left_chat_member))
