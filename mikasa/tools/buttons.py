from typing import Optional, Tuple

from pyrogram import enums
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

PREFIX = 'mikasa'

ACTIONS = ('pause', 'resume', 'skip', 'stop', 'close', 'status')


def control_data(action: str, chat_id: int) -> str:
    return f'{PREFIX}:{action}:{chat_id}'


def parse_callback(data: str) -> Tuple[Optional[str], Optional[int]]:
    parts = (data or '').split(':')
    if len(parts) != 3 or parts[0] != PREFIX:
        return None, None
    _, action, raw_id = parts
    if action not in ACTIONS:
        return None, None
    try:
        return action, int(raw_id)
    except (TypeError, ValueError):
        return None, None


def player_controls(
    chat_id: int,
    paused: bool = False,
    labels: Optional[dict] = None,
    timer: Optional[str] = None,
) -> InlineKeyboardMarkup:
    labels = labels or {}

    def text(key: str, default: str) -> str:
        return labels.get(key) or default

    rows = []
    if timer:
        rows.append([
            InlineKeyboardButton(
                timer,
                callback_data=control_data('status', chat_id),
                style=enums.ButtonStyle.PRIMARY,
            )
        ])
    if paused:
        toggle = InlineKeyboardButton(
            text('btn_resume', 'Resume'),
            callback_data=control_data('resume', chat_id),
            style=enums.ButtonStyle.PRIMARY,
        )
    else:
        toggle = InlineKeyboardButton(
            text('btn_pause', 'Pause'),
            callback_data=control_data('pause', chat_id),
            style=enums.ButtonStyle.PRIMARY,
        )
    rows.extend([
        [
            toggle,
            InlineKeyboardButton(
                text('btn_skip', 'Skip'),
                callback_data=control_data('skip', chat_id),
                style=enums.ButtonStyle.PRIMARY,
            ),
            InlineKeyboardButton(
                text('btn_stop', 'Stop'),
                callback_data=control_data('stop', chat_id),
                style=enums.ButtonStyle.PRIMARY,
            ),
        ],
        [
            InlineKeyboardButton(
                text('btn_close', 'Close'),
                callback_data=control_data('close', chat_id),
                style=enums.ButtonStyle.DANGER,
            )
        ],
    ])
    return InlineKeyboardMarkup(rows)


HELP_TOPICS = ('play', 'control', 'seek', 'queue', 'auth', 'admin', 'blist', 'ping', 'stats', 'sudo', 'broadcast', 'system')


def start_key(
    bot_username: str = '',
    owner_username: str = '',
    support_chat: str = '',
    support_channel: str = '',
    labels: Optional[dict] = None,
) -> InlineKeyboardMarkup:
    labels = labels or {}

    def text(key: str, default: str) -> str:
        return labels.get(key) or default

    rows = []
    if bot_username:
        rows.append([
            InlineKeyboardButton(
                text('add_me', 'Add Me'),
                url=f'https://t.me/{bot_username}?startgroup=true',
                style=enums.ButtonStyle.PRIMARY,
            )
        ])
    rows.append([
        InlineKeyboardButton(
            text('btn_help', 'Help and Commands'),
            callback_data='mikasa:start:help',
            style=enums.ButtonStyle.PRIMARY,
        )
    ])
    row = []
    if owner_username:
        row.append(
            InlineKeyboardButton(
                text('owner', 'Owner'),
                url=f'https://t.me/{owner_username.lstrip("@")}',
                style=enums.ButtonStyle.PRIMARY,
            )
        )
    if support_chat:
        row.append(
            InlineKeyboardButton(
                text('support', 'Support'),
                url=support_chat,
                style=enums.ButtonStyle.PRIMARY,
            )
        )
    if row:
        rows.append(row)
    if support_channel:
        rows.append([
            InlineKeyboardButton(
                text('channel', 'Channel'),
                url=support_channel,
                style=enums.ButtonStyle.PRIMARY,
            )
        ])
    return InlineKeyboardMarkup(rows)


