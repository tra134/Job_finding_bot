import argparse
import sys
from datetime import date

from . import contest_digest, contest_filters, digest, filters
from .http_client import BlockedError, FetchError, HttpClient
from .sources import (careerlink, careerviet, devpost, itviec, mlh, topcv, vietnamworks)

JOB_SOURCES = {
    "vietnamworks": vietnamworks, "topcv": topcv, "itviec": itviec,
    "careerviet": careerviet, "careerlink": careerlink,
}

CONTEST_SOURCES = {"devpost": devpost, "mlh": mlh}
APPROVED_HOSTS = {"mlh.io", "www.mlh.com", "mlh.com", "devpost.com"}


def run_source(name, module, client):
    """Returns (jobs, status, detail). Status: ok | empty | blocked | error."""
    try:
        jobs = module.fetch(client)
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


def main(argv=None):
    p = argparse.ArgumentParser(prog="finder")
    p.add_argument("--dry-run", action="store_true", help="print only; send nothing")
    p.add_argument("--channel", choices=["jobs", "contests"], default="jobs")
    p.add_argument("--sources", help="comma-separated source names")
    args = p.parse_args(argv)

    if not args.dry_run:
        print("Sending is not implemented yet (Milestone 5). Use --dry-run.", file=sys.stderr)
        return 2
    registry = CONTEST_SOURCES if args.channel == "contests" else JOB_SOURCES
    names = list(registry)
    if args.sources:
        names = [s.strip() for s in args.sources.split(",")]
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
    jobs, report = collect_jobs(names, client)
    groups = filters.select(jobs, date.today())
    print(digest.render_jobs(groups))
    print("\nSource report:")
    for n, status, detail in report:
        print(f"  {n}: {status} ({detail})")
    print(f"Raw postings: {len(jobs)}; kept after filters: "
          f"{sum(len(v) for v in groups.values())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
