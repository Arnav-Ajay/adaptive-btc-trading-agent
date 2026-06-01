"""Manual runner for building or sending the weekly HTML report on demand."""

from __future__ import annotations

import argparse
import sys

from app.config.settings import load_config
from app.monitoring.alerts import NotificationManager


def main(argv: list[str] | None = None) -> int:
    """Build the weekly report for preview or send it immediately."""
    parser = argparse.ArgumentParser(description="Adaptive BTC Trading Agent weekly report runner")
    parser.add_argument("--send", action="store_true", help="Send the weekly report via Gmail SMTP")
    args = parser.parse_args(argv)

    config = load_config()
    notifications = NotificationManager(config)
    report = notifications.build_weekly_report()
    if args.send:
        return 0 if notifications.gmail.send_weekly_report(report.subject, report.html) else 1

    sys.stdout.write(report.subject + "\n\n")
    sys.stdout.write(report.html)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
