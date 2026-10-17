# MikasaMusic

A Telegram music bot that plays songs in group voice chats. Search a song, tap a button, and it plays. That's pretty much it.

Built with [Pyrogram](https://github.com/pyrogram/pyrogram) and [PyTgCalls](https://github.com/pytgcalls/pytgcalls).

## How it works

You add the bot to a group, start a voice chat, and use `/play` or `/search`. The bot downloads the audio (through a download API, with yt-dlp as fallback) and an assistant account streams it into the voice chat. One assistant can handle one group at a time — if you add more assistant sessions, each group sticks to its own assistant.

## Features

- Play by song name, YouTube link / playlist, direct audio/video URL, or by replying to a file
- YouTube playlists auto-expand (first song plays, rest queue up)
- `/search` with tap-to-play buttons
- Queue with `/remove` and `/shuffle`, skip, pause, resume, stop, seek/seekback, loop, force-play (`-f`, `/playforce`), video mode (`/vplay`, `-v`)
- Autoplay: keeps playing related songs when the queue ends, with same-song protection
- Live progress bar on the player card, updated every few seconds
- Per-group settings with `/settings`: play mode (admins only or everyone) and language (English + Burmese so far)
- Inline control buttons under the now-playing card
- Sticky multi-assistant pool (up to 5 assistants, each group sticks to its own)
- Persistent download cache, thumbnail cards
- Auth users, blacklist, sudo users, broadcast, stats

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
git clone https://github.com/Aditya-Sh4rma/mikasatunes.git
cd mikasatunes

# 2. System packages (Debian/Ubuntu) — ffmpeg is a must, deno is needed
#    for the YouTube fallback, so install both together
sudo apt update && sudo apt install -y python3-venv ffmpeg curl unzip
curl -fsSL https://deno.land/install.sh | sh

# 2b. Put deno on PATH (the installer drops it in ~/.deno/bin,
#    which new shells don't know about — without this the bot
#    won't find it when started from tmux/systemd/cron)
echo 'export DENO_INSTALL="$HOME/.deno"' >> ~/.bashrc
echo 'export PATH="$DENO_INSTALL/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
deno --version   # should print a version, not "command not found"

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
docker build -t mikasatunes .
docker run -d --env-file .env mikasatunes
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
| `/playforce`, `/vplayforce` (or `-f` flag) | Stop current and play right now |
| `/search <song>` | Show 5 tap-to-play results |
| `/queue`, `/playing` | Show what's playing and queued |
| `/remove <position>` | Remove the queued track at that position (admins) |
| `/shuffle` | Shuffle the waiting queue (admins) |
| `/pause`, `/resume` | Pause / resume |
| `/skip`, `/next` | Skip to next |
| `/stop`, `/end` | Stop and leave the voice chat |
| `/seek <sec>`, `/seekback <sec>` | Jump forward/back (min 10s) |
| `/loop <count\|off>` | Replay the current song |
| `/autoplay <on\|off>` | Keep playing related songs when the queue ends |
| `/lang`, `/language` | Group language (English, Burmese) |
| `/settings`, `/playmode` | Group settings: play mode and language (admins) |
| `/ping`, `/alive` | Latency, uptime, CPU/RAM/disk |
| `/stats` | Bot stats (extra system info for owner) |
| `/ac`, `/activevc` | Active streams (owner) |
| `/auth`, `/unauth`, `/authlist` | Let non-admins control playback (admins) |
| `/reload`, `/admincache` | Refresh the admin list |
| `/addsudo`, `/delsudo`, `/rmsudo`, `/sudolist`, `/listsudo` | Sudo users (owner) |
| `/blacklist`, `/unblacklist`, `/whitelist` | Block/unblock chats/users (owner) |
| `/broadcast` | Broadcast a replied message (owner) |
| `/eval`, `/logs`, `/logger`, `/restart` | Owner tools |

Pause/skip/stop, `/remove`, `/shuffle` and the buttons under the player card need an admin (or the owner, a sudo user, or an authorized user).

## Project layout

```
config.py            # all settings, loaded from .env
mikasa/__main__.py   # thin entrypoint, calls boot()
mikasa/boot.py       # startup: db → bot → assistants → plugins
mikasa/core/         # bot, userbot, calls (voice), db, youtube, telegram, lang, dir, watch
mikasa/tools/        # models, queue, utils, thumbs, admins, buttons, users, perms
mikasa/plugins/      # one file per command group, auto-loaded on startup
strings/             # bot reply texts (every language lives here)
```

## Credits

- Owner: [@itz_m4rvin](https://t.me/itz_m4rvin)
- Help and updates: [Samurais Support](https://t.me/SamuraisSupport)
- Inspired by [AnonXMusic](https://github.com/AnonymousX1025/AnonXMusic) by AnonymousX1025 (MIT) — the assistant pool, auth/trusted-user idea and inline player controls follow its design. All code here is written fresh for this project.

## License

MIT — see [LICENSE](LICENSE). Feel free to fork it and run your own instance — just don't push your own `.env` file with real tokens anywhere.
