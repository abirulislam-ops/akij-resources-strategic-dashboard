"""
Double-click launcher for the ROMI DWH refresh.

Runs refresh.refresh_all(), prints a human-readable summary, and pauses so the
console window stays open. Intended to be bundled into a standalone .exe with
PyInstaller (runs on the office machine, which has DWH + ODBC access).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import refresh


def _pause(msg="Press Enter to close..."):
    try:
        input(msg)
    except (EOFError, OSError):
        pass


def main():
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass

    print("=" * 60)
    print("  AKIJ ROMI  —  Refresh from DWH")
    print("=" * 60)
    print("Pulling revenue / spend / GP-margin for all campaigns...\n")

    try:
        r = refresh.refresh_all(verbose=True)
    except Exception as e:
        print(f"\n[FATAL] Refresh failed: {e}")
        _pause()
        return 1

    print("-" * 60)
    print(f"Total campaigns : {r['total']}")
    print(f"Updated         : {r['updated']}")
    if r.get("errors"):
        print(f"Skipped         : {len(r['errors'])}")
    print("-" * 60)

    if r.get("warnings"):
        print("\nWarnings (please review):")
        for w in r["warnings"]:
            print(f"  [!] {w}")

    if r.get("errors"):
        print("\nErrors:")
        for e in r["errors"]:
            print(f"  [x] {e}")

    print("\nDone.")
    _pause()
    return 0


if __name__ == "__main__":
    sys.exit(main())
