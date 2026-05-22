import argparse
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Family Photos indexer")
    parser.add_argument(
        "--step",
        choices=["merge", "scan", "google_metadata", "location", "pre_caption", "caption", "embed", "thumb", "all"],
        required=True,
        help="Pipeline step to run",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max photos to process (caption defaults to 50 if unset)",
    )
    parser.add_argument(
        "--reindex",
        action="store_true",
        help="Re-process already-indexed photos",
    )
    parser.add_argument(
        "--folders",
        nargs="+",
        type=Path,
        default=None,
        help="Takeout folders to merge (required for --step merge)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview merge without copying files",
    )
    args = parser.parse_args()

    if args.step == "merge":
        if not args.folders:
            parser.error("--step merge requires --folders")
        from .merge import run_merge
        from .scan import run_scan
        result = run_merge(args.folders, dry_run=args.dry_run)
        if not args.dry_run:
            run_scan(reindex=args.reindex, prehashed=result["items"])

    elif args.step == "scan":
        from .scan import run_scan
        run_scan(reindex=args.reindex)

    elif args.step == "google_metadata":
        from .google_metadata import run_google_metadata
        run_google_metadata(reindex=args.reindex)

    elif args.step == "location":
        from .location import run_location
        run_location(reindex=args.reindex)

    elif args.step == "pre_caption":
        from .scan import run_scan
        from .google_metadata import run_google_metadata
        from .location import run_location
        run_scan(reindex=args.reindex)
        run_google_metadata(reindex=args.reindex)
        run_location(reindex=args.reindex)

    elif args.step == "caption":
        from .caption import run_caption
        run_caption(limit=args.limit or 50, reindex=args.reindex)

    elif args.step == "embed":
        from .embed import run_embed
        run_embed(reindex=args.reindex, limit=args.limit)

    elif args.step == "thumb":
        from .thumb import run_thumb
        run_thumb(reindex=args.reindex, limit=args.limit)

    elif args.step == "all":
        from .scan import run_scan
        from .google_metadata import run_google_metadata
        from .location import run_location
        from .caption import run_caption
        from .embed import run_embed
        run_scan(reindex=args.reindex)
        run_google_metadata(reindex=args.reindex)
        run_location(reindex=args.reindex)
        run_caption(limit=args.limit, reindex=args.reindex)
        run_embed(reindex=args.reindex)
        from .thumb import run_thumb
        run_thumb(reindex=args.reindex)


if __name__ == "__main__":
    main()