def help_markup(
    labels: Optional[dict] = None,
    back: bool = False,
    origin: str = 'help',
) -> InlineKeyboardMarkup:
    labels = labels or {}
    if origin == 'start':
        topic_data = lambda topic: f'mikasa:start:{topic}'
        back_data = 'mikasa:start:help'
        menu_back_data = 'mikasa:start:back'
    else:
        topic_data = lambda topic: f'mikasa:help:{topic}'
        back_data = 'mikasa:help:back'
        menu_back_data = None
    if back:
        return InlineKeyboardMarkup([[
            InlineKeyboardButton(
                labels.get('back') or 'Back',
                callback_data=back_data,
                style=enums.ButtonStyle.PRIMARY,
            ),
            InlineKeyboardButton(
                labels.get('btn_close') or 'Close',
                callback_data='mikasa:help:close',
                style=enums.ButtonStyle.DANGER,
            ),
        ]])
    buttons = [
        InlineKeyboardButton(
            labels.get(f'help_{index}') or topic,
            callback_data=topic_data(topic),
            style=enums.ButtonStyle.PRIMARY,
        )
        for index, topic in enumerate(HELP_TOPICS)
    ]
    rows = [buttons[i:i + 3] for i in range(0, len(buttons), 3)]
    if menu_back_data is not None:
        rows.append([
            InlineKeyboardButton(
                labels.get('back') or 'Back',
                callback_data=menu_back_data,
                style=enums.ButtonStyle.PRIMARY,
            ),
            InlineKeyboardButton(
                labels.get('btn_close') or 'Close',
                callback_data='mikasa:help:close',
                style=enums.ButtonStyle.DANGER,
            ),
        ])
    return InlineKeyboardMarkup(rows)


def queue_actions(
    chat_id: int,
    bot_username: str = '',
    add_label: str = 'Add Me',
    close_label: str = 'Close',
) -> InlineKeyboardMarkup:
    row = []
    if bot_username:
        row.append(
            InlineKeyboardButton(
                add_label,
                url=f'https://t.me/{bot_username}?startgroup=true',
                style=enums.ButtonStyle.PRIMARY,
            )
        )
    row.append(
        InlineKeyboardButton(
            close_label,
            callback_data=control_data('close', chat_id),
            style=enums.ButtonStyle.DANGER,
        )
    )
    return InlineKeyboardMarkup([row])


def select_data(video_id: str) -> str:
    return f'{PREFIX}:select:{video_id}'


def lang_data(code: str) -> str:
    return f'{PREFIX}:lang:{code}'


def lang_markup(
    chat_id: int,
    current: str = '',
    names: Optional[dict] = None,
    close_label: str = 'Close',
) -> InlineKeyboardMarkup:
    names = names or {}
    codes = sorted(names)
    rows = []
    for index in range(0, len(codes), 2):
        row = []
        for code in codes[index:index + 2]:
            label = names[code]
            if code == current:
                label = f'[ {label} ]'
            row.append(
                InlineKeyboardButton(
                    label,
                    callback_data=lang_data(code),
                    style=enums.ButtonStyle.PRIMARY,
                )
            )
        rows.append(row)
    rows.append([
        InlineKeyboardButton(
            close_label,
            callback_data=control_data('close', chat_id),
            style=enums.ButtonStyle.DANGER,
        )
    ])
    return InlineKeyboardMarkup(rows)


def settings_data(action: str) -> str:
    return f'{PREFIX}:settings:{action}'


def settings_markup(
    play_mode: bool = False,
    lang_name: str = '',
    labels: Optional[dict] = None,
) -> InlineKeyboardMarkup:
    labels = labels or {}

    def text(key: str, default: str) -> str:
        return labels.get(key) or default

    mode = text('play_mode_admins', 'Admins Only') if play_mode else text('play_mode_everyone', 'Everyone')
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                text('play_mode', 'Play Mode'),
                callback_data=settings_data('noop'),
                style=enums.ButtonStyle.DEFAULT,
            ),
            InlineKeyboardButton(
                mode,
                callback_data=settings_data('play'),
                style=enums.ButtonStyle.PRIMARY,
            ),
        ],
        [
            InlineKeyboardButton(
                text('language', 'Language'),
                callback_data=settings_data('noop'),
                style=enums.ButtonStyle.DEFAULT,
            ),
            InlineKeyboardButton(
                lang_name or 'English',
                callback_data=settings_data('lang'),
                style=enums.ButtonStyle.PRIMARY,
            ),
        ],
    ])


def search_results(
    chat_id: int,
    entries,
    close_label: str = 'Close',
) -> InlineKeyboardMarkup:
    rows = []
    for video_id, label in entries:
        rows.append([
            InlineKeyboardButton(
                label,
                callback_data=select_data(video_id),
                style=enums.ButtonStyle.PRIMARY,
            )
        ])
    rows.append([
        InlineKeyboardButton(
            close_label,
            callback_data=control_data('close', chat_id),
            style=enums.ButtonStyle.DANGER,
        )
    ])
    return InlineKeyboardMarkup(rows)
