import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from pyrogram import enums

from mikasa import plugins
from mikasa.context import ctx
from mikasa.exceptions import DownloadError
from mikasa.helpers._dataclass import ChatSettings, Media, Track
from mikasa.plugins import active, admin, auth, blacklist, broadcast, loop, ping, play
from mikasa.plugins import queue as queue_plugin
from mikasa.plugins import search as search_plugin
from mikasa.plugins import seek, start, stats, sudo
from mikasa.plugins import pause as pause_plugin
from mikasa.plugins import resume as resume_plugin
from mikasa.plugins import skip as skip_plugin
from mikasa.plugins import stop as stop_plugin
from mikasa.core.calls import PlaybackBackend, Player
from mikasa.core.lang import Language
from mikasa.helpers._queue import Queue


class FakeState:
    def __init__(self, slot):
        self.slot = slot
        self.ready = True


class FakePool:
    def __init__(self, slots=(1,)):
        self._states = {slot: FakeState(slot) for slot in slots}
        self._claims = {}

    def get(self, slot):
        return self._states.get(slot)

    def claimed_slot(self, chat_id):
        return self._claims.get(chat_id)

    def slots(self):
        return list(self._states)

    async def claim(self, chat_id):
        return await self.claim_specific(chat_id, None)

    async def claim_specific(self, chat_id, slot):
        claimed = self._claims.get(chat_id)
        if claimed is not None:
            return self._states[claimed]
        if slot is not None:
            state = self._states.get(slot)
            if state is not None and state.ready and slot not in set(self._claims.values()):
                self._claims[chat_id] = slot
                return state
        used = set(self._claims.values())
        for slot, state in self._states.items():
            if state.ready and slot not in used:
                self._claims[chat_id] = slot
                return state
        return None

    async def release(self, chat_id):
        self._claims.pop(chat_id, None)


class FakeBackend(PlaybackBackend):
    def __init__(self):
        self.played = []
        self.stopped = []
        self.left = []
        self.paused = []
        self.resumed = []

    async def play(self, chat_id, file_path, is_video=False):
        self.played.append((chat_id, file_path, is_video))

    async def stop(self, chat_id):
        self.stopped.append(chat_id)

    async def leave(self, chat_id):
        self.left.append(chat_id)

    async def pause(self, chat_id):
        self.paused.append(chat_id)
        return True

    async def resume(self, chat_id):
        self.resumed.append(chat_id)
        return True


