"""Run all source scrapers in parallel."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SCRAPERS = (
    "scripts/scrape_firstpost_articles.py",
    "scripts/scrape_the_hindu_articles.py",
    "scripts/scrape_hindustan_times_articles.py",
    "scripts/scrape_news18_articles.py",
    "scripts/scrape_pib_articles.py",
    "scripts/scrape_ndtv_articles.py",
)
POLL_SECONDS = 0.25
SCRAPER_TIMEOUT_SECONDS = 15 * 60


@dataclass(frozen=True)
class RunningScraper:
    name: str
    script: Path
    process: subprocess.Popen[str]


def main() -> None:
    scrapers = start_scrapers()
    output_threads = [stream_output(scraper) for scraper in scrapers]
    try:
        failures = wait_for_scrapers(scrapers)
    except KeyboardInterrupt:
        stop_scrapers(scrapers)
        raise

    for thread in output_threads:
        thread.join(timeout=2)

    if failures:
        print("\nFailed scrapers:", flush=True)
        for name, return_code in failures:
            print(f"  {name}: exited with {return_code}", flush=True)
        raise SystemExit(1)

    print("\nDone. All scrapers completed.", flush=True)


def start_scrapers() -> list[RunningScraper]:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    scrapers: list[RunningScraper] = []
    for script_name in SCRAPERS:
        script = ROOT_DIR / script_name
        process = subprocess.Popen(
            [sys.executable, "-u", str(script)],
            cwd=ROOT_DIR,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        scraper = RunningScraper(name=script.stem, script=script, process=process)
        scrapers.append(scraper)
        print(f"started {scraper.name} pid={process.pid}", flush=True)

    return scrapers


def stream_output(scraper: RunningScraper) -> threading.Thread:
    thread = threading.Thread(target=print_output, args=(scraper,), daemon=True)
    thread.start()
    return thread


def print_output(scraper: RunningScraper) -> None:
    if scraper.process.stdout is None:
        return

    for line in scraper.process.stdout:
        print(f"[{scraper.name}] {line}", end="", flush=True)


def wait_for_scrapers(scrapers: list[RunningScraper]) -> list[tuple[str, int]]:
    pending = list(scrapers)
    failures: list[tuple[str, int]] = []
    started_at = time.monotonic()

    while pending:
        if time.monotonic() - started_at > SCRAPER_TIMEOUT_SECONDS:
            for scraper in pending:
                scraper.process.kill()
                failures.append((scraper.name, -9))
            return failures

        for scraper in pending[:]:
            return_code = scraper.process.poll()
            if return_code is None:
                continue

            pending.remove(scraper)
            if return_code == 0:
                print(f"finished {scraper.name}", flush=True)
            else:
                failures.append((scraper.name, return_code))

        if pending:
            time.sleep(POLL_SECONDS)

    return failures


def stop_scrapers(scrapers: list[RunningScraper]) -> None:
    for scraper in scrapers:
        if scraper.process.poll() is None:
            scraper.process.terminate()


if __name__ == "__main__":
    main()
