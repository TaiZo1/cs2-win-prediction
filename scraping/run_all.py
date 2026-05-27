"""
Batch runner for HLTV tournament scraper.

Runs the scraper for all tournaments defined in config.py, either
sequentially or in parallel with multiple Chrome instances.

Usage:
    python run_all.py                      # Sequential, all tournaments
    python run_all.py -p 2                 # 2 parallel scrapers
    python run_all.py -p 3 -s             # 3 parallel, skip already done
    python run_all.py --only iem-cologne-2025 pgl-astana-2025
    python run_all.py --list               # Just list tournaments

Parallel mode:
    Each scraper runs as a separate process with its own Chrome instance.
    Output for each tournament is logged to <stats_dir>/<tournament>/_scraper.log
    Recommended: start with -p 2, increase to 3 if no HLTV blocks.
    Going above 3 risks IP bans from HLTV.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from config import TOURNAMENTS, STATS_DIR, RAW_DIR


def is_completed(key):
    """Check if a tournament has already been fully scraped (has metadata.json)."""
    metadata = STATS_DIR / key / "metadata.json"
    if not metadata.exists():
        return False
    # Check if demos directory also exists and has files
    demo_dir = RAW_DIR / key
    if demo_dir.exists() and any(demo_dir.rglob("*.dem")):
        return True
    # Has metadata but no demos - might be partially done
    # Still consider it "completed" for skip purposes since
    # the scraper itself handles resuming partial scrapes
    return True


def run_sequential(keys):
    """Run scrapers one by one, output goes to console."""
    results = {"ok": [], "failed": []}

    for i, key in enumerate(keys, 1):
        print(f"\n{'='*70}")
        print(f"  [{i}/{len(keys)}] {key}")
        print(f"  URL: {TOURNAMENTS[key]}")
        print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*70}\n")

        result = subprocess.run(
            [sys.executable, "tournament_scraper.py", key],
            cwd=str(Path(__file__).parent),
        )

        if result.returncode == 0:
            results["ok"].append(key)
            print(f"\n  [{key}] COMPLETED SUCCESSFULLY")
        else:
            results["failed"].append(key)
            print(f"\n  [{key}] FAILED (exit code {result.returncode})")

    return results


def run_parallel(keys, max_workers):
    """Run multiple scrapers simultaneously, output goes to log files.

    Staggers Chrome launches by 45 seconds to avoid undetected_chromedriver
    patcher conflicts (file lock on chromedriver.exe).
    """
    STAGGER_DELAY = 45  # seconds between launching each worker
    active = {}  # key -> (Popen, log_file_handle, log_path)
    remaining = list(keys)
    results = {"ok": [], "failed": []}
    last_launch = 0  # timestamp of last process launch

    print(f"Starting parallel scraping with {max_workers} workers...")
    print(f"Stagger delay: {STAGGER_DELAY}s between Chrome launches")
    print(f"Logs are saved to: <stats_dir>/<tournament>/_scraper.log\n")

    while remaining or active:
        # Launch new processes up to max_workers (with stagger delay)
        while remaining and len(active) < max_workers:
            # Enforce stagger delay between launches
            elapsed_since_launch = time.time() - last_launch
            if last_launch > 0 and elapsed_since_launch < STAGGER_DELAY:
                wait = STAGGER_DELAY - elapsed_since_launch
                print(f"  Waiting {wait:.0f}s before next Chrome launch...")
                time.sleep(wait)

            key = remaining.pop(0)
            log_path = STATS_DIR / key / "_scraper.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)

            log_handle = open(log_path, "w", encoding="utf-8")
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            proc = subprocess.Popen(
                [sys.executable, "-u", "tournament_scraper.py", key],
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                cwd=str(Path(__file__).parent),
                env=env,
            )
            active[key] = (proc, log_handle, log_path)
            last_launch = time.time()
            now = datetime.now().strftime("%H:%M:%S")
            print(f"  [{now}] STARTED  {key} (PID {proc.pid}) -> {log_path}")

        # Poll active processes for completion
        for key in list(active):
            proc, log_handle, log_path = active[key]
            rc = proc.poll()
            if rc is not None:
                log_handle.close()
                now = datetime.now().strftime("%H:%M:%S")
                if rc == 0:
                    results["ok"].append(key)
                    print(f"  [{now}] DONE     {key}")
                else:
                    results["failed"].append(key)
                    print(f"  [{now}] FAILED   {key} (exit code {rc}) - check {log_path}")
                del active[key]

        # Don't busy-wait
        if active:
            time.sleep(10)

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Batch runner for HLTV tournament scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "-p", "--parallel", type=int, default=1, metavar="N",
        help="Number of parallel scrapers (default: 1 = sequential)"
    )
    parser.add_argument(
        "-s", "--skip-completed", action="store_true",
        help="Skip tournaments that already have metadata.json"
    )
    parser.add_argument(
        "--only", nargs="+", metavar="KEY",
        help="Only scrape these specific tournaments"
    )
    parser.add_argument(
        "--list", action="store_true",
        help="Just list tournaments and exit"
    )
    args = parser.parse_args()

    # Build tournament list
    keys = list(args.only or TOURNAMENTS.keys())

    # Validate keys
    invalid = [k for k in keys if k not in TOURNAMENTS]
    if invalid:
        print(f"ERROR: Unknown tournament(s): {', '.join(invalid)}")
        print(f"Available: {', '.join(TOURNAMENTS.keys())}")
        sys.exit(1)

    if args.list:
        print(f"\nAll tournaments ({len(TOURNAMENTS)}):\n")
        for i, (k, url) in enumerate(TOURNAMENTS.items(), 1):
            completed = is_completed(k)
            status = " [DONE]" if completed else ""
            print(f"  {i:2d}. {k}{status}")
            print(f"      {url}")
        sys.exit(0)

    # Skip completed if requested
    if args.skip_completed:
        before = len(keys)
        keys = [k for k in keys if not is_completed(k)]
        skipped = before - len(keys)
        if skipped:
            print(f"Skipping {skipped} already completed tournament(s)")

    if not keys:
        print("Nothing to scrape! All tournaments are already completed.")
        sys.exit(0)

    # Summary
    print(f"\n{'='*70}")
    print(f"  HLTV Tournament Batch Scraper")
    print(f"  Mode: {'Parallel (' + str(args.parallel) + ' workers)' if args.parallel > 1 else 'Sequential'}")
    print(f"  Tournaments: {len(keys)}")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}")
    for i, k in enumerate(keys, 1):
        print(f"  {i:2d}. {k}")
    print()

    # Run
    start = time.time()
    if args.parallel > 1:
        results = run_parallel(keys, args.parallel)
    else:
        results = run_sequential(keys)

    # Final report
    elapsed = (time.time() - start) / 3600
    print(f"\n{'='*70}")
    print(f"  BATCH COMPLETE")
    print(f"  Total time: {elapsed:.1f} hours")
    print(f"  Completed: {len(results['ok'])}/{len(keys)}")
    if results["failed"]:
        print(f"  Failed: {', '.join(results['failed'])}")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
