# Da Nang Intern & Contest Finder

A small bot for a Linux laptop that finds new **software internships** and **tech contests / hackathons** and sends them to Telegram, so you don't have to check job sites every day.

## What it does

- **Finds internships.** It checks several public Vietnamese job sites and keeps only technical intern/trainee roles such as developer, QA, data, AI and DevOps. Sales, HR, senior and labour-export posts are dropped.
- **Filters by location.** You choose which areas to receive: Da Nang, remote, and/or other cities (Hanoi, HCMC…).
- **Finds contests.** It collects upcoming hackathons and tech competitions on topics like AI, data, cloud, security and fintech, held online or in Da Nang. Events whose deadline has passed are skipped.
- **Sends only what's new.** It remembers everything it has already sent. Each digest lists only new items, with a title, company, location, salary and link. If nothing is new, it sends nothing.
- **Runs by itself.** A background timer checks about every 3 hours while the laptop is on, and catches up after a reboot or sleep.
- **Warns you once if a site stops working**, for example if the site blocks the bot or its page layout changes.
- **Scrapes politely.** It respects `robots.txt`, waits between requests, and never logs in, uses proxies or gets around blocks.

## Setup

Requires Python 3.13 and `systemd --user`.

1. Install:
   ```bash
   python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
   ```
2. In Telegram, create a bot with `@BotFather` (`/newbot`). Create a private channel and add the bot as an admin with *Post Messages*.
3. Configure:
   ```bash
   cp .env.example .env && chmod 600 .env
   ```
   | Key | Value |
   |---|---|
   | `TELEGRAM_BOT_TOKEN` | token from BotFather. Keep it secret, never commit it. |
   | `TELEGRAM_JOBS_CHAT_ID` | channel ID for jobs (starts with `-100`) |
   | `TELEGRAM_CONTESTS_CHAT_ID` | channel ID for contests (can be the same channel) |
   | `JOB_AREAS` | any of `danang`, `remote`, `other`, comma-separated. Unset = all |
4. Preview (sends nothing): `.venv/bin/python -m finder --dry-run`
5. Start the background timer: `scripts/install`

The first run sends a single summary and remembers everything currently listed. After that you only get new items.

## Usage

```bash
.venv/bin/python -m finder            # normal run
.venv/bin/python -m finder --dry-run  # print results only
.venv/bin/python -m finder --seed     # remember current items without sending
.venv/bin/python -m finder --force    # run even if the last scan was recent
```

Useful commands:

```bash
systemctl --user list-timers danang-intern-finder.timer    # when it runs next
journalctl --user -u danang-intern-finder.service -e       # logs
systemctl --user disable --now danang-intern-finder.timer  # pause
scripts/uninstall                                          # remove the timer (keeps .env and state/)
```

**Nothing arriving?** Check that the bot is a channel admin and the chat ID is correct, then try `--dry-run` to see whether anything matches. To start fresh, delete `state/state.json`.
