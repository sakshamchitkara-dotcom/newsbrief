"""Command line entry point: `newsbrief run|schedule|unsubscribe|check`."""
from __future__ import annotations

import argparse
import logging
import sys
import time

from .config import ConfigError, load_config
from .deliver import DeliveryError
from .pipeline import run
from .state import State
from .unsubscribe import verify_token

log = logging.getLogger("newsbrief")


def _run_once(args, cfg) -> int:
    try:
        outs = run(cfg, dry_run=args.dry_run, only_due=args.only_due, subscriber=args.subscriber,
                   fetch_text=False if args.no_fetch_text else None)
    except DeliveryError as e:
        log.error("%s", e)
        return 2
    for o in outs:
        where = f" -> {o.paths[1]}" if o.paths else ""
        print(f"{o.subscriber}: {o.stories} stories via {o.transport}{where}")
    return 0


def cmd_run(args) -> int:
    return _run_once(args, load_config(args.config))


def cmd_schedule(args) -> int:
    """Loop forever, delivering to each subscriber once their local send time passes."""
    args.only_due = True
    log.info("scheduler started; checking every %ss", args.interval)
    while True:
        try:
            _run_once(args, load_config(args.config))  # reload so config edits apply without restart
        except Exception:  # noqa: BLE001 - one bad tick must not kill the daemon
            log.exception("scheduled run failed")
        time.sleep(args.interval)


def cmd_unsubscribe(args) -> int:
    cfg = load_config(args.config)
    if not verify_token(args.email, args.token):
        print("invalid token", file=sys.stderr)
        return 1
    st = State(cfg.state_db)
    st.unsubscribe(args.email)
    st.close()
    print(f"unsubscribed {args.email}")
    return 0


def cmd_check(args) -> int:
    cfg = load_config(args.config)
    print(f"{len(cfg.sources)} sources, {len(cfg.subscribers)} subscribers")
    for s in cfg.subscribers:
        names = ", ".join(x.name for x in cfg.sources_for(s)) or "(none!)"
        print(f"  {s.email} at {s.send_at} {s.timezone}: {names}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="newsbrief", description=__doc__)
    p.add_argument("-c", "--config", default="newsbrief.yaml")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    def delivery_flags(sp):
        sp.add_argument("--dry-run", action="store_true", help="write .eml/.html to the outbox instead of sending")
        sp.add_argument("--subscriber", help="only this subscriber email")
        sp.add_argument("--no-fetch-text", action="store_true", help="use feed blurbs, skip fetching article pages")

    r = sub.add_parser("run", help="build and deliver briefs once")
    delivery_flags(r)
    r.add_argument("--only-due", action="store_true", help="skip subscribers whose send time hasn't come")
    r.set_defaults(func=cmd_run)

    s = sub.add_parser("schedule", help="run forever, sending at each subscriber's local time")
    delivery_flags(s)
    s.add_argument("--interval", type=int, default=300, help="seconds between checks")
    s.set_defaults(func=cmd_schedule)

    u = sub.add_parser("unsubscribe", help="unsubscribe an email given its token")
    u.add_argument("email")
    u.add_argument("token")
    u.set_defaults(func=cmd_unsubscribe)

    c = sub.add_parser("check", help="validate config and show who gets what")
    c.set_defaults(func=cmd_check)

    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        return args.func(args)
    except (ConfigError, FileNotFoundError) as e:
        print(f"config error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
