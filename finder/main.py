import argparse
import socket
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

from . import contest_digest, contest_filters, digest, filters, state as st, telegram
from .http_client import BlockedError, FetchError, HttpClient, RobotsDisallowed
from .sources import careerviet, devpost, itviec, luma, mlh, topcv, vietnamworks

JOB_SOURCES = {
    "vietnamworks": vietnamworks, "topcv": topcv, "itviec": itviec,
    "careerviet": careerviet,   # CareerLink removed: it serves a CAPTCHA to bots
}

CONTEST_SOURCES = {"luma": luma, "devpost": devpost, "mlh": mlh}
APPROVED_HOSTS = {"mlh.io", "www.mlh.com", "mlh.com", "devpost.com"}

ROOT = Path(__file__).resolve().parent.parent
CHAT_KEYS = {"jobs": "TELEGRAM_JOBS_CHAT_ID", "contests": "TELEGRAM_CONTESTS_CHAT_ID"}
NETWORK_WAIT, NETWORK_STEP = 300, 15


def run_source(name, module, client):
    """Returns (jobs, status, detail). Status: ok | empty | blocked | skipped | error."""
    try:
        jobs = module.fetch(client)
    except RobotsDisallowed as e:
        return [], "skipped", str(e)
    except BlockedError as e:
        return [], "blocked", str(e)
    except FetchError as e:
        return [], "error", str(e)
    except Exception as e:  # parser bug: report, do not crash other sources
        return [], "error", f"{type(e).__name__}: {e}"
    return jobs, ("ok" if jobs else "empty"), f"{len(jobs)} raw postings"


def collect_jobs(names, client, registry=None):
    registry = registry or JOB_SOURCES
    all_jobs, report = [], []
    for n in names:
        jobs, status, detail = run_source(n, registry[n], client)
        all_jobs += jobs
        report.append((n, status, detail))
    return all_jobs, report


def load_env(path):
    out = {}
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        out[k.strip()] = v
    return out


def telegram_reachable():
    try:
        socket.create_connection(("api.telegram.org", 443), timeout=5).close()
        return True
    except OSError:
        return False


def boot_time():
    """When this machine last booted (UTC), from /proc/stat; None if unavailable."""
    try:
        for line in Path("/proc/stat").read_text().splitlines():
            if line.startswith("btime "):
                return datetime.fromtimestamp(int(line.split()[1]), timezone.utc)
    except (OSError, ValueError):
        pass
    return None


def slept_seconds():
    """Total seconds suspended since boot (BOOTTIME counts sleep, MONOTONIC does not).
    It grows each time the laptop sleeps, so a larger value means it woke up since."""
    try:
        return time.clock_gettime(time.CLOCK_BOOTTIME) - time.clock_gettime(time.CLOCK_MONOTONIC)
    except (AttributeError, OSError):
        return None


def wait_for_network(check, sleep, total=NETWORK_WAIT, step=NETWORK_STEP):
    waited = 0
    while not check():
        if waited >= total:
            return False
        sleep(step)
        waited += step
    return True


def _job_groups(items, today, tiers):
    """filters.select, keeping only the location tiers chosen by JOB_AREAS."""
    groups = filters.select(items, today)
    return {t: groups[t] for t in (1, 2, 3) if t in tiers}


def _kept(channel, items, today, tiers):
    """Returns (kept list, groups-or-None)."""
    if channel == "jobs":
        groups = _job_groups(items, today, tiers)
        return [j for t in groups for j in groups[t]], groups
    return contest_filters.select(items, today), None


def run_channel(channel, names, client, state, sender, chat_id, today, seed, tiers=(1, 2, 3)):
    """Returns (has_data, send_ok)."""
    registry = JOB_SOURCES if channel == "jobs" else CONTEST_SOURCES
    items, report = collect_jobs(names, client, registry)
    kept, groups = _kept(channel, items, today, tiers)
    send_ok = True
    has_data = any(s in ("ok", "empty") for _, s, _ in report)
    if seed:
        state.mark_seen(channel, [st.item_key(i) for i in kept])
        state.mark_initialized(channel)
    elif not state.is_initialized(channel):
        try:
            sender.send(chat_id, telegram.first_run_summary(channel, len(kept)))
            state.mark_seen(channel, [st.item_key(i) for i in kept])
            state.mark_initialized(channel)
        except telegram.TelegramError as e:
            print(f"[{channel}] Telegram send failed: {e}", file=sys.stderr)
            send_ok = False
    else:
        new = [i for i in kept if not state.is_seen(channel, st.item_key(i))]
        if new:
            if channel == "jobs":
                ids = {id(i) for i in new}
                blocks = telegram.render_jobs(
                    {t: [j for j in groups[t] if id(j) in ids] for t in groups}, st.item_key)
            else:
                blocks = telegram.render_contests(new, st.item_key)
            try:
                telegram.send_digest(sender, chat_id, telegram.split_blocks(blocks),
                                     lambda keys: state.mark_seen(channel, keys))
            except telegram.TelegramError as e:
                print(f"[{channel}] Telegram send failed: {e}", file=sys.stderr)
                send_ok = False
    for n, status, detail in report:
        warn = state.update_source(n, status)
        if seed or not warn:
            continue
        try:
            sender.send(chat_id, telegram.source_warning(n, status, detail))
            state.mark_warned(n)
        except telegram.TelegramError as e:
            print(f"[{channel}] Telegram send failed: {e}", file=sys.stderr)
            send_ok = False
    return has_data, send_ok


