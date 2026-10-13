import unittest
from types import SimpleNamespace

from pyrogram import enums

from mikasa import plugins
from mikasa.context import ctx
from mikasa.plugins import callbacks
from mikasa.core.lang import Language


class FakeQueryMessage:
    def __init__(self, photo=None):
        self.photo = photo
        self.deleted = False
        self.markups = []
        self.replies = []
        self.reply_markups = []
        self.text_edits = []
        self.caption_edits = []

    async def delete(self):
        self.deleted = True

    async def edit_reply_markup(self, reply_markup):
        self.markups.append(reply_markup)

    async def edit_text(self, text, reply_markup=None):
        self.text_edits.append({"text": text, "markup": reply_markup})

    async def edit_caption(self, caption, reply_markup=None):
        self.caption_edits.append({"caption": caption, "markup": reply_markup})

    async def reply_text(self, text, reply_markup=None):
        self.replies.append(text)
        self.reply_markups.append(reply_markup)


class FakeQuery:
    def __init__(self, data, user_id=1, admin=True, message=None):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id, first_name="Tester")
        self.message = message if message is not None else FakeQueryMessage()
        self.answers = []

    async def answer(self, text="", show_alert=False, url=None):
        self.answers.append((text, show_alert, url))


class FakeClient:
    def __init__(self, admin=True):
        self.admin = admin

    async def get_chat_member(self, chat_id, user_id):
        status = (
            enums.ChatMemberStatus.ADMINISTRATOR
            if self.admin
            else enums.ChatMemberStatus.MEMBER
        )
        return SimpleNamespace(status=status)


class FakeController:
    def __init__(self):
        self._current = None
        self._paused = False
        self.calls = []

    def set_current(self, item):
        self._current = item

    async def current(self, chat_id):
        return self._current

    def is_paused(self, chat_id):
        return self._paused

    async def pause(self, chat_id):
        self.calls.append("pause")
        self._paused = True
        return True

    async def resume(self, chat_id):
        self.calls.append("resume")
        self._paused = False
        return True

    async def skip(self, chat_id):
        self.calls.append("skip")
        return True

    async def stop(self, chat_id):
        self.calls.append("stop")
        self._current = None
        return True


def track():
    return SimpleNamespace(video_id="vid1", title="Song")


class CallbackTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._old = {
            name: getattr(ctx, name, None) for name in (
                "settings", "language", "controller", "assistants", "bot"
            )
        }
        self.controller = FakeController()
        ctx.settings = SimpleNamespace(owner_id=999, default_language="en")
        ctx.language = Language()
        ctx.controller = self.controller
        ctx.assistants = None
        ctx.bot = None
        self.addCleanup(self._restore)

    def _restore(self):
        for name, value in self._old.items():
            setattr(ctx, name, value)


class CloseTests(CallbackTestCase):
    async def test_close_deletes_message(self):
        query = FakeQuery("mikasa:close:10")
        await callbacks.control_cb(FakeClient(), query)
        self.assertTrue(query.message.deleted)
        self.assertEqual(query.answers, [("", False, None)])

    async def test_unknown_data_ignored(self):
        query = FakeQuery("mikasa:dance:10")
        await callbacks.control_cb(FakeClient(), query)
        self.assertEqual(query.answers, [])
        self.assertFalse(query.message.deleted)


class PauseCallbackTests(CallbackTestCase):
    async def test_non_admin_denied(self):
        self.controller.set_current(track())
        query = FakeQuery("mikasa:pause:10", user_id=5)
        await callbacks.control_cb(FakeClient(admin=False), query)
        self.assertEqual(
            query.answers, [("You need to be an admin to do that.", True, None)]
        )
        self.assertEqual(self.controller.calls, [])

    async def test_pause_without_current(self):
        query = FakeQuery("mikasa:pause:10")
        await callbacks.control_cb(FakeClient(), query)
        self.assertEqual(
            query.answers, [("The bot isn't streaming in the video chat.", True, None)]
        )

    async def test_pause_twice(self):
        self.controller.set_current(track())
        first = FakeQuery("mikasa:pause:10")
        await callbacks.control_cb(FakeClient(), first)
        self.assertEqual(
            first.answers,
            [("<b><blockquote>Stream paused by</b> Tester</blockquote>", False, None)],
        )
        self.assertEqual(len(first.message.markups), 1)
        second = FakeQuery("mikasa:pause:10")
        await callbacks.control_cb(FakeClient(), second)
        self.assertEqual(
            second.answers,
            [("Do you remember that you resumed the stream?", True, None)],
        )

    async def test_resume_without_pause(self):
        self.controller.set_current(track())
        query = FakeQuery("mikasa:resume:10")
        await callbacks.control_cb(FakeClient(), query)
        self.assertEqual(
            query.answers, [("Do you remember that you paused the stream?", True, None)]
        )