class FakeIntake:
    async def from_message(self, message, client, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / 'replied.mp3'
        path.write_text('data')
        return Media(file_id='tg1', title='Replied', duration_seconds=3, file_path=str(path))

    async def from_url(self, url, directory, title=None, is_video=False):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / 'url.mp3'
        path.write_text('data')
        return Media(file_id=url, title=title or 'url', duration_seconds=0, file_path=str(path), url=url, is_video=is_video)


class FakeSearch:
    def __init__(self, tracks=None):
        self.tracks = list(tracks or [])
        self.queries = []

    async def search(self, query, limit=5):
        self.queries.append(query)
        return self.tracks[:limit]


class FakeClient:
    def __init__(self, admin=True, members=(), chats=None, users=None, admin_ids=None):
        self.admin = admin
        self._members = tuple(members)
        self._chats = chats or {}
        self._users = users or {}
        self._admin_ids = admin_ids

    async def get_chat_member(self, chat_id, user_id):
        if self._admin_ids is not None:
            is_admin = user_id in self._admin_ids
        else:
            is_admin = self.admin
        status = (
            enums.ChatMemberStatus.ADMINISTRATOR
            if is_admin
            else enums.ChatMemberStatus.MEMBER
        )
        return SimpleNamespace(status=status)

    async def get_chat_members(self, chat_id, filter=None):
        for member in self._members:
            yield member

    async def get_chat(self, username):
        if username in self._chats:
            return SimpleNamespace(id=self._chats[username])
        raise ValueError("no such chat")

    async def get_users(self, user_id):
        if user_id in self._users:
            return self._users[user_id]
        raise ValueError("no such user")


class FakeMessage:
    def __init__(self, text='', chat_id=10, user_id=1, command=None, reply=None, chat_type=enums.ChatType.SUPERGROUP):
        self.text = text
        self.caption = None
        self.command = command if command is not None else []
        self.chat = SimpleNamespace(id=chat_id, type=chat_type)
        self.from_user = SimpleNamespace(id=user_id, first_name='Tester')
        self.reply_to_message = reply
        self.replies = []
        self.markups = []
        self.photos = []
        self.documents = []
        self.forwarded = []
        self.copied = []
        self.sent_messages = []

    async def reply_text(self, text, reply_markup=None):
        self.replies.append(text)
        self.markups.append(reply_markup)
        sent = FakeSentMessage()
        self.sent_messages.append(sent)
        return sent

    async def reply_photo(self, photo, caption=None, reply_markup=None):
        self.photos.append({"photo": photo, "caption": caption, "markup": reply_markup})
        sent = FakeSentMessage()
        self.sent_messages.append(sent)
        return sent

    async def reply_document(self, document, caption=None):
        self.documents.append({"document": document, "caption": caption})
        sent = FakeSentMessage()
        self.sent_messages.append(sent)
        return sent

    async def forward(self, chat_id):
        self.forwarded.append(chat_id)
        return SimpleNamespace(id=1)

    async def copy(self, chat_id):
        self.copied.append(chat_id)
        return SimpleNamespace(id=1)


class FakeSentMessage:
    def __init__(self):
        self.id = 1000 + (id(self) % 9000)
        self.text_edits = []
        self.media_edits = []
        self.deleted = False
        self.replies = []

    async def edit_text(self, text, reply_markup=None):
        self.text_edits.append({"text": text, "markup": reply_markup})

    async def edit_media(self, media, reply_markup=None):
        self.media_edits.append({"media": media, "markup": reply_markup})

    async def delete(self):
        self.deleted = True

    async def reply_text(self, text):
        self.replies.append(text)


def track(video_id='vid1', title='Song'):
    return Track(
        video_id=video_id,
        title=title,
        duration_seconds=10,
        url=f'https://www.youtube.com/watch?v={video_id}',
    )


class CommandTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.pool = FakePool()
        self.backend = FakeBackend()
        self.queue = Queue(limit=3)
        self.search = FakeSearch()
        self.intake = FakeIntake()
        self.player = Player(
            self.pool,
            self.queue,
            lambda state: self.backend,
            resolver=self._resolve,
            temp_root=self.root,
        )
        ctx.controller = self.player
        ctx.queue = self.queue
        ctx.settings = SimpleNamespace(owner_id=999, default_language='en')
        ctx.language = Language()
        ctx.search = self.search
        ctx.downloader = self.intake
        ctx.bot = SimpleNamespace(download_media=None)

    def tearDown(self):
        self._tmp.cleanup()

    async def _resolve(self, chat_id, item, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        safe = str(item.id).replace('/', '_').replace(':', '_')
        path = directory / f'{safe}.mp3'
        path.write_text('data')
        return path


class PlayTests(CommandTestCase):
    async def test_play_search_starts_playback(self):
        self.search.tracks = [track()]
        message = FakeMessage(text='/play song', command=['play', 'song'])
        await play.play(FakeClient(), message)
        current = await self.player.current(10)
        self.assertEqual(current.id, 'vid1')
        self.assertEqual(len(self.backend.played), 1)
        sent = message.sent_messages[-1]
        self.assertEqual(
            [edit["text"] for edit in sent.text_edits],
            ['<blockquote>Started Streaming |</blockquote>\n'
             '<blockquote>Title : <a href=https://www.youtube.com/watch?v=vid1>Song</a>\n'
             'Duration : 0:10 Minutes\n'
             'Requested By : Tester</blockquote>'],
        )

    async def test_play_direct_url_queues_media(self):
        message = FakeMessage(text='/play url', command=['play', 'https://host/song.mp3'])
        await play.play(FakeClient(), message)
        current = await self.player.current(10)
        self.assertIsInstance(current, Media)
        self.assertEqual(current.url, 'https://host/song.mp3')

    async def test_play_without_argument_shows_usage(self):
        message = FakeMessage(text='/play', command=['play'])
        await play.play(FakeClient(), message)
        self.assertEqual(
            message.replies,
            ['<blockquote><b>Usage:</b>\n\n<code>/play attention</code></blockquote>'],
        )

    async def test_play_no_results(self):
        self.search.tracks = []
        message = FakeMessage(text='/play song', command=['play', 'song'])
        await play.play(FakeClient(), message)
        sent = message.sent_messages[-1]
        self.assertEqual(
            [edit["text"] for edit in sent.text_edits],
            ['<blockquote>Failed to process the query.\n\n'
             'If the issue persists, report it to the '
             '<a href=https://t.me/>support chat</a>.</blockquote>'],
        )

    async def test_play_duplicate(self):
        item = track()
        await self.player.enqueue(10, item)
        self.search.tracks = [item]
        message = FakeMessage(text='/play song', command=['play', 'song'])
        await play.play(FakeClient(), message)
        sent = message.sent_messages[-1]
        self.assertEqual(
            [edit["text"] for edit in sent.text_edits],
            ['That item is already in the queue.'],
        )

    async def test_play_reply_downloads_and_plays(self):
        reply = SimpleNamespace()
        message = FakeMessage(text='/play', command=['play'], reply=reply)
        await play.play(FakeClient(), message)
        current = await self.player.current(10)
        self.assertIsInstance(current, Media)
        self.assertTrue((self.root / '10' / 'replied.mp3').exists())

    async def test_play_full_queue_cleans_download(self):
        self.player = Player(
            self.pool,
            Queue(limit=1),
            lambda state: self.backend,
            resolver=self._resolve,
            temp_root=self.root,
        )
        ctx.controller = self.player
        ctx.queue = self.player._queue
        ctx.settings = SimpleNamespace(
            owner_id=999, default_language='en', queue_limit=1
        )
        await self.player.enqueue(10, track('other'))
        reply = SimpleNamespace()
        message = FakeMessage(text='/play', command=['play'], reply=reply)
        await play.play(FakeClient(), message)
        sent = message.sent_messages[-1]
        self.assertEqual(
            [edit["text"] for edit in sent.text_edits],
            ['The queue limit (1) has been reached. Please wait for the currently '
             'queued tracks to finish playing, then try again.'],
        )
        self.assertFalse((self.root / '10' / 'replied.mp3').exists())


class ControlTests(CommandTestCase):
    async def test_skip_non_admin_denied(self):
        message = FakeMessage(text='/skip', command=['skip'], user_id=5)
        await skip_plugin.skip(FakeClient(admin=False), message)
        self.assertEqual(message.replies, ['You need to be an admin to do that.'])
        self.assertEqual(self.backend.stopped, [])

    async def test_skip_advances(self):
        await self.player.enqueue(10, track('a', 'First'))
        await self.player.enqueue(10, track('b', 'Second'))
        await self.player.start(10)
        message = FakeMessage(text='/skip', command=['skip'])
        await skip_plugin.skip(FakeClient(admin=True), message)
        self.assertEqual(
            message.replies, ['<blockquote>Stream skipped\n\nBy : Tester</blockquote>']
        )
        self.assertEqual((await self.player.current(10)).id, 'b')
        markup = message.markups[-1]
        self.assertEqual(len(markup.inline_keyboard), 1)
        self.assertEqual(
            markup.inline_keyboard[0][-1].callback_data, 'mikasa:close:10'
        )

    async def test_stop_admin(self):
        await self.player.enqueue(10, track())
        await self.player.start(10)
        message = FakeMessage(text='/stop', command=['stop'])
        await stop_plugin.stop(FakeClient(admin=True), message)
        self.assertEqual(
            message.replies,
            ['<blockquote>Stream Ended / Stopped\n\nBy : Tester</blockquote>'],
        )
        self.assertIsNone(self.pool.claimed_slot(10))
        markup = message.markups[-1]
        self.assertEqual(len(markup.inline_keyboard), 1)
        self.assertEqual(
            markup.inline_keyboard[0][-1].callback_data, 'mikasa:close:10'
        )

    async def test_pause_without_playback(self):
        message = FakeMessage(text='/pause', command=['pause'])
        await pause_plugin.pause(FakeClient(admin=True), message)
        self.assertEqual(message.replies, ["The bot isn't streaming in the video chat."])

    async def test_pause_and_resume(self):
        await self.player.enqueue(10, track())
        await self.player.start(10)
        pauser = FakeMessage(text='/pause', command=['pause'])
        await pause_plugin.pause(FakeClient(admin=True), pauser)
        self.assertEqual(
            pauser.replies, ['<b><blockquote>Stream paused by</b> Tester</blockquote>']
        )
        resumer = FakeMessage(text='/resume', command=['resume'])
        await resume_plugin.resume(FakeClient(admin=True), resumer)
        self.assertEqual(resumer.replies, ['<b>Stream resumed by</b> Tester'])


class QueueCommandTests(CommandTestCase):
    async def test_queue_empty(self):
        message = FakeMessage(text='/queue', command=['queue'])
        await queue_plugin.queue_cmd(FakeClient(), message)
        self.assertEqual(message.replies, ["The bot isn't streaming in the video chat."])

    async def test_queue_lists_items(self):
        await self.player.enqueue(10, track('a', 'First'))
        await self.player.enqueue(10, track('b', 'Second'))
        await self.player.start(10)
        message = FakeMessage(text='/queue', command=['queue'])
        await queue_plugin.queue_cmd(FakeClient(), message)
        text = message.replies[-1]
        self.assertIn('Currently playing:', text)
        self.assertIn('First', text)
        self.assertIn('Second', text)


class MetaTests(CommandTestCase):
    async def test_start(self):
        message = FakeMessage(text='/start', command=['start'])
        await start.start_cmd(FakeClient(), message)
        self.assertIn('MikasaMusic', message.replies[-1])

    async def test_help(self):
        message = FakeMessage(text='/help', command=['help'])
        await start.help_cmd(FakeClient(), message)
        self.assertIn('Click the buttons below', message.replies[-1])

    async def test_start_group_text(self):
        message = FakeMessage(text='/start', command=['start'])
        await start.start_cmd(FakeClient(), message)
        self.assertIn('MikasaMusic', message.replies[-1])
        self.assertEqual(message.photos, [])

    async def test_start_private_sends_text_without_image(self):
        message = FakeMessage(
            text='/start', command=['start'], chat_type=enums.ChatType.PRIVATE
        )
        await start.start_cmd(FakeClient(), message)
        self.assertEqual(message.photos, [])
        self.assertIn('Tester', message.replies[-1])

    async def test_start_private_sends_photo_with_image(self):
        ctx.settings = SimpleNamespace(
            owner_id=999,
            default_language='en',
            start_image='https://example.com/start.jpg',
        )
        message = FakeMessage(
            text='/start', command=['start'], chat_type=enums.ChatType.PRIVATE
        )
        await start.start_cmd(FakeClient(), message)
        self.assertEqual(len(message.photos), 1)
        self.assertEqual(message.photos[0]['photo'], 'https://example.com/start.jpg')
        self.assertIn('Tester', message.photos[0]['caption'])
        self.assertIsNotNone(message.photos[0]['markup'])


class ResolveItemTests(CommandTestCase):
    async def test_youtube_fallback_track(self):
        self.search.tracks = []
        item = await play._resolve_item('https://youtu.be/dQw4w9WgXcQ', None, FakeMessage(chat_id=1))
        self.assertIsInstance(item, Track)
        self.assertEqual(item.video_id, 'dQw4w9WgXcQ')

    async def test_query_no_results_raises(self):
        self.search.tracks = []
        with self.assertRaises(DownloadError):
            await play._resolve_item('nothing', None, FakeMessage(chat_id=1))

    async def test_reply_uses_downloader(self):
        reply = SimpleNamespace()
        item = await play._resolve_item('', reply, FakeMessage(chat_id=10))
        self.assertIsInstance(item, Media)
        self.assertEqual(item.file_id, 'tg1')


class FakeAssistantClient:
    def __init__(self):
        self.joined = []

    async def join_chat(self, invite):
        self.joined.append(invite)
        return True


class FakeAssistants:
    def __init__(self, states):
        self._states = list(states)

    def ready(self):
        return list(self._states)


class FakeBot:
    def __init__(self, member_status=None, invite="https://t.me/+abc", error=None):
        self._member_status = member_status
        self._invite = invite
        self._error = error

    async def get_chat_member(self, chat_id, user_id):
        if self._error is not None:
            raise self._error
        return SimpleNamespace(status=self._member_status)

    async def export_chat_invite_link(self, chat_id):
        return self._invite


class NoActiveCallTests(CommandTestCase):
    async def test_play_without_voice_chat_shows_call_error(self):
        from pytgcalls.exceptions import NoActiveGroupCall

        async def boom(chat_id, file_path, is_video=False):
            raise NoActiveGroupCall()

        old_play = self.backend.play
        self.backend.play = boom
        try:
            self.search.tracks = [track("a", "First")]
            message = FakeMessage(text="/play one", command=["play", "one"])
            await play.play(FakeClient(), message)
            sent = message.sent_messages[-1]
            self.assertEqual(
                [edit["text"] for edit in sent.text_edits],
                ["No Active Voice Chat Found.\n\nPlease Start Voice Chat In Your Group / Channel And Try Again."],
            )
            self.assertIsNone(self.pool.claimed_slot(10))
        finally:
            self.backend.play = old_play


class AliasTests(unittest.TestCase):
    def test_aliases_registered(self):
        registered = sorted(
            cmd
            for module in (skip_plugin, stop_plugin, queue_plugin)
            for _, cmd in module.HANDLERS
        )
        for alias in ("end", "next", "playing"):
            self.assertIn(alias, registered)


class PauseStateTests(CommandTestCase):
    async def test_pause_twice_reports_already_paused(self):
        await self.player.enqueue(10, track())
        await self.player.start(10)
        first = FakeMessage(text="/pause", command=["pause"])
        await pause_plugin.pause(FakeClient(admin=True), first)
        self.assertEqual(
            first.replies, ["<b><blockquote>Stream paused by</b> Tester</blockquote>"]
        )
        second = FakeMessage(text="/pause", command=["pause"])
        await pause_plugin.pause(FakeClient(admin=True), second)
        self.assertEqual(
            second.replies, ["Do you remember that you resumed the stream?"]
        )

    async def test_resume_without_pause_reports_not_paused(self):
        await self.player.enqueue(10, track())
        await self.player.start(10)
        message = FakeMessage(text="/resume", command=["resume"])
        await resume_plugin.resume(FakeClient(admin=True), message)
        self.assertEqual(
            message.replies, ["Do you remember that you paused the stream?"]
        )

    async def test_pause_state_clears_on_skip_and_stop(self):
        await self.player.enqueue(10, track("a", "First"))
        await self.player.enqueue(10, track("b", "Second"))
        await self.player.start(10)
        await self.player.pause(10)
        self.assertTrue(self.player.is_paused(10))
        await self.player.skip(10)
        self.assertFalse(self.player.is_paused(10))
        await self.player.pause(10)
        self.assertTrue(self.player.is_paused(10))
        await self.player.stop(10)
        self.assertFalse(self.player.is_paused(10))


class PlayMessageTests(CommandTestCase):
    async def test_added_to_queue_shows_position(self):
        self.search.tracks = [track("a", "First")]
        first = FakeMessage(text="/play one", command=["play", "one"])
        await play.play(FakeClient(), first)
        first_sent = first.sent_messages[-1]
        self.assertEqual(
            [edit["text"] for edit in first_sent.text_edits],
            ['<blockquote>Started Streaming |</blockquote>\n'
             '<blockquote>Title : <a href=https://www.youtube.com/watch?v=a>First</a>\n'
             'Duration : 0:10 Minutes\n'
             'Requested By : Tester</blockquote>'],
        )
        self.search.tracks = [track("b", "Second")]
        second = FakeMessage(text="/play two", command=["play", "two"])
        await play.play(FakeClient(), second)
        second_sent = second.sent_messages[-1]
        self.assertEqual(
            [edit["text"] for edit in second_sent.text_edits],
            ['<blockquote>Added To Queue At #1</blockquote>\n\n'
             '<blockquote>Title : <a href=https://www.youtube.com/watch?v=b>Second</a>\n'
             'Duration : 0:10 Minutes\n'
             'Requested By : Tester</blockquote>'],
        )

    async def test_duration_limit_rejects_long_track(self):
        ctx.settings = SimpleNamespace(
            owner_id=999, default_language="en", duration_limit=60
        )
        long_track = Track(
            video_id="long1",
            title="Long",
            duration_seconds=3600,
            url="https://youtu.be/long1long1a",
        )
        self.search.tracks = [long_track]
        message = FakeMessage(text="/play long", command=["play", "long"])
        await play.play(FakeClient(), message)
        sent = message.sent_messages[-1]
        self.assertEqual(
            [edit["text"] for edit in sent.text_edits],
            ["Streams longer than 1 minutes are not allowed to play."],
        )
        self.assertIsNone(await self.player.current(10))


class EnsureAssistantTests(CommandTestCase):
    def setUp(self):
        super().setUp()
        self._old_assistants = ctx.assistants
        self._old_bot = ctx.bot
        self.addCleanup(self._restore_ctx)

    def _restore_ctx(self):
        ctx.assistants = self._old_assistants
        ctx.bot = self._old_bot

    async def test_skips_assistant_already_in_chat(self):
        client = FakeAssistantClient()
        ctx.assistants = FakeAssistants([SimpleNamespace(client=client, user_id=777)])
        ctx.bot = FakeBot(member_status=enums.ChatMemberStatus.MEMBER)
        await play._ensure_assistant(10)
        self.assertEqual(client.joined, [])

    async def test_invites_left_assistant(self):
        client = FakeAssistantClient()
        ctx.assistants = FakeAssistants([SimpleNamespace(client=client, user_id=777)])
        ctx.bot = FakeBot(member_status=enums.ChatMemberStatus.LEFT)
        await play._ensure_assistant(10)
        self.assertEqual(client.joined, ["https://t.me/+abc"])

    async def test_invites_when_not_participant(self):
        from pyrogram.errors import UserNotParticipant

        client = FakeAssistantClient()
        ctx.assistants = FakeAssistants([SimpleNamespace(client=client, user_id=777)])
        ctx.bot = FakeBot(error=UserNotParticipant("not here"))
        await play._ensure_assistant(10)
        self.assertEqual(client.joined, ["https://t.me/+abc"])

    async def test_noop_when_bot_lacks_api(self):
        client = FakeAssistantClient()
        ctx.assistants = FakeAssistants([SimpleNamespace(client=client, user_id=777)])
        ctx.bot = SimpleNamespace(download_media=None)
        await play._ensure_assistant(10)
        self.assertEqual(client.joined, [])


class StubThumbs:
    def __init__(self, card="/tmp/card.png"):
        self.card = card
        self.calls = []

    async def generate(self, item, channel="", duration=""):
        self.calls.append(item)
        return self.card


class PhotoAnnounceTests(CommandTestCase):
    def setUp(self):
        super().setUp()
        self._had_thumbs = hasattr(ctx, "thumbs")
        self._old_thumbs = getattr(ctx, "thumbs", None)
        self.thumbs = StubThumbs()
        ctx.thumbs = self.thumbs
        self.addCleanup(self._restore_thumbs)

    def _restore_thumbs(self):
        if self._had_thumbs:
            ctx.thumbs = self._old_thumbs
        else:
            try:
                del ctx.thumbs
            except AttributeError:
                pass

    async def test_play_search_sends_wait_first(self):
        self.search.tracks = [track("a", "First")]
        message = FakeMessage(text="/play one", command=["play", "one"])
        await play.play(FakeClient(), message)
        self.assertIn("hold on", message.replies[0].lower())

    async def test_play_edits_wait_into_photo_card(self):
        self.search.tracks = [track("a", "First")]
        message = FakeMessage(text="/play one", command=["play", "one"])
        await play.play(FakeClient(), message)
        sent = message.sent_messages[-1]
        self.assertEqual(len(sent.media_edits), 1)
        edit = sent.media_edits[0]
        self.assertEqual(edit["media"].media, "/tmp/card.png")
        self.assertIn("First", edit["media"].caption)
        self.assertIsNotNone(edit["markup"])
        self.assertEqual(message.photos, [])

    async def test_play_falls_back_to_text_without_thumbs(self):
        ctx.thumbs = None
        self.search.tracks = [track("a", "First")]
        message = FakeMessage(text="/play one", command=["play", "one"])
        await play.play(FakeClient(), message)
        sent = message.sent_messages[-1]
        self.assertEqual(sent.media_edits, [])
        self.assertIn("First", sent.text_edits[-1]["text"])

    async def test_callback_handlers_registered(self):
        from mikasa.plugins import callbacks as callbacks_plugin

        class App:
            def __init__(self):
                self.handlers = []

            def add_handler(self, handler, group=0):
                self.handlers.append(handler)
                return (handler, group)

        app = App()
        callbacks_plugin.register(app)
        self.assertEqual(len(app.handlers), 3)


class FakeDatabase:
    def __init__(self):
        self.chats = []
        self.users = []
        self.slots = {}
        self.auth = {}
        self.blocked_chats_set = set()
        self.blocked_users_set = set()
        self.logger_status = False
        self.sudo_set = set()
        self.chat_docs = {}

    async def add_sudo(self, user_id):
        self.sudo_set.add(user_id)

    async def remove_sudo(self, user_id):
        self.sudo_set.discard(user_id)

    async def sudo_users(self):
        return set(self.sudo_set)

    async def add_chat(self, chat_id):
        if chat_id not in self.chats:
            self.chats.append(chat_id)

    async def remove_chat(self, chat_id):
        if chat_id in self.chats:
            self.chats.remove(chat_id)

    async def served_chats(self):
        return list(self.chats)

    async def add_user(self, user_id):
        if user_id not in self.users:
            self.users.append(user_id)

    async def remove_user(self, user_id):
        if user_id in self.users:
            self.users.remove(user_id)

    async def served_users(self):
        return list(self.users)

    async def assistant_slot(self, chat_id, slots):
        if chat_id in self.slots and self.slots[chat_id] in slots:
            return self.slots[chat_id]
        slot = slots[0]
        self.slots[chat_id] = slot
        return slot

    async def set_assistant_slot(self, chat_id, slot):
        self.slots[chat_id] = slot

    async def add_auth(self, chat_id, user_id):
        self.auth.setdefault(chat_id, set()).add(user_id)

    async def remove_auth(self, chat_id, user_id):
        self.auth.get(chat_id, set()).discard(user_id)

    async def is_auth(self, chat_id, user_id):
        return user_id in self.auth.get(chat_id, set())

    async def chat_auth_users(self, chat_id):
        return sorted(self.auth.get(chat_id, set()))

    async def add_blocked_chat(self, chat_id):
        self.blocked_chats_set.add(chat_id)

    async def remove_blocked_chat(self, chat_id):
        self.blocked_chats_set.discard(chat_id)

    async def blocked_chats(self):
        return set(self.blocked_chats_set)

    async def add_blocked_user(self, user_id):
        self.blocked_users_set.add(user_id)

    async def remove_blocked_user(self, user_id):
        self.blocked_users_set.discard(user_id)

    async def blocked_users(self):
        return set(self.blocked_users_set)

    async def set_logger(self, status):
        self.logger_status = status

    async def logger_enabled(self):
        return self.logger_status

    async def chat_settings(self, chat_id):
        return self.chat_docs.get(chat_id, ChatSettings())

    async def save_chat(self, chat_id, settings):
        self.chat_docs[chat_id] = settings


class PingTests(CommandTestCase):
    async def test_ping_replies_and_edits(self):
        message = FakeMessage(text="/ping", command=["ping"])
        await ping.ping_cmd(FakeClient(), message)
        self.assertEqual(message.replies, ["Pinging… please wait…"])
        sent = message.sent_messages[-1]
        self.assertEqual(len(sent.text_edits), 1)
        self.assertIn("Pong!", sent.text_edits[0]["text"])
        self.assertIn("Uptime:", sent.text_edits[0]["text"])


class StatsTests(CommandTestCase):
    def setUp(self):
        super().setUp()
        self._old_db = getattr(ctx, "database", None)
        self._old_assistants = getattr(ctx, "assistants", None)
        self.database = FakeDatabase()
        ctx.database = self.database
        ctx.assistants = SimpleNamespace(slots=lambda: [1, 2])
        self.addCleanup(self._restore_ctx)

    def _restore_ctx(self):
        ctx.database = self._old_db
        ctx.assistants = self._old_assistants

    async def test_stats_group_member(self):
        await self.database.add_chat(-100)
        await self.database.add_user(7)
        message = FakeMessage(text="/stats", command=["stats"])
        await stats.stats_cmd(FakeClient(), message)
        text = message.replies[-1]
        self.assertIn("stats", text)
        self.assertIn("Assistants:</b> 2", text)
        self.assertIn("Served chats:</b> 1", text)
        self.assertIn("Served users:</b> 1", text)
        self.assertNotIn("Modules:", text)

    async def test_stats_owner_sees_system_section(self):
        message = FakeMessage(text="/stats", command=["stats"], user_id=999)
        await stats.stats_cmd(FakeClient(), message)
        self.assertIn("Modules:", message.replies[-1])

    async def test_stats_private_unsupported(self):
        message = FakeMessage(
            text="/stats", command=["stats"], chat_type=enums.ChatType.PRIVATE
        )
        await stats.stats_cmd(FakeClient(), message)
        self.assertEqual(message.replies, ["That request is not supported."])


class TrackingTests(CommandTestCase):
    def setUp(self):
        super().setUp()
        self._old_db = getattr(ctx, "database", None)
        self._old_bot = ctx.bot
        self.database = FakeDatabase()
        ctx.database = self.database
        self.addCleanup(self._restore_ctx)

    def _restore_ctx(self):
        ctx.database = self._old_db
        ctx.bot = self._old_bot

    async def test_start_in_group_tracks_chat(self):
        message = FakeMessage(text="/start", command=["start"])
        await start.start_cmd(FakeClient(), message)
        self.assertIn("MikasaMusic", message.replies[-1])
        self.assertEqual(self.database.chats, [10])
        self.assertEqual(self.database.users, [])

    async def test_start_in_private_tracks_user(self):
        message = FakeMessage(
            text="/start", command=["start"], chat_type=enums.ChatType.PRIVATE
        )
        await start.start_cmd(FakeClient(), message)
        self.assertEqual(self.database.users, [1])
        self.assertEqual(self.database.chats, [])

    async def test_member_joined_tracks_bot_chat(self):
        ctx.bot = SimpleNamespace(me=SimpleNamespace(id=55))
        message = FakeMessage(text="", command=[])
        message.new_chat_members = [SimpleNamespace(id=42), SimpleNamespace(id=55)]
        await start.member_joined(FakeClient(), message)
        self.assertEqual(self.database.chats, [10])

    async def test_member_joined_ignores_other_users(self):
        ctx.bot = SimpleNamespace(me=SimpleNamespace(id=55))
        message = FakeMessage(text="", command=[])
        message.new_chat_members = [SimpleNamespace(id=42)]
        await start.member_joined(FakeClient(), message)
        self.assertEqual(self.database.chats, [])

    async def test_member_left_removes_chat(self):
        await self.database.add_chat(10)
        ctx.bot = SimpleNamespace(me=SimpleNamespace(id=55))
        message = FakeMessage(text="", command=[])
        message.left_chat_member = SimpleNamespace(id=55)
        await start.member_left(FakeClient(), message)
        self.assertEqual(self.database.chats, [])


class ActiveTests(CommandTestCase):
    async def test_non_owner_denied(self):
        message = FakeMessage(text="/ac", command=["ac"], user_id=5)
        await active.active_cmd(FakeClient(), message)
        self.assertEqual(message.replies, ["You need to be an admin to do that."])

    async def test_empty_reports_no_streams(self):
        message = FakeMessage(text="/ac", command=["ac"], user_id=999)
        await active.active_cmd(FakeClient(), message)
        self.assertEqual(
            message.replies, ["Looks like there aren't any active streams on the bot."]
        )

    async def test_ac_reports_count(self):
        self.search.tracks = [track("a", "First")]
        first = FakeMessage(text="/play one", command=["play", "one"])
        await play.play(FakeClient(), first)
        message = FakeMessage(text="/ac", command=["ac"], user_id=999)
        await active.active_cmd(FakeClient(), message)
        self.assertEqual(message.replies, ["Active streams on the bot: <b>1</b>"])

    async def test_activevc_lists_titles(self):
        self.search.tracks = [track("a", "First")]
        first = FakeMessage(text="/play one", command=["play", "one"])
        await play.play(FakeClient(), first)
        message = FakeMessage(text="/activevc", command=["activevc"], user_id=999)
        await active.active_cmd(FakeClient(), message)
        text = message.replies[-1]
        self.assertIn("List of active streams:", text)
        self.assertIn("First", text)


class DatabaseCase(CommandTestCase):
    def setUp(self):
        super().setUp()
        self._old_db = getattr(ctx, "database", None)
        self.database = FakeDatabase()
        ctx.database = self.database
        self.addCleanup(self._restore_db)

    def _restore_db(self):
        ctx.database = self._old_db


class FakeLoopDB(FakeDatabase):
    def __init__(self):
        super().__init__()
        self.settings = {}

    async def chat_settings(self, chat_id):
        return self.settings.get(chat_id, ChatSettings())

    async def save_chat(self, chat_id, settings):
        self.settings[chat_id] = settings


class SeekTests(CommandTestCase):
    async def test_seek_forward_clamps_to_duration(self):
        await self.player.enqueue(10, track("a", "First"))
        await self.player.start(10)
        message = FakeMessage(text="/seek 10", command=["seek", "10"])
        await seek.seek_cmd(FakeClient(admin=True), message)
        sent = message.sent_messages[-1]
        self.assertIn("5 seconds", sent.text_edits[-1]["text"])
        self.assertTrue(self.backend.played)

    async def test_seekback_floors_at_one(self):
        await self.player.enqueue(10, track("a", "First"))
        await self.player.start(10)
        message = FakeMessage(text="/seekback 10", command=["seekback", "10"])
        await seek.seek_cmd(FakeClient(admin=True), message)
        sent = message.sent_messages[-1]
        self.assertIn("1 seconds", sent.text_edits[-1]["text"])

    async def test_seek_usage_and_minimum(self):
        await self.player.enqueue(10, track("a", "First"))
        await self.player.start(10)
        bare = FakeMessage(text="/seek", command=["seek"])
        await seek.seek_cmd(FakeClient(admin=True), bare)
        self.assertIn("Usage:", bare.replies[-1])
        small = FakeMessage(text="/seek 3", command=["seek", "3"])
        await seek.seek_cmd(FakeClient(admin=True), small)
        self.assertIn("10 seconds", small.replies[-1])

    async def test_seek_without_playback(self):
        message = FakeMessage(text="/seek 15", command=["seek", "15"])
        await seek.seek_cmd(FakeClient(admin=True), message)
        self.assertIn("isn't streaming", message.replies[-1])

    async def test_seek_paused_reports_already_paused(self):
        await self.player.enqueue(10, track("a", "First"))
        await self.player.start(10)
        await self.player.pause(10)
        message = FakeMessage(text="/seek 15", command=["seek", "15"])
        await seek.seek_cmd(FakeClient(admin=True), message)
        self.assertIn("resumed the stream", message.replies[-1])

    async def test_seek_without_duration(self):
        item = Track(
            video_id="nodur1",
            title="NoDur",
            duration_seconds=0,
            url="https://youtu.be/nodur1xxxxx",
        )
        await self.player.enqueue(10, item)
        await self.player.start(10)
        message = FakeMessage(text="/seek 15", command=["seek", "15"])
        await seek.seek_cmd(FakeClient(admin=True), message)
        self.assertIn("duration", message.replies[-1])


class LoopTests(DatabaseCase):
    async def test_loop_set_and_report(self):
        await self.player.enqueue(10, track("a", "First"))
        await self.player.start(10)
        setter = FakeMessage(text="/loop 3", command=["loop", "3"])
        await loop.loop_cmd(FakeClient(admin=True), setter)
        self.assertIn("3", setter.replies[-1])
        checker = FakeMessage(text="/loop", command=["loop"])
        await loop.loop_cmd(FakeClient(admin=True), checker)
        self.assertIn("3", checker.replies[-1])
        offer = FakeMessage(text="/loop off", command=["loop", "off"])
        await loop.loop_cmd(FakeClient(admin=True), offer)
        self.assertIn("disabled", offer.replies[-1].lower())

    async def test_loop_rejects_bad_argument(self):
        await self.player.enqueue(10, track("a", "First"))
        await self.player.start(10)
        message = FakeMessage(text="/loop xyz", command=["loop", "xyz"])
        await loop.loop_cmd(FakeClient(admin=True), message)
        self.assertIn("Usage:", message.replies[-1])

    async def test_loop_replays_then_advances(self):
        from mikasa.core.calls import Player
        from mikasa.helpers._queue import Queue

        db = FakeLoopDB()
        player = Player(
            self.pool,
            Queue(limit=5),
            lambda state: self.backend,
            resolver=self._resolve,
            temp_root=self.root,
            database=db,
        )
        await player.enqueue(10, track("a", "First"))
        await player.enqueue(10, track("b", "Second"))
        await player.start(10)
        db.settings[10] = ChatSettings(loop=1)
        self.assertTrue(await player.advance(10))
        self.assertEqual((await player.current(10)).id, "a")
        self.assertEqual(db.settings[10].loop, 0)
        self.assertTrue(await player.advance(10))
        self.assertEqual((await player.current(10)).id, "b")


class AuthTests(DatabaseCase):
    def _admin_client(self):
        return FakeClient(admin_ids={1})

    async def test_auth_add_and_control(self):
        add = FakeMessage(text="/auth 5", command=["auth", "5"])
        await auth.auth_cmd(self._admin_client(), add)
        self.assertIn("authorized users list", add.replies[-1])
        self.assertTrue(await self.database.is_auth(10, 5))
        await self.player.enqueue(10, track("a", "First"))
        await self.player.start(10)
        pauser = FakeMessage(text="/pause", command=["pause"], user_id=5)
        await pause_plugin.pause(FakeClient(admin_ids={1}), pauser)
        self.assertIn("paused by", pauser.replies[-1])

    async def test_auth_rejects_existing_admin(self):
        message = FakeMessage(text="/auth 5", command=["auth", "5"])
        await auth.auth_cmd(FakeClient(admin_ids={1, 5}), message)
        self.assertIn("already an", message.replies[-1])

    async def test_unauth_removes(self):
        await self.database.add_auth(10, 5)
        message = FakeMessage(text="/unauth 5", command=["unauth", "5"])
        await auth.auth_cmd(self._admin_client(), message)
        self.assertIn("Removed", message.replies[-1])
        self.assertFalse(await self.database.is_auth(10, 5))

    async def test_non_admin_cannot_auth(self):
        message = FakeMessage(text="/auth 5", command=["auth", "5"])
        await auth.auth_cmd(FakeClient(admin_ids=set()), message)
        self.assertIn("admin", message.replies[-1])

    async def test_authlist(self):
        empty = FakeMessage(text="/authlist", command=["authlist"])
        await auth.authlist_cmd(FakeClient(admin_ids={1}), empty)
        self.assertIn("empty", empty.replies[-1])
        await self.database.add_auth(10, 5)
        listed = FakeMessage(text="/authlist", command=["authlist"])
        await auth.authlist_cmd(FakeClient(admin_ids={1}), listed)
        self.assertIn("tg://user?id=5", listed.replies[-1])

    async def test_authlist_escapes_chat_title(self):
        await self.database.add_auth(10, 5)
        message = FakeMessage(text="/authlist", command=["authlist"])
        message.chat = SimpleNamespace(id=10, type=enums.ChatType.SUPERGROUP, title="<b>evil</b>")
        await auth.authlist_cmd(FakeClient(admin_ids={1}), message)
        self.assertIn("&lt;b&gt;evil&lt;/b&gt;", message.replies[-1])
        self.assertNotIn("<b>evil</b>", message.replies[-1])


class BlacklistTests(DatabaseCase):
    async def test_add_remove_user(self):
        add = FakeMessage(text="/blacklist 7", command=["blacklist", "7"], user_id=999)
        await blacklist.blacklist_cmd(FakeClient(), add)
        self.assertIn("blacklisted.", add.replies[-1])
        again = FakeMessage(text="/blacklist 7", command=["blacklist", "7"], user_id=999)
        await blacklist.blacklist_cmd(FakeClient(), again)
        self.assertIn("already", again.replies[-1])
        remove = FakeMessage(
            text="/unblacklist 7", command=["unblacklist", "7"], user_id=999
        )
        await blacklist.blacklist_cmd(FakeClient(), remove)
        self.assertIn("removed", remove.replies[-1])

    async def test_add_chat_and_username(self):
        chat = FakeMessage(
            text="/blacklist -1005", command=["blacklist", "-1005"], user_id=999
        )
        await blacklist.blacklist_cmd(FakeClient(), chat)
        self.assertIn(-1005, self.database.blocked_chats_set)
        named = FakeMessage(
            text="/blacklist @some", command=["blacklist", "@some"], user_id=999
        )
        await blacklist.blacklist_cmd(FakeClient(chats={"@some": 321}), named)
        self.assertIn(321, self.database.blocked_users_set)

    async def test_usage_and_invalid(self):
        bare = FakeMessage(text="/blacklist", command=["blacklist"], user_id=999)
        await blacklist.blacklist_cmd(FakeClient(), bare)
        self.assertIn("Usage:", bare.replies[-1])
        bad = FakeMessage(text="/blacklist xyz", command=["blacklist", "xyz"], user_id=999)
        await blacklist.blacklist_cmd(FakeClient(), bad)
        self.assertIn("Only chat IDs", bad.replies[-1])

    async def test_non_owner_denied(self):
        message = FakeMessage(text="/blacklist 7", command=["blacklist", "7"], user_id=5)
        await blacklist.blacklist_cmd(FakeClient(), message)
        self.assertIn("admin", message.replies[-1])

    async def test_blocked_user_cannot_play(self):
        await self.database.add_blocked_user(1)
        self.search.tracks = [track("a", "First")]
        message = FakeMessage(text="/play one", command=["play", "one"])
        await play.play(FakeClient(), message)
        self.assertIn("blacklisted", message.replies[-1])


class SudoTests(DatabaseCase):
    async def test_add_remove_sudo(self):
        add = FakeMessage(text="/addsudo 5", command=["addsudo", "5"], user_id=999)
        await sudo.sudo_cmd(FakeClient(), add)
        self.assertIn("sudo users list", add.replies[-1])
        again = FakeMessage(text="/addsudo 5", command=["addsudo", "5"], user_id=999)
        await sudo.sudo_cmd(FakeClient(), again)
        self.assertIn("already", again.replies[-1])
        remove = FakeMessage(text="/rmsudo 5", command=["rmsudo", "5"], user_id=999)
        await sudo.sudo_cmd(FakeClient(), remove)
        self.assertIn("Removed", remove.replies[-1])

    async def test_sudo_grants_control(self):
        await self.database.add_sudo(5)
        await self.player.enqueue(10, track("a", "First"))
        await self.player.start(10)
        pauser = FakeMessage(text="/pause", command=["pause"], user_id=5)
        await pause_plugin.pause(FakeClient(admin_ids=set()), pauser)
        self.assertIn("paused by", pauser.replies[-1])

    async def test_sudolist(self):
        await self.database.add_sudo(5)
        message = FakeMessage(text="/sudolist", command=["sudolist"])
        await sudo.sudolist_cmd(FakeClient(), message)
        text = message.sent_messages[-1].text_edits[-1]["text"]
        self.assertIn("Owner:", text)
        self.assertIn("tg://user?id=5", text)

    async def test_non_owner_denied(self):
        message = FakeMessage(text="/addsudo 5", command=["addsudo", "5"], user_id=5)
        await sudo.sudo_cmd(FakeClient(), message)
        self.assertIn("admin", message.replies[-1])


class BroadcastTests(DatabaseCase):
    async def test_requires_reply(self):
        message = FakeMessage(text="/broadcast", command=["broadcast"], user_id=999)
        await broadcast.broadcast_cmd(FakeClient(), message)
        self.assertIn("Reply to a message", message.replies[-1])

    async def test_forwards_to_served_chats(self):
        await self.database.add_chat(-100)
        source = FakeMessage(text="hello", command=[])
        message = FakeMessage(
            text="/broadcast", command=["broadcast"], user_id=999, reply=source
        )
        await broadcast.broadcast_cmd(FakeClient(), message)
        self.assertEqual(source.forwarded, [-100])
        self.assertIn("1 groups and 0 users", message.replies[-1])

    async def test_copy_and_user_flags(self):
        await self.database.add_chat(-100)
        await self.database.add_user(9)
        source = FakeMessage(text="hello", command=[])
        message = FakeMessage(
            text="/broadcast",
            command=["broadcast", "-copy", "-user"],
            user_id=999,
            reply=source,
        )
        await broadcast.broadcast_cmd(FakeClient(), message)
        self.assertEqual(source.copied, [-100, 9])
        self.assertIn("1 groups and 1 users", message.replies[-1])

    async def test_non_owner_denied(self):
        source = FakeMessage(text="hello", command=[])
        message = FakeMessage(
            text="/broadcast", command=["broadcast"], user_id=5, reply=source
        )
        await broadcast.broadcast_cmd(FakeClient(), message)
        self.assertIn("admin", message.replies[-1])


class EvalTests(CommandTestCase):
    async def test_eval_expression(self):
        message = FakeMessage(text="/eval 1+1", command=["eval", "1+1"], user_id=999)
        await admin.eval_cmd(FakeClient(), message)
        self.assertIn("2", message.replies[-1])
        self.assertIn("Output", message.replies[-1])

    async def test_eval_empty(self):
        message = FakeMessage(text="/eval", command=["eval"], user_id=999)
        await admin.eval_cmd(FakeClient(), message)
        self.assertIn("What?", message.replies[-1])

    async def test_eval_error(self):
        message = FakeMessage(text="/eval 1/0", command=["eval", "1/0"], user_id=999)
        await admin.eval_cmd(FakeClient(), message)
        self.assertIn("Error executing", message.replies[-1])

    async def test_non_owner_denied(self):
        message = FakeMessage(text="/eval 1+1", command=["eval", "1+1"], user_id=5)
        await admin.eval_cmd(FakeClient(), message)
        self.assertIn("admin", message.replies[-1])


class LogsTests(CommandTestCase):
    async def test_logger_usage_and_toggle(self):
        usage = FakeMessage(text="/logger", command=["logger"], user_id=999)
        await admin.logger_cmd(FakeClient(), usage)
        self.assertIn("Usage:", usage.replies[-1])
        bad = FakeMessage(text="/logger maybe", command=["logger", "maybe"], user_id=999)
        await admin.logger_cmd(FakeClient(), bad)
        self.assertIn("Usage:", bad.replies[-1])

    async def test_logger_requires_database(self):
        message = FakeMessage(text="/logger on", command=["logger", "on"], user_id=999)
        await admin.logger_cmd(FakeClient(), message)
        self.assertIn("Something went wrong", message.replies[-1])

    async def test_logs_missing_file(self):
        old = admin._LOG_PATH
        admin._LOG_PATH = "/nonexistent-xyz-12345.log"
        try:
            message = FakeMessage(text="/logs", command=["logs"], user_id=999)
            await admin.logs_cmd(FakeClient(), message)
            sent = message.sent_messages[-1]
            self.assertIn("doesn't exist", sent.text_edits[-1]["text"])
        finally:
            admin._LOG_PATH = old

    async def test_logs_sends_document(self):
        path = self.root / "test.log"
        path.write_text("hello logs")
        old = admin._LOG_PATH
        admin._LOG_PATH = str(path)
        try:
            message = FakeMessage(text="/logs", command=["logs"], user_id=999)
            await admin.logs_cmd(FakeClient(), message)
            self.assertEqual(len(message.documents), 1)
            self.assertEqual(message.documents[0]["document"], str(path))
        finally:
            admin._LOG_PATH = old

    async def test_non_owner_denied(self):
        message = FakeMessage(text="/logs", command=["logs"], user_id=5)
        await admin.logs_cmd(FakeClient(), message)
        self.assertIn("admin", message.replies[-1])


class RestartTests(CommandTestCase):
    async def test_restart_replaces_process(self):
        calls = []
        old_replace = admin._replace_process
        old_clean = admin._clean_restart_dirs
        admin._replace_process = lambda: calls.append("replace")
        admin._clean_restart_dirs = lambda: calls.append("clean")
        try:
            message = FakeMessage(text="/restart", command=["restart"], user_id=999)
            await admin.restart_cmd(FakeClient(), message)
            self.assertIn("Restarting", message.replies[0])
            self.assertIn("Restart in progress", message.sent_messages[-1].text_edits[-1]["text"])
            self.assertIn("replace", calls)
            self.assertIn("clean", calls)
        finally:
            admin._replace_process = old_replace
            admin._clean_restart_dirs = old_clean

    async def test_non_owner_denied(self):
        message = FakeMessage(text="/restart", command=["restart"], user_id=5)
        await admin.restart_cmd(FakeClient(), message)
        self.assertIn("admin", message.replies[-1])

    async def test_restart_stops_everything_first(self):
        stopped = []

        class FakeService:
            def __init__(self, name):
                self._name = name

            async def close(self):
                stopped.append(("close", self._name))

            async def stop(self):
                stopped.append(("stop", self._name))

            async def exit(self):
                stopped.append(("exit", self._name))

        old = {
            name: getattr(ctx, name, None)
            for name in ("controller", "assistants", "bot", "database")
        }
        ctx.controller = FakeService("player")
        ctx.assistants = FakeService("assistants")
        ctx.bot = FakeService("bot")
        ctx.database = FakeService("database")
        calls = []
        old_replace = admin._replace_process
        old_clean = admin._clean_restart_dirs
        admin._replace_process = lambda: calls.append("replace")
        admin._clean_restart_dirs = lambda: calls.append("clean")
        try:
            message = FakeMessage(text="/restart", command=["restart"], user_id=999)
            await admin.restart_cmd(FakeClient(), message)
            self.assertIn("replace", calls)
            kinds = [kind for kind, _ in stopped]
            self.assertIn("close", kinds)
            self.assertIn("stop", kinds)
            self.assertIn("exit", kinds)
        finally:
            for name, value in old.items():
                setattr(ctx, name, value)
            admin._replace_process = old_replace
            admin._clean_restart_dirs = old_clean


class ReloadTests(CommandTestCase):
    def setUp(self):
        super().setUp()
        from mikasa.helpers import _admins as guard

        guard.clear_admin_cache()
        self._old_rel_hist = dict(auth._rel_hist)
        auth._rel_hist.clear()
        self.addCleanup(self._restore_reload_state)

    def _restore_reload_state(self):
        from mikasa.helpers import _admins as guard

        guard.clear_admin_cache()
        auth._rel_hist.clear()
        auth._rel_hist.update(self._old_rel_hist)

    async def test_reload_refreshes_cache(self):
        from mikasa.helpers import _admins as guard

        members = [SimpleNamespace(user=SimpleNamespace(id=7, is_bot=False))]
        message = FakeMessage(text="/reload", command=["reload"], user_id=50, chat_id=99)
        await auth.reload_cmd(FakeClient(members=members), message)
        sent = message.sent_messages[-1]
        self.assertIn("refreshed", sent.text_edits[-1]["text"])
        self.assertIn(7, guard._admin_cache.get(99, set()))

    async def test_reload_cooldown(self):
        members = [SimpleNamespace(user=SimpleNamespace(id=7, is_bot=False))]
        first = FakeMessage(text="/reload", command=["reload"], user_id=50, chat_id=99)
        await auth.reload_cmd(FakeClient(members=members), first)
        second = FakeMessage(text="/reload", command=["reload"], user_id=50, chat_id=99)
        await auth.reload_cmd(FakeClient(members=members), second)
        self.assertIn("10 minutes", second.replies[-1])

    async def test_reload_prunes_expired_entries(self):
        auth._rel_hist[60] = 1.0
        members = [SimpleNamespace(user=SimpleNamespace(id=7, is_bot=False))]
        message = FakeMessage(text="/reload", command=["reload"], user_id=51, chat_id=99)
        await auth.reload_cmd(FakeClient(members=members), message)
        self.assertNotIn(60, auth._rel_hist)
        self.assertIn(51, auth._rel_hist)


class VideoForceTests(CommandTestCase):
    async def test_vplay_marks_video(self):
        self.search.tracks = [track("a", "First")]
        message = FakeMessage(text="/vplay one", command=["vplay", "one"])
        await play.vplay(FakeClient(), message)
        self.assertTrue(self.backend.played)
        self.assertTrue(self.backend.played[-1][2])

    async def test_force_replaces_current(self):
        self.search.tracks = [track("a", "First")]
        first = FakeMessage(text="/play one", command=["play", "one"])
        await play.play(FakeClient(), first)
        self.assertEqual((await self.player.current(10)).id, "a")
        self.search.tracks = [track("b", "Second")]
        forced = FakeMessage(text="/play -f two", command=["play", "-f", "two"])
        await play.play(FakeClient(), forced)
        self.assertEqual((await self.player.current(10)).id, "b")
        self.assertEqual(await self.player._queue.size(10), 0)


class FakeSelectQuery:
    def __init__(self, data, message, user_id=1):
        self.data = data
        self.message = message
        self.from_user = SimpleNamespace(id=user_id, first_name="Tester")
        self.answers = []

    async def answer(self, text="", show_alert=False):
        self.answers.append((text, show_alert))


def search_track(video_id, title):
    return Track(
        video_id=video_id,
        title=title,
        duration_seconds=10,
        url=f"https://www.youtube.com/watch?v={video_id}",
    )


class SearchTests(CommandTestCase):
    async def test_search_lists_five_truncated_buttons(self):
        self.search.tracks = [
            search_track(f"id{i:02d}abcdefg", f"Song number {i} with a very long title indeed")
            for i in range(6)
        ]
        message = FakeMessage(text="/search songs", command=["search", "songs"])
        await search_plugin.search_cmd(FakeClient(), message)
        sent = message.sent_messages[-1]
        self.assertEqual(len(sent.text_edits), 1)
        edit = sent.text_edits[0]
        self.assertIn("Search results", edit["text"])
        rows = edit["markup"].inline_keyboard
        self.assertEqual(len(rows), 6)
        first = rows[0][0]
        self.assertEqual(first.callback_data, "mikasa:select:id00abcdefg")
        self.assertLessEqual(len(first.text), 35)
        self.assertTrue(first.text.endswith("…"))
        self.assertEqual(rows[-1][0].callback_data, "mikasa:close:10")

    async def test_search_no_results(self):
        self.search.tracks = []
        message = FakeMessage(text="/search nothing", command=["search", "nothing"])
        await search_plugin.search_cmd(FakeClient(), message)
        sent = message.sent_messages[-1]
        self.assertIn("Failed to process", sent.text_edits[-1]["text"])

    async def test_search_no_query_shows_usage(self):
        message = FakeMessage(text="/search", command=["search"])
        await search_plugin.search_cmd(FakeClient(), message)
        self.assertIn("Usage:", message.replies[-1])
        sent = message.sent_messages[-1]
        self.assertEqual(sent.text_edits, [])

    async def test_search_private_unsupported(self):
        message = FakeMessage(
            text="/search x", command=["search", "x"], chat_type=enums.ChatType.PRIVATE
        )
        await search_plugin.search_cmd(FakeClient(), message)
        self.assertIn("not supported", message.replies[-1])


class SelectTests(CommandTestCase):
    def setUp(self):
        super().setUp()
        search_plugin._pending.clear()
        self.addCleanup(search_plugin._pending.clear)

    async def _search(self, tracks):
        self.search.tracks = tracks
        message = FakeMessage(text="/search q", command=["search", "q"])
        await search_plugin.search_cmd(FakeClient(), message)
        return message

    async def test_select_plays_when_idle(self):
        command = await self._search([search_track("aaa111bbb22", "Picked Song")])
        sent = command.sent_messages[-1]
        sent.chat = command.chat
        query = FakeSelectQuery("mikasa:select:aaa111bbb22", sent)
        await search_plugin.select_cb(FakeClient(), query)
        self.assertEqual(query.answers, [("", False)])
        current = await self.player.current(10)
        self.assertIsNotNone(current)
        self.assertEqual(current.id, "aaa111bbb22")
        self.assertTrue(any("Picked Song" in e["text"] for e in sent.text_edits))

    async def test_select_queues_when_busy(self):
        self.search.tracks = [track("a", "First")]
        first = FakeMessage(text="/play one", command=["play", "one"])
        await play.play(FakeClient(), first)
        command = await self._search([search_track("bbb222ccc33", "Second Song")])
        sent_msg = command.sent_messages[-1]
        sent_msg.chat = command.chat
        query = FakeSelectQuery("mikasa:select:bbb222ccc33", sent_msg)
        await search_plugin.select_cb(FakeClient(), query)
        self.assertIn("Added To Queue", sent_msg.text_edits[-1]["text"])

    async def test_select_expired(self):
        command = FakeMessage(text="/search q", command=["search", "q"])
        command.chat = SimpleNamespace(id=10, type=enums.ChatType.SUPERGROUP)
        query = FakeSelectQuery("mikasa:select:zzz999yyy88", command)
        await search_plugin.select_cb(FakeClient(), query)
        self.assertEqual(query.answers, [("This button has expired. Please search again.", True)])

    async def test_select_invalid_data_ignored(self):
        command = FakeMessage(text="/search q", command=["search", "q"])
        for data in ("mikasa:select:", "mikasa:select:bad id!", "mikasa:other:aaa111bbb22"):
            query = FakeSelectQuery(data, command)
            await search_plugin.select_cb(FakeClient(), query)
            self.assertEqual(query.answers, [])

    async def test_select_blocked_user_denied(self):
        await self._search([search_track("aaa111bbb22", "Picked Song")])
        self._old_db = getattr(ctx, "database", None)
        ctx.database = self._make_blocked_db()
        try:
            command = FakeMessage(text="/x", command=["x"])
            sent = FakeSentMessage()
            sent.chat = SimpleNamespace(id=10, type=enums.ChatType.SUPERGROUP)
            query = FakeSelectQuery("mikasa:select:aaa111bbb22", sent)
            await search_plugin.select_cb(FakeClient(), query)
            self.assertTrue(query.answers[0][0].startswith("You've been blacklisted"))
            self.assertTrue(query.answers[0][1])
        finally:
            ctx.database = self._old_db

    def _make_blocked_db(self):
        database = FakeDatabase()
        database.blocked_users_set.add(1)
        return database

    async def test_pending_cache_capped(self):
        for chat in range(55):
            search_plugin.remember_search(chat, [search_track("aaa111bbb22", "S")])
        self.assertLessEqual(len(search_plugin._pending), 50)


class RegisterTests(unittest.TestCase):
    def test_load_plugins_registers_all_handlers(self):
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
        self.assertEqual(len(app.handlers), 47)


if __name__ == '__main__':
    unittest.main()