def real_run(args, root, sender_factory, sleep, net_check, now, client_factory, booted_at,
             slept=slept_seconds):
    channels = [args.channel] if args.channel else ["jobs", "contests"]
    chat_ids, sender = {}, None
    env = load_env(root / ".env")
    try:
        tiers = filters.parse_areas(env.get("JOB_AREAS"))
    except ValueError as e:
        print(f"{e}. Nothing was sent.", file=sys.stderr)
        return 2
    if not args.seed:
        need = ["TELEGRAM_BOT_TOKEN"] + [CHAT_KEYS[c] for c in channels]
        missing = [k for k in need if not env.get(k)]
        if missing:
            print(f"Missing configuration in .env: {', '.join(missing)}. Nothing was sent.",
                  file=sys.stderr)
            return 2
        chat_ids = {c: env[CHAT_KEYS[c]] for c in channels}
        sender = sender_factory(env["TELEGRAM_BOT_TOKEN"])
    try:
        with st.RunLock(root / "state" / "finder.lock"):
            state = st.State(root / "state" / "state.json")
            if not (args.force or args.seed) and not state.scan_due(now(), 3, booted_at(),
                                                                     slept()):
                print("Already scanned since boot/wake and under 3 hours ago; "
                      "skipping (use --force).")
                return 0
            if not wait_for_network(net_check, sleep):
                print("Network unavailable; giving up without updating the last scan.")
                return 0
            client = client_factory()
            today, rc = date.today(), 0
            complete = not args.sources and not args.channel
            for c in channels:
                registry = JOB_SOURCES if c == "jobs" else CONTEST_SOURCES
                names = [n for n in (args.names or registry) if n in registry]
                if not names:
                    continue
                has_data, send_ok = run_channel(c, names, client, state, sender,
                                                chat_ids.get(c), today, args.seed, tiers)
                complete = complete and has_data and send_ok
                if not send_ok:
                    rc = 1
            if complete and rc == 0:
                state.record_scan(now(), slept())
            return rc
    except st.LockHeld:
        print("Another run is in progress; exiting.")
        return 0
    except st.StateError as e:
        print(f"State file problem: {e}", file=sys.stderr)
        return 1


def main(argv=None, *, root=None, sender_factory=telegram.TelegramSender, sleep=time.sleep,
         net_check=telegram_reachable, now=lambda: datetime.now(timezone.utc),
         client_factory=lambda: HttpClient(approved_hosts=APPROVED_HOSTS),
         booted_at=boot_time, slept=slept_seconds):
    p = argparse.ArgumentParser(prog="finder")
    p.add_argument("--dry-run", action="store_true", help="print only; send nothing")
    p.add_argument("--channel", choices=["jobs", "contests"], default=None)
    p.add_argument("--sources", help="comma-separated source names")
    p.add_argument("--force", action="store_true", help="ignore the 3-hour guard")
    p.add_argument("--seed", action="store_true", help="mark everything seen; send nothing")
    args = p.parse_args(argv)
    args.names = None
    if args.sources:
        args.names = [s.strip() for s in args.sources.split(",")]
    if args.names and not args.dry_run:
        known = {**JOB_SOURCES, **CONTEST_SOURCES}
        bad = [n for n in args.names if n not in known]
        if bad:
            print(f"Unknown source(s): {', '.join(bad)}. Known: {', '.join(known)}",
                  file=sys.stderr)
            return 2

    if not args.dry_run:
        return real_run(args, Path(root or ROOT), sender_factory, sleep, net_check, now,
                        client_factory, booted_at, slept)
    args.channel = args.channel or "jobs"
    registry = CONTEST_SOURCES if args.channel == "contests" else JOB_SOURCES
    names = args.names or list(registry)
    bad = [n for n in names if n not in registry]
    if bad:
        print(f"Unknown source(s): {', '.join(bad)}. Known: {', '.join(registry)}",
              file=sys.stderr)
        return 2

    client = HttpClient(approved_hosts=APPROVED_HOSTS)
    if args.channel == "contests":
        items, report = collect_jobs(names, client, registry)
        chosen = contest_filters.select(items, date.today())
        print(contest_digest.render_contests(chosen))
        print("\nSource report:")
        for n, status, detail in report:
            print(f"  {n}: {status} ({detail})")
        print(f"Raw events: {len(items)}; kept after filters: {len(chosen)}")
        return 0
    try:
        tiers = filters.parse_areas(load_env(Path(root or ROOT) / ".env").get("JOB_AREAS"))
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2
    jobs, report = collect_jobs(names, client)
    groups = _job_groups(jobs, date.today(), tiers)
    print(digest.render_jobs(groups))
    print("\nSource report:")
    for n, status, detail in report:
        print(f"  {n}: {status} ({detail})")
    print(f"Raw postings: {len(jobs)}; kept after filters: "
          f"{sum(len(v) for v in groups.values())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
