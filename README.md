# MikasaMusic

A Telegram music bot that plays songs in group voice chats. Search a song, tap a button, and it plays. That's pretty much it.

Built with [Pyrogram](https://github.com/pyrogram/pyrogram) and [PyTgCalls](https://github.com/pytgcalls/pytgcalls).

## How it works

You add the bot to a group, start a voice chat, and use `/play` or `/search`. The bot downloads the audio (through a download API, with yt-dlp as fallback) and an assistant account streams it into the voice chat. One assistant can handle one group at a time — if you add more assistant sessions, each group sticks to its own assistant.

## Features

- Play by song name, YouTube link, direct audio/video URL, or by replying to a file
- `/search` with tap-to-play buttons
- Queue, skip, pause, resume, stop, seek, loop
- Inline control buttons under the now-playing card
- Auth users, blacklist, sudo users, broadcast, stats, thumbnails

## Requirements

- Python 3.10+
- `ffmpeg` installed on the system (must — the bot refuses to start without it)
- `deno` recommended (only used by the last-resort yt-dlp fallback for tricky YouTube videos; the bot still starts without it)
- A MongoDB database (local or Atlas)
- Telegram `API_ID` / `API_HASH` from [my.telegram.org/apps](https://my.telegram.org/apps)
- A bot token from [@BotFather](https://t.me/BotFather)
- At least one user session string (the assistant that joins voice chats)

## Hosting it yourself (VPS, step by step)

```bash
# 1. Clone the repo
git clone https://github.com/Aditya-Sh4rma/mikasamusic.git
cd mikasamusic

# 2. System packages (Debian/Ubuntu)
sudo apt update && sudo apt install -y python3-venv ffmpeg

# 3. Virtual environment + dependencies
python3 -m venv venv
source venv/bin/activate
pip install -U pip
pip install -r requirements.txt

# 4. Config — copy the sample file and fill your own values in
cp sample.env .env
nano .env
```

Fill in at least `API_ID`, `API_HASH`, `BOT_TOKEN`, `MONGO_URL`, `LOGGER_ID`, `OWNER_ID` and `SESSION_1`. Everything else has working defaults — check `sample.env` for what each variable does.

```bash
# 5. Run it (keeps running after you disconnect)
tmux new -s mikasa
venv/bin/python -m mikasa
# detach with Ctrl+B, then D. Reattach later with: tmux attach -t mikasa
```

Or with Docker:

```bash
docker build -t mikasamusic .
docker run -d --env-file .env mikasamusic
```

## Using it in a group

1. Add the bot **and** the assistant account to your group.
2. Start a voice chat in the group (the bot won't create one by itself).
3. Give the assistant permission to join/speak — easiest is making it an admin, otherwise it may fail to join.

## Commands

| Command | What it does |
|---|---|
| `/play <song/url>` (reply works too) | Play a song, or add to queue |
| `/vplay` | Same, but as video |
| `/search <song>` | Show 5 tap-to-play results |
| `/queue`, `/playing` | Show what's playing and queued |
| `/pause`, `/resume` | Pause / resume |
| `/skip`, `/next` | Skip to next |
| `/stop`, `/end` | Stop and leave the voice chat |
| `/seek <sec>`, `/seekback <sec>` | Jump forward/back (min 10s) |
| `/loop <count\|off>` | Replay the current song |
| `/ping` | Latency, uptime, CPU/RAM/disk |
| `/stats` | Bot stats (extra system info for owner) |
| `/ac`, `/activevc` | Active streams (owner) |
| `/auth`, `/unauth`, `/authlist` | Let non-admins control playback (admins) |
| `/reload` | Refresh the admin list |
| `/addsudo`, `/delsudo`, `/sudolist` | Sudo users (owner) |
| `/blacklist`, `/unblacklist` | Block chats/users (owner) |
| `/broadcast` | Broadcast a replied message (owner) |
| `/eval`, `/logs`, `/logger`, `/restart` | Owner tools |

Pause/skip/stop and the buttons under the player card need an admin (or the owner, a sudo user, or an authorized user).

## Project layout

```
config.py            # all settings, loaded from .env
mikasa/__main__.py   # startup: db → bot → assistants → plugins
mikasa/core/         # bot, userbot, calls (voice), mongo, youtube, telegram, lang, dir, cache
mikasa/tools/        # models, queue, utils, thumbs, admins, buttons, users, perms
mikasa/plugins/      # one file per command group, auto-loaded on startup
mikasa/strings/      # bot reply texts (every language lives here)
```

## Credits

- Owner: [@itz_m4rvin](https://t.me/itz_m4rvin)
- Help and updates: [Samurais Support](https://t.me/SamuraisSupport)

## License

This project is open source. Feel free to fork it and run your own instance — just don't push your own `.env` file with real tokens anywhere.