class SkipStopCallbackTests(CallbackTestCase):
    async def test_skip_sends_status_and_deletes(self):
        self.controller.set_current(track())
        query = FakeQuery("mikasa:skip:10")
        await callbacks.control_cb(FakeClient(), query)
        self.assertEqual(self.controller.calls, ["skip"])
        self.assertEqual(
            query.message.replies,
            ["<blockquote>Stream skipped\n\nBy : Tester</blockquote>"],
        )
        markup = query.message.reply_markups[-1]
        self.assertEqual(len(markup.inline_keyboard), 1)
        self.assertEqual(
            markup.inline_keyboard[0][-1].callback_data, "mikasa:close:10"
        )
        self.assertTrue(query.message.deleted)

    async def test_stop_sends_status_and_deletes(self):
        self.controller.set_current(track())
        query = FakeQuery("mikasa:stop:10")
        await callbacks.control_cb(FakeClient(), query)
        self.assertEqual(self.controller.calls, ["stop"])
        self.assertEqual(
            query.message.replies,
            ["<blockquote>Stream Ended / Stopped\n\nBy : Tester</blockquote>"],
        )
        markup = query.message.reply_markups[-1]
        self.assertEqual(len(markup.inline_keyboard), 1)
        self.assertEqual(
            markup.inline_keyboard[0][-1].callback_data, "mikasa:close:10"
        )
        self.assertTrue(query.message.deleted)


class HelpCallbackTests(CallbackTestCase):
    async def test_topic_shows_text_with_back_buttons(self):
        query = FakeQuery("mikasa:help:play")
        await callbacks.help_cb(FakeClient(), query)
        self.assertEqual(query.answers, [("", False, None)])
        self.assertEqual(len(query.message.text_edits), 1)
        edit = query.message.text_edits[0]
        self.assertIn("Play commands:", edit["text"])
        self.assertIsNotNone(edit["markup"])

    async def test_back_returns_to_menu(self):
        query = FakeQuery("mikasa:help:back")
        await callbacks.help_cb(FakeClient(), query)
        self.assertEqual(len(query.message.text_edits), 1)
        self.assertIn("Click the buttons below", query.message.text_edits[0]["text"])

    async def test_close_deletes_message(self):
        query = FakeQuery("mikasa:help:close")
        await callbacks.help_cb(FakeClient(), query)
        self.assertTrue(query.message.deleted)

    async def test_unknown_topic_ignored(self):
        query = FakeQuery("mikasa:help:nope")
        await callbacks.help_cb(FakeClient(), query)
        self.assertEqual(query.message.text_edits, [])

    async def test_bare_help_deep_links_when_username_known(self):
        ctx.bot = SimpleNamespace(me=SimpleNamespace(username="SomeBot"))
        try:
            query = FakeQuery("mikasa:help")
            await callbacks.help_cb(FakeClient(), query)
            self.assertEqual(
                query.answers, [("", False, "https://t.me/SomeBot?start=help")]
            )
            self.assertEqual(query.message.text_edits, [])
        finally:
            ctx.bot = None


class StartCallbackTests(CallbackTestCase):
    async def test_help_edits_same_message_to_menu(self):
        query = FakeQuery("mikasa:start:help")
        await callbacks.start_cb(FakeClient(), query)
        self.assertEqual(query.answers, [("", False, None)])
        self.assertEqual(len(query.message.text_edits), 1)
        edit = query.message.text_edits[0]
        self.assertIn("Click the buttons below", edit["text"])
        datas = [
            button.callback_data
            for row in edit["markup"].inline_keyboard
            for button in row
        ]
        self.assertIn("mikasa:start:back", datas)

    async def test_topic_back_returns_to_menu(self):
        topic_query = FakeQuery("mikasa:start:play")
        await callbacks.start_cb(FakeClient(), topic_query)
        self.assertIn(
            "Play commands:", topic_query.message.text_edits[0]["text"]
        )
        back_datas = [
            button.callback_data
            for row in topic_query.message.text_edits[0]["markup"].inline_keyboard
            for button in row
        ]
        self.assertIn("mikasa:start:help", back_datas)

    async def test_back_rebuilds_start_card(self):
        query = FakeQuery("mikasa:start:back", message=FakeQueryMessage(photo=True))
        await callbacks.start_cb(FakeClient(), query)
        self.assertEqual(len(query.message.caption_edits), 1)
        self.assertIn("Tester", query.message.caption_edits[0]["caption"])

    async def test_unknown_start_data_ignored(self):
        query = FakeQuery("mikasa:start:dance")
        await callbacks.start_cb(FakeClient(), query)
        self.assertEqual(query.answers, [])
        self.assertEqual(query.message.text_edits, [])


class RegisterCallbacksTests(unittest.TestCase):
    def test_register_adds_handler(self):
        class App:
            def __init__(self):
                self.handlers = []

            def add_handler(self, handler, group=0):
                self.handlers.append(handler)
                return (handler, group)

        app = App()
        callbacks.register(app)
        self.assertEqual(len(app.handlers), 3)

    def test_loader_registers_everything(self):
        from pyrogram.handlers import CallbackQueryHandler, MessageHandler

        class App:
            def __init__(self):
                self.handlers = []

            def add_handler(self, handler, group=0):
                self.handlers.append(handler)
                return (handler, group)

        app = App()
        loaded = plugins.load_plugins(app)
        self.assertEqual(len(loaded), 19)
        kinds = [type(handler) for handler in app.handlers]
        self.assertEqual(sum(1 for kind in kinds if kind is MessageHandler), 43)
        self.assertEqual(sum(1 for kind in kinds if kind is CallbackQueryHandler), 4)


if __name__ == "__main__":
    unittest.main()
