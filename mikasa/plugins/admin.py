from html import escape as html_escape

from pyrogram import filters
from pyrogram.handlers import MessageHandler

from ..context import ctx
from ..logging_config import get_logger
from .common import _bot_name, _need_database, _owner_only, _set_lang, _t

logger = get_logger('mikasa.plugins.admin')

_LOG_PATH = 'log.txt'


async def _run_eval(code: str) -> str:
    import asyncio
    import contextlib
    import io
    import traceback

    namespace: dict = {}
    buffer = io.StringIO()
    try:
        compiled = compile(code, '<eval>', 'eval')
    except SyntaxError:
        compiled = None
    try:
        with contextlib.redirect_stdout(buffer):
            if compiled is not None:
                result = eval(compiled, namespace)
                if asyncio.iscoroutine(result):
                    result = await result
            else:
                lines = ['async def __mikasa_eval__():']
                lines.extend('    ' + line for line in code.splitlines() or ['pass'])
                exec(compile('\n'.join(lines), '<eval>', 'exec'), namespace)
                result = await namespace['__mikasa_eval__']()
    except Exception:
        details = traceback.format_exc(limit=3)[-1500:]
        return _t('eval_error') + '<code>' + html_escape(details) + '</code>'
    output = buffer.getvalue()
    if result is not None:
        if output and not output.endswith('\n'):
            output += '\n'
        output += repr(result)
    output = output.strip()
    if not output:
        output = '…'
    return _t('eval_out', output=html_escape(output[:2000]))


async def eval_cmd(client, message) -> None:
    await _set_lang(message)
    import asyncio

    if not await _owner_only(client, message):
        return
    text = getattr(message, 'text', None) or ''
    parts = text.split(None, 1)
    if len(parts) < 2 or not parts[1].strip():
        await message.reply_text(_t('eval_inp'))
        return
    try:
        result = await asyncio.wait_for(_run_eval(parts[1]), timeout=30)
    except asyncio.TimeoutError:
        result = _t('eval_error') + '<code>timed out after 30s</code>'
    await message.reply_text(result)


async def logs_cmd(client, message) -> None:
    await _set_lang(message)
    import os

    if not await _owner_only(client, message):
        return
    sent = await message.reply_text(_t('log_fetch'))
    if not os.path.exists(_LOG_PATH):
        edit = getattr(sent, 'edit_text', None)
        if edit is not None:
            try:
                await edit(_t('log_not_found'))
                return
            except Exception:
                pass
        await message.reply_text(_t('log_not_found'))
        return
    reply_document = getattr(message, 'reply_document', None)
    if reply_document is None:
        await message.reply_text(_t('log_not_found'))
        return
    try:
        await reply_document(document=_LOG_PATH, caption=_t('log_sent', name=_bot_name()))
    except Exception:
        await message.reply_text(_t('error'))


async def logger_cmd(client, message) -> None:
    await _set_lang(message)
    if not await _owner_only(client, message):
        return
    command = (getattr(message, 'command', None) or [''])[0]
    args = (getattr(message, 'command', None) or [])[1:]
    if not args or args[0] not in ('on', 'off'):
        await message.reply_text(_t('logger_usage', command=command))
        return
    database = await _need_database(message)
    if database is None:
        return
    try:
        await database.set_logger(args[0] == 'on')
    except Exception:
        await message.reply_text(_t('error'))
        return
    await message.reply_text(_t('logger_on' if args[0] == 'on' else 'logger_off'))


def _replace_process() -> None:
    import os
    import sys

    os.execl(sys.executable, sys.executable, '-m', 'mikasa')


def _clean_restart_dirs() -> None:
    import shutil

    for directory in ('cache', 'downloads'):
        try:
            shutil.rmtree(directory, ignore_errors=True)
        except Exception:
            pass


async def _graceful_stop() -> None:
    controller = getattr(ctx, 'controller', None)
    if controller is not None:
        try:
            await controller.close()
        except Exception:
            pass
    assistants = getattr(ctx, 'assistants', None)
    if assistants is not None:
        try:
            await assistants.stop()
        except Exception:
            pass
    bot = getattr(ctx, 'bot', None)
    if bot is not None:
        try:
            await bot.exit()
        except Exception:
            pass
    database = getattr(ctx, 'database', None)
    if database is not None:
        try:
            await database.close()
        except Exception:
            pass


async def restart_cmd(client, message) -> None:
    await _set_lang(message)
    import asyncio

    if not await _owner_only(client, message):
        return
    sent = await message.reply_text(_t('restarting'))
    await _graceful_stop()
    edit = getattr(sent, 'edit_text', None)
    if edit is not None:
        try:
            await edit(_t('restarted'))
        except Exception:
            pass
    else:
        await message.reply_text(_t('restarted'))
    _clean_restart_dirs()
    await asyncio.sleep(2)
    try:
        _replace_process()
    except Exception as exc:
        logger.warning('restart failed: %s', type(exc).__name__)
        await message.reply_text(_t('error'))


HANDLERS = (
    (eval_cmd, 'eval'),
    (logs_cmd, 'logs'),
    (logger_cmd, 'logger'),
    (restart_cmd, 'restart'),
)


def register(app) -> None:
    for handler, command in HANDLERS:
        app.add_handler(MessageHandler(handler, filters.command(command)))
