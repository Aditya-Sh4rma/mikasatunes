import unittest

from mikasa.helpers._inline import (
    HELP_TOPICS,
    control_data,
    help_markup,
    parse_callback,
    player_controls,
    queue_actions,
    start_key,
)


class ControlDataTests(unittest.TestCase):
    def test_roundtrip(self):
        self.assertEqual(control_data("pause", 10), "mikasa:pause:10")

    def test_parse_valid(self):
        action, chat_id = parse_callback("mikasa:skip:-100")
        self.assertEqual((action, chat_id), ("skip", -100))

    def test_parse_invalid(self):
        for data in ("", "pause:10", "other:pause:10", "mikasa:dance:10", "mikasa:pause:xx"):
            action, chat_id = parse_callback(data)
            self.assertIsNone(action)
            self.assertIsNone(chat_id)


class PlayerControlsTests(unittest.TestCase):
    def test_playing_state_shows_pause(self):
        markup = player_controls(10, paused=False)
        first_row = markup.inline_keyboard[0]
        self.assertEqual(first_row[0].text, "Pause")
        self.assertEqual(first_row[0].callback_data, "mikasa:pause:10")
        self.assertEqual(first_row[1].callback_data, "mikasa:skip:10")
        self.assertEqual(first_row[2].callback_data, "mikasa:stop:10")
        self.assertEqual(markup.inline_keyboard[1][0].text, "Close")
        self.assertEqual(markup.inline_keyboard[1][0].callback_data, "mikasa:close:10")

    def test_paused_state_shows_resume(self):
        markup = player_controls(10, paused=True)
        self.assertEqual(markup.inline_keyboard[0][0].text, "Resume")
        self.assertEqual(markup.inline_keyboard[0][0].callback_data, "mikasa:resume:10")

    def test_custom_labels(self):
        labels = {
            "btn_pause": "P",
            "btn_resume": "R",
            "btn_skip": "S",
            "btn_stop": "T",
            "btn_close": "C",
        }
        markup = player_controls(10, labels=labels)
        self.assertEqual(markup.inline_keyboard[0][0].text, "P")
        self.assertEqual(markup.inline_keyboard[1][0].text, "C")


class QueueActionsTests(unittest.TestCase):
    def test_single_row_add_me_and_close(self):
        markup = queue_actions(10, bot_username="SomeBot")
        self.assertEqual(len(markup.inline_keyboard), 1)
        row = markup.inline_keyboard[0]
        self.assertEqual(len(row), 2)
        self.assertIn("SomeBot", row[0].url)
        self.assertEqual(row[1].callback_data, "mikasa:close:10")

    def test_without_username_only_close(self):
        markup = queue_actions(10)
        self.assertEqual(len(markup.inline_keyboard), 1)
        row = markup.inline_keyboard[0]
        self.assertEqual(len(row), 1)
        self.assertEqual(row[0].callback_data, "mikasa:close:10")


class StartKeyTests(unittest.TestCase):
    def test_full_rows(self):
        markup = start_key(
            bot_username="SomeBot",
            owner_username="owner",
            support_chat="https://t.me/support",
            support_channel="https://t.me/channel",
            labels={},
        )
        rows = markup.inline_keyboard
        self.assertEqual(len(rows), 4)
        self.assertIn("SomeBot", rows[0][0].url)
        self.assertEqual(rows[1][0].callback_data, "mikasa:start:help")
        self.assertIn("owner", rows[2][0].url)
        self.assertIn("support", rows[2][1].url)
        self.assertIn("channel", rows[3][0].url)

    def test_minimal_rows(self):
        markup = start_key(labels={})
        rows = markup.inline_keyboard
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0].callback_data, "mikasa:start:help")


class HelpMarkupTests(unittest.TestCase):
    def test_menu_has_nine_topic_buttons(self):
        labels = {f"help_{index}": f"T{index}" for index in range(9)}
        markup = help_markup(labels)
        buttons = [b for row in markup.inline_keyboard for b in row]
        self.assertEqual(len(buttons), 9)
        self.assertEqual(len(HELP_TOPICS), 9)
        for button, topic in zip(buttons, HELP_TOPICS):
            self.assertEqual(button.callback_data, f"mikasa:help:{topic}")

    def test_back_has_back_and_close(self):
        markup = help_markup({"back": "B", "btn_close": "C"}, back=True)
        row = markup.inline_keyboard[0]
        self.assertEqual(row[0].callback_data, "mikasa:help:back")
        self.assertEqual(row[1].callback_data, "mikasa:help:close")

    def test_origin_start_uses_start_data(self):
        markup = help_markup({}, origin="start")
        datas = [
            button.callback_data
            for row in markup.inline_keyboard
            for button in row
        ]
        self.assertIn("mikasa:start:play", datas)
        self.assertIn("mikasa:start:back", datas)
        topic_markup = help_markup({}, back=True, origin="start")
        back_row = topic_markup.inline_keyboard[0]
        self.assertEqual(back_row[0].callback_data, "mikasa:start:help")


if __name__ == "__main__":
    unittest.main()
