"""Unified command line interface for AutoType."""
from __future__ import annotations

import argparse
import os
import sys

from autotype.__version__ import __version__


def run_daemon(debug: bool = False) -> int:
    """Launch the AutoType background daemon."""
    from app import main as daemon_main

    daemon_main(debug=debug)
    return 0


def run_settings() -> int:
    """Launch the AutoType GTK settings GUI."""
    from settings_gui import main as settings_main

    settings_main()
    return 0


def run_download_model(args: argparse.Namespace) -> int:
    """Handle download, removal, and listing of local speech models."""
    from autotype.downloader import (
        ChecksumMismatchError,
        DownloaderError,
        InsufficientDiskSpaceError,
        UnverifiedModelError,
        download_item,
        remove_item,
    )
    from autotype.manifest import (
        format_size,
        get_item,
        get_recommended_items,
        is_item_installed,
        load_manifest,
    )

    if args.list:
        items = load_manifest()
        if not items:
            print("No models found in manifest.", file=sys.stderr)
            return 1

        print("Available speech models & binaries:\n")
        print(f"{'ID':<22} {'TYPE':<12} {'SIZE':<10} {'STATUS':<14} {'NAME'}")
        print("-" * 75)
        for item in items:
            installed = is_item_installed(item)
            if installed:
                status = "installed"
            elif not item.installable:
                status = "unverified"
            else:
                status = "not installed"

            rec_badge = " [recommended]" if item.recommended else ""
            print(
                f"{item.id:<22} {item.type:<12} {format_size(item.size_bytes):<10} "
                f"{status:<14} {item.display_name}{rec_badge}"
            )
        return 0

    def progress_callback(downloaded: int, total: int) -> None:
        if total <= 0:
            sys.stdout.write(f"\r  Progress: {format_size(downloaded)}")
        else:
            pct = min(100.0, max(0.0, (downloaded / total) * 100.0))
            width = 25
            filled = int(width * (downloaded / total))
            filled = min(width, max(0, filled))
            bar = "=" * filled + ("-" * (width - filled))
            sys.stdout.write(
                f"\r  Progress: [{bar}] {pct:5.1f}% ({format_size(downloaded)} / {format_size(total)})"
            )
        sys.stdout.flush()

    if args.install:
        item = get_item(args.install)
        if not item:
            print(f"Error: Unknown model ID '{args.install}'. Run with --list to view available models.", file=sys.stderr)
            return 2

        if not item.installable or not item.verified:
            reason = item.unverified_reason or "model is marked unverified"
            print(f"Error: Model '{item.id}' cannot be installed: {reason}", file=sys.stderr)
            return 2

        print(f"Downloading '{item.display_name}' ({item.id})...")
        try:
            target = download_item(item, progress_callback=progress_callback)
            sys.stdout.write("\n")
            print(f"Successfully installed '{item.id}' to {target}")
            return 0
        except ChecksumMismatchError as err:
            sys.stdout.write("\n")
            print(f"Error: {err}", file=sys.stderr)
            return 3
        except (DownloaderError, InsufficientDiskSpaceError, UnverifiedModelError) as err:
            sys.stdout.write("\n")
            print(f"Error: {err}", file=sys.stderr)
            return 1
        except Exception as err:
            sys.stdout.write("\n")
            print(f"Unexpected error: {err}", file=sys.stderr)
            return 1

    if args.remove:
        item = get_item(args.remove)
        if not item:
            print(f"Error: Unknown model ID '{args.remove}'. Run with --list to view available models.", file=sys.stderr)
            return 2

        if not is_item_installed(item):
            print(f"Model '{item.id}' is not installed.")
            return 0

        success = remove_item(item)
        if success:
            print(f"Successfully removed '{item.id}'.")
            return 0
        else:
            print(f"Failed to remove '{item.id}'.", file=sys.stderr)
            return 1

    if args.all_recommended:
        recommended = get_recommended_items()
        if not recommended:
            print("No recommended models found in manifest.")
            return 0

        print(f"Installing {len(recommended)} recommended item(s)...")
        for idx, item in enumerate(recommended, 1):
            print(f"\n[{idx}/{len(recommended)}] Downloading '{item.display_name}' ({item.id})...")
            try:
                target = download_item(item, progress_callback=progress_callback)
                sys.stdout.write("\n")
                print(f"Successfully installed '{item.id}' to {target}")
            except ChecksumMismatchError as err:
                sys.stdout.write("\n")
                print(f"Error: {err}", file=sys.stderr)
                return 3
            except Exception as err:
                sys.stdout.write("\n")
                print(f"Error downloading '{item.id}': {err}", file=sys.stderr)
                return 1

        print("\nAll recommended items successfully installed.")
        return 0

    print("Usage error: one of --list, --install <id>, --remove <id>, or --all-recommended is required.", file=sys.stderr)
    return 2


def run_doctor(json_output: bool = False) -> int:
    """Run environment and dependency diagnostics."""
    from autotype.doctor import format_report_json, format_report_text, run_checks

    report = run_checks()
    if json_output:
        print(format_report_json(report))
    else:
        print(format_report_text(report))

    return 0 if report.ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autotype",
        description="AutoType: Voice typing daemon for Linux Mint XFCE on X11",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=__version__,
        help="Show program's version number and exit.",
    )

    subparsers = parser.add_subparsers(
        title="subcommands",
        dest="subcommand",
        metavar="<command>",
    )

    # daemon
    daemon_parser = subparsers.add_parser(
        "daemon",
        help="Start the voice-typing background daemon.",
    )
    daemon_parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging output.",
    )

    # settings
    subparsers.add_parser(
        "settings",
        help="Open the GTK settings preferences window.",
    )

    # version
    subparsers.add_parser(
        "version",
        help="Print the current version.",
    )

    # download-model
    download_parser = subparsers.add_parser(
        "download-model",
        help="Download and manage local speech models.",
    )
    download_parser.add_argument(
        "--list",
        action="store_true",
        help="List available models and binaries from manifest.",
    )
    download_parser.add_argument(
        "--install",
        metavar="ID",
        help="Download and install a model or binary by ID.",
    )
    download_parser.add_argument(
        "--remove",
        metavar="ID",
        help="Remove an installed model or binary by ID.",
    )
    download_parser.add_argument(
        "--all-recommended",
        action="store_true",
        help="Download and install all recommended models and binaries.",
    )

    # doctor
    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Run environment and dependency diagnostics.",
    )
    doctor_parser.add_argument(
        "--json",
        action="store_true",
        help="Output diagnostics in JSON format.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    parser = build_parser()

    # If no arguments provided, show help and exit 0
    if not argv:
        parser.print_help()
        return 0

    # Custom handling for subcommands
    args = parser.parse_args(argv)

    if args.subcommand == "daemon":
        return run_daemon(debug=getattr(args, "debug", False))
    elif args.subcommand == "settings":
        return run_settings()
    elif args.subcommand == "version":
        print(__version__)
        return 0
    elif args.subcommand == "download-model":
        return run_download_model(args)
    elif args.subcommand == "doctor":
        return run_doctor(json_output=getattr(args, "json", False))
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
