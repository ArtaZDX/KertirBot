# Personal Telegram Bot 🤖

A **private** personal-assistant and archive bot for Telegram. It only works for
*your* Telegram account and helps you store, organise, search, and get reminders
about important personal information.

Modules:

| Module | What it does |
|--------|--------------|
| 📁 Documents | Store PDFs/images/Office files by category, search, download |
| 📅 Reminders | Appointments, flights, deadlines, visa/passport/MOT expiry with multiple alerts |
| 📚 Books | A library of books/PDFs/EPUBs with reading status and notes |
| 🧾 Expenses | Log expenses (and receipt photos), totals per month, CSV export |
| ⚖️ Legal Archive | Evidence, a dated timeline, and witness notes for a tribunal/legal case |
| 🎵 Music | A personal archive of audio files you upload |
| 📝 Notes | Quick notes / knowledge base |
| ⚙️ Settings | Backup the whole vault to a zip |

> ⚠️ **Security note.** This bot stores potentially sensitive documents on the
> machine it runs on. The files are **not encrypted** by default. For anything
> truly sensitive, prefer running on a machine only you control, encrypt your
> disk, and/or move to secure cloud storage (see *Version 2 ideas*). Keep your
> `.env` file private and never commit it.

---

## 1. What you need first

1. **Python 3.10 or newer.** Check with `python --version`.
2. **A Telegram bot token.**
   - Open Telegram, search for **@BotFather**, send `/newbot`, follow the steps.
   - It gives you a token like `123456:ABC-...`. Keep it secret.
3. **Your numeric Telegram user ID.**
   - Message **@userinfobot** on Telegram. It replies with your `Id` (a number).
   - This is the ID that the bot will allow. Everyone else is blocked.

---

## 2. Setup (run on your own computer)

Open a terminal **in the `personal_telegram_bot` folder** and run:

### Windows (PowerShell)

```powershell
# 1. Create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Install the dependencies
pip install -r requirements.txt

# 3. Create your .env from the example, then edit it
copy .env.example .env
notepad .env
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env
```

In `.env`, fill in **at least**:

```
TELEGRAM_BOT_TOKEN=...your token from BotFather...
ALLOWED_USER_ID=...your numeric id from @userinfobot...
```

---

## 3. Run it

```bash
python bot.py
```

You should see `Bot starting. Allowed user id: ...`. Now open Telegram, find
your bot, and send `/start`. You'll get the main menu.

To stop the bot, press `Ctrl + C` in the terminal.

The first run automatically creates:

```
data/
  vault.db        <- your SQLite database
  files/          <- uploaded files, one sub-folder per category
  backups/        <- backup zips
```

---

## 4. How to use it (quick tour)

- **Save a document:** send `/save`, then send the file, pick a category, add an
  optional description with `#tags`.
- **Find it again:** `/find passport` or `/category Tax`, then `/getfile <id>`.
- **Set a reminder:** `/remind 2026-08-12 18:30 Flight to Tehran`.
- **Important reminder (multiple alerts):**
  `/remindimportant 2026-09-01 09:00 Tribunal hearing` → you get pinged 1 week,
  1 day, and 2 hours before, plus on time.
- **Expiry reminder:** `/expiry 2027-03-10 Passport expires`.
- **See what's due:** `/today` and `/week`.
- **Log an expense:** `/expense 12.50 Tesco food`. Monthly total: `/total June 2026`.
  Export everything: `/export expenses`.
- **Legal case:** `/legaladd` to file evidence, `/timelineadd 2024-03-15 Requested
  entry card`, `/witness Gerry He saw the incident`, then `/legalfind overtime`.
- **Music:** `/musicadd` then send an audio file. `/playlist calm`.
- **Obsidian:** set `OBSIDIAN_VAULT_PATH` in `.env` to your vault folder. New books
  are then written as Markdown notes automatically; run `/booksync` once to export
  every existing book.
- **Notes:** `/note Remember to renew TV licence #home`.
- **Backup everything:** `/backup` (sends you a zip, also saved in `data/backups`).

Send `/help` any time to see the menu again. Any multi-step flow can be stopped
with `/cancel`.

---

## 5. Testing it works

A quick manual smoke test after `python bot.py`:

1. Send `/start` → you get the menu. (If you get *"not on its allowlist"*, your
   `ALLOWED_USER_ID` is wrong.)
