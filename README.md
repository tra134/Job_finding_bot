# Da Nang Intern & Contest Finder

A personal tool for a Linux laptop. It looks for new software internships and tech contests and posts them to two private Telegram channels (Jobs and Contests). It is silent when nothing is new.

Status: unit tests use fakes. The systemd startup path (reboot and wake) and delivery to real Telegram channels have not been tested yet.

## Setup

Requires Python 3.13 and `systemd --user`.

1. Create the virtualenv and install dependencies (only `requests` and `beautifulsoup4`):

   ```
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```

2. Create a bot: message `@BotFather` on Telegram, send `/newbot`, and keep the token private.
3. Create two private channels (Jobs and Contests) and add the bot to each as an administrator.
4. Find each channel's numeric chat ID (it starts with `-100`).
5. Configure and protect `.env`:

   ```
   cp .env.example .env
   # edit .env: TELEGRAM_BOT_TOKEN, TELEGRAM_JOBS_CHAT_ID, TELEGRAM_CONTESTS_CHAT_ID
   chmod 600 .env
   ```

   `JOB_AREAS` chooses which job locations are posted: any of `danang`, `remote`, `other` (Hanoi, HCMC and other cities), comma-separated, e.g. `JOB_AREAS=danang,remote`. If unset, all three are posted. Jobs in areas that are turned off are not marked as seen, so turning an area on later posts its current listings as new.

   `.env`, `state/` and `output/` are git-ignored. Never paste the token into chat or commit it.

6. Preview without sending anything:

   ```
   .venv/bin/python -m finder --dry-run
   ```

7. Record the current listings as already seen, sending nothing (optional, see below):

   ```
   .venv/bin/python -m finder --seed
   ```

8. Install the user timer (no sudo):

   ```
   scripts/install
   ```

   It refuses to run unless `.env` exists with mode 600 and `.venv` exists. It writes two unit files into `~/.config/systemd/user/` and enables the timer.

## How it runs

- Trigger: the timer fires 1 minute after login/startup and then hourly (`Persistent=true`, so a missed run happens after wake).
- 3-hour guard: if the last successful scan was under 3 hours ago, the run exits. `--force` skips this check.
- Only one run at a time (lock file `state/finder.lock`).
- Network: it waits up to about 5 minutes for api.telegram.org to be reachable. If still down it exits without updating the last-scan time.
- First run per channel: nothing is sent item by item. One summary message is sent, and everything found is recorded as seen. `--seed` does the same recording without sending the summary.
- Later runs: only new items are sent, split into messages under Telegram's size limit. Items are marked seen only after Telegram confirms delivery, so a failed send is retried next time.
- Silent when nothing is new.
- Jobs digest: internships for technical roles, ordered Da Nang, then remote, then Hanoi/HCMC/other cities (at most 10, with a "+N more" line). Each digest ends with one-click search links.
- Contests digest: hackathons and tech contests on the planned topics, in Da Nang or online; global online events are marked with a globe.
- Source health: one warning is sent to the relevant channel when a source is blocked, errors, or is repeatedly empty. It is not repeated until the source recovers and fails again.
- The last-scan time is only updated when the run was complete: no `--sources` or `--channel` filter, each channel had at least one working source, and every send succeeded.

## Command line

```
.venv/bin/python -m finder [options]
```

- `--dry-run`: print results only. No Telegram, no state, no lock, no config needed. Without `--channel` it covers jobs only.
- `--channel jobs|contests`: limit to one channel (real runs and `--seed` do both by default).
- `--sources a,b`: only the named sources.
- `--force`: ignore the 3-hour guard.
- `--seed`: record current items as seen and send nothing.

Exit codes: 0 normal (including "not due", "already running", "network down"), 1 Telegram failure or unreadable state file, 2 missing configuration or unknown source name.

## Sources

Jobs: VietnamWorks, TopCV, ITviec, CareerViet, CareerLink. A TopDev parser exists but is not enabled, because the page it reads is not filtered to internships.

Contests: Devpost and MLH. Kaggle, Luma, Google Developer Groups and YBOX were checked and are not used.

Requests use a fixed User-Agent, honour `robots.txt` and wait at least 2 seconds between requests to a host. A source is dropped for the rest of the run on HTTP 401, 403, 429 or 451 or a CAPTCHA, and the block is never worked around.

## What it never does

- It never requests Facebook, LinkedIn or Indeed. Those appear only as search links for you to click.
- No logins, cookies, proxies, spoofed browsers or CAPTCHA solving.
- It does not store recruiter names or contact details.
- It does not print or log the bot token.

## Disabling and uninstalling

Pause the timer (keeps the files):

```
systemctl --user disable --now danang-intern-finder.timer
```

Remove it completely:

```
scripts/uninstall
```

This stops and disables the timer and service, deletes the two unit files from `~/.config/systemd/user/` and reloads systemd. It does not touch `state/`, `.env` or anything in the project, and is safe to run again.

## Troubleshooting

- Logs: `journalctl --user -u danang-intern-finder.service -e`
- Timer status: `systemctl --user list-timers danang-intern-finder.timer`
- Run once by hand: `.venv/bin/python -m finder --force`
- "Missing configuration" (exit 2): check that `.env` has all three keys filled in. Nothing is marked as sent in that case.
- Install refuses: run `chmod 600 .env` and make sure `.venv` exists.
- Source reported blocked or empty: the site may have blocked the request or changed its layout. Blocks are respected; wait, or update that parser.
- Nothing arrives: confirm the bot is an admin of the channel and the chat ID is correct; try `--dry-run` to see whether anything matches.
- Reset state: delete `state/state.json` (stop the timer first if you like). The next run is treated as a first run and sends the summary again; use `--seed` to re-record silently. If the state file is corrupt the tool stops rather than resetting it silently.
