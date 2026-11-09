import argparse
import sys
from datetime import date

from . import digest, filters
from .http_client import BlockedError, FetchError, HttpClient
from .sources import (careerlink, careerviet, itviec, topcv, vietnamworks)

JOB_SOURCES = {
    "vietnamworks": vietnamworks, "topcv": topcv, "itviec": itviec,
    "careerviet": careerviet, "careerlink": careerlink,
}


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


def collect_jobs(names, client):
    all_jobs, report = [], []
    for n in names:
        jobs, status, detail = run_source(n, JOB_SOURCES[n], client)
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
    if args.channel == "contests":
        print("Contest sources are not implemented yet (Milestone 4).", file=sys.stderr)
        return 2
    names = list(JOB_SOURCES)
    if args.sources:
        names = [s.strip() for s in args.sources.split(",")]
        bad = [n for n in names if n not in JOB_SOURCES]
        if bad:
            print(f"Unknown source(s): {', '.join(bad)}. Known: {', '.join(JOB_SOURCES)}",
                  file=sys.stderr)
            return 2

    jobs, report = collect_jobs(names, HttpClient())
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
