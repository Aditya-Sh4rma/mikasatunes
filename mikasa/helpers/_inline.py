from typing import Optional, Tuple

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

PREFIX = 'mikasa'

ACTIONS = ('pause', 'resume', 'skip', 'stop', 'close')


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
) -> InlineKeyboardMarkup:
    labels = labels or {}

    def text(key: str, default: str) -> str:
        return labels.get(key) or default

    if paused:
        toggle = InlineKeyboardButton(
            text('btn_resume', 'Resume'),
            callback_data=control_data('resume', chat_id),
        )
    else:
        toggle = InlineKeyboardButton(
            text('btn_pause', 'Pause'),
            callback_data=control_data('pause', chat_id),
        )
    rows = [
        [
            toggle,
            InlineKeyboardButton(
                text('btn_skip', 'Skip'),
                callback_data=control_data('skip', chat_id),
            ),
            InlineKeyboardButton(
                text('btn_stop', 'Stop'),
                callback_data=control_data('stop', chat_id),
            ),
        ],
        [
            InlineKeyboardButton(
                text('btn_close', 'Close'),
                callback_data=control_data('close', chat_id),
            )
        ],
    ]
    return InlineKeyboardMarkup(rows)


HELP_TOPICS = ('admins', 'auth', 'blist', 'lang', 'ping', 'play', 'queue', 'stats', 'sudo')


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
            )
        ])
    rows.append([
        InlineKeyboardButton(
            text('btn_help', 'Help and Commands'), callback_data='mikasa:start:help'
        )
    ])
    row = []
    if owner_username:
        row.append(
            InlineKeyboardButton(
                text('owner', 'Owner'),
                url=f'https://t.me/{owner_username.lstrip("@")}',
            )
        )
    if support_chat:
        row.append(
            InlineKeyboardButton(text('support', 'Support'), url=support_chat)
        )
    if row:
        rows.append(row)
    if support_channel:
        rows.append([
            InlineKeyboardButton(text('channel', 'Channel'), url=support_channel)
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
                labels.get('back') or 'Back', callback_data=back_data
            ),
            InlineKeyboardButton(
                labels.get('btn_close') or 'Close', callback_data='mikasa:help:close'
            ),
        ]])
    buttons = [
        InlineKeyboardButton(
            labels.get(f'help_{index}') or topic,
            callback_data=topic_data(topic),
        )
        for index, topic in enumerate(HELP_TOPICS)
    ]
    rows = [buttons[i:i + 3] for i in range(0, len(buttons), 3)]
    if menu_back_data is not None:
        rows.append([
            InlineKeyboardButton(
                labels.get('back') or 'Back', callback_data=menu_back_data
            ),
            InlineKeyboardButton(
                labels.get('btn_close') or 'Close', callback_data='mikasa:help:close'
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
            )
        )
    row.append(
        InlineKeyboardButton(
            close_label,
            callback_data=control_data('close', chat_id),
        )
    )
    return InlineKeyboardMarkup([row])


def select_data(video_id: str) -> str:
    return f'{PREFIX}:select:{video_id}'


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
            )
        ])
    rows.append([
        InlineKeyboardButton(
            close_label,
            callback_data=control_data('close', chat_id),
        )
    ])
    return InlineKeyboardMarkup(rows)
