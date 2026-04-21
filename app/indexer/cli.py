import argparse
import sys


def main():
    parser = argparse.ArgumentParser(description="Family Photos indexer")
    parser.add_argument(
        "--step",
        choices=["scan", "google_metadata", "location", "caption", "embed", "all"],
        required=True,
        help="Pipeline step to run",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Max photos to caption (default: 50)",
    )
    parser.add_argument(
        "--reindex",
        action="store_true",
        help="Re-process already-indexed photos",
    )
    args = parser.parse_args()

    if args.step == "scan":
        from .scan import run_scan
        run_scan(reindex=args.reindex)

    elif args.step == "google_metadata":
        from .google_metadata import run_google_metadata
        run_google_metadata(reindex=args.reindex)

    elif args.step == "location":
        from .location import run_location
        run_location(reindex=args.reindex)

    elif args.step == "caption":
        from .caption import run_caption
        run_caption(limit=args.limit, reindex=args.reindex)

    elif args.step == "embed":
        from .embed import run_embed
        run_embed(reindex=args.reindex)

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


if __name__ == "__main__":
    main()