2. `/note Test note #demo` → "Note saved", then `/notes demo` → it shows up.
3. `/save` → send any PDF/photo → pick *Tax* → `/recent` → it's listed →
   `/getfile <id>` → you get the file back.
4. Set a reminder one minute ahead, e.g. if it's 14:00 now:
   `/remind 2026-06-26 14:01 Test ping` → wait ~1 minute → you get a 🔔 message.
5. `/expense 9.99 TestShop` → `/total June 2026` → shows £9.99.
6. `/backup` → you receive a zip.

If something errors, look at the terminal — the bot logs the full error there.

---

## 6. Running it later on a VPS or Raspberry Pi

The bot uses *long polling*, so it needs **no public IP, domain, or open ports** —
it just needs internet access. To keep it running 24/7:

**Option A — screen/tmux (simplest):**
```bash
sudo apt install tmux
tmux new -s bot
cd personal_telegram_bot
source .venv/bin/activate
python bot.py
# detach with Ctrl-b then d ; reattach with: tmux attach -t bot
```

**Option B — systemd service (auto-restart on boot):** create
`/etc/systemd/system/personalbot.service`:

```ini
[Unit]
Description=Personal Telegram Bot
After=network-online.target

[Service]
WorkingDirectory=/home/pi/personal_telegram_bot
ExecStart=/home/pi/personal_telegram_bot/.venv/bin/python bot.py
Restart=always
User=pi

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl enable --now personalbot
sudo systemctl status personalbot      # check it's running
journalctl -u personalbot -f           # watch the logs
```

On a Raspberry Pi this runs comfortably; just make sure the SD card / disk has
room for your files, and run `/backup` regularly (or copy the `data/` folder).

---

## 6b. Connecting the book archive to Obsidian

An Obsidian vault is just a folder of Markdown files, so the bot can write a note
per book straight into it.

1. In `.env`, set `OBSIDIAN_VAULT_PATH` to your vault folder, e.g.
   `OBSIDIAN_VAULT_PATH=C:\Users\You\Documents\MyVault`. Restart the bot.
2. From now on, `/bookadd` also writes `MyVault/Books/<title> (book-<id>).md`.
3. Run `/booksync` once to export every book you already had.
4. `/booknote` (status + notes) refreshes the matching note.

Each note has YAML frontmatter (`title`, `author`, `category`, `status`, `tags`,
`added`, `book_id`) so Obsidian's search, tags, and Dataview queries work. Tags
also appear as `#tags` in the body for the graph view.

This is **one-way** (bot → Obsidian): editing a note in Obsidian does not change
the bot's database. Two-way sync is a possible v2 (the bot would re-read notes and
update SQLite by `book_id`).

## 7. Moving to PostgreSQL later

Everything talks to the database through the small `Database` class in
`database.py` (`execute` / `query` / `query_one`). To switch:

1. `pip install psycopg[binary]`.
2. Reimplement those three methods using a PostgreSQL connection (read from
   `DATABASE_URL`).
3. Change the `?` SQL placeholders to `%s`.

No module code needs to change.

---

## 8. Version 2 ideas

- **Encryption at rest** for stored files (e.g. `cryptography` Fernet), so even
  someone with disk access can't read your documents.
- **Cloud storage backends** (Google Drive / Dropbox / S3): add a new class in
  `services/storage.py` with the same `save`/`delete` methods and swap it in.
- **PostgreSQL** for multi-device / bigger data (see section 7).
- **Full-text search** (SQLite FTS5 or Postgres `tsvector`) for faster, smarter
  search across everything.
- **OCR** on uploaded receipts/letters so their text becomes searchable.
- **Recurring reminders** (every month / year) and snooze buttons.
- **Automatic scheduled backups** to a cloud location.
- **Per-module export** (e.g. zip a whole legal case to share with a solicitor).
- **Inline confirmation everywhere** and undo for deletes.
- **Web dashboard** (read-only) to browse the archive on a bigger screen.

---

## Project structure

```
personal_telegram_bot/
├── bot.py            # entry point + main menu
├── config.py         # loads .env, paths, secrets
├── database.py       # SQLite wrapper + table creation
├── requirements.txt
├── README.md
├── .env.example
├── modules/          # one file per feature
│   ├── documents.py  reminders.py  books.py  expenses.py
│   ├── legal.py      music.py      notes.py  backup.py
└── services/
    ├── storage.py    # file storage (local now, cloud later)
    ├── scheduler.py  # reminder checker on the job queue
    └── security.py   # allowlist + safe filenames
```
