"""Command line: analyse one track, or backfill every track that hasn't been analysed.

    audio-worker analyze <track-id>
    audio-worker backfill [--limit 50]
"""

from __future__ import annotations

import argparse
import logging
import sys

from .config import load_settings
from .pipeline import RejectedTrack, analyze_track
from .store import SupabaseStore


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(prog="audio-worker")
    sub = parser.add_subparsers(dest="cmd", required=True)
    one = sub.add_parser("analyze", help="analyse one track")
    one.add_argument("track_id")
    many = sub.add_parser("backfill", help="analyse tracks that have no analysis yet")
    many.add_argument("--limit", type=int, default=50)
    args = parser.parse_args(argv)

    settings = load_settings()
    store = SupabaseStore(settings)
    ids = [args.track_id] if args.cmd == "analyze" else store.track_ids_without_analysis(args.limit)

    failed = 0
    for i, track_id in enumerate(ids, 1):
        try:
            r = analyze_track(track_id, store, settings)
            print(f"[{i}/{len(ids)}] {track_id}: {r.duration_sec:.0f}s, "
                  f"{r.loudness_lufs} LUFS, {len(r.duplicates)} duplicate(s), {r.elapsed_sec}s")
        except RejectedTrack as e:
            print(f"[{i}/{len(ids)}] {track_id}: skipped ({e})")
        except Exception as e:  # keep going; the failure is recorded on the row
            failed += 1
            print(f"[{i}/{len(ids)}] {track_id}: FAILED ({e})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
