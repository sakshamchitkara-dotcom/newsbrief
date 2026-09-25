"""Command line entry point: `newsbrief run|schedule|subscribers|unsubscribe|serve|check|eval|archive`."""
from __future__ import annotations

import argparse
import logging
import sys
import time

from .config import ConfigError, load_config, load_raw, save_subscribers
from .deliver import DeliveryError
from .pipeline import run
from .state import State
from .unsubscribe import verify_token

log = logging.getLogger("newsbrief")


def _run_once(args, cfg, dry_run_log=None) -> int:
    try:
        outs = run(cfg, dry_run=args.dry_run, only_due=args.only_due, subscriber=args.subscriber,
                   fetch_text=False if args.no_fetch_text else None, dry_run_log=dry_run_log)
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
    dry_run_log: set[tuple[str, str]] = set()
    while True:
        try:
            _run_once(args, load_config(args.config), dry_run_log)  # reload so config edits apply without restart
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


def cmd_serve(args) -> int:
    from .server import serve
    from .unsubscribe import require_secret

    require_secret()
    cfg = load_config(args.config)
    print(f"unsubscribe endpoint on http://{args.host}:{args.port}/unsubscribe")
    serve(cfg.state_db, args.host, args.port)
    return 0


def cmd_check(args) -> int:
    cfg = load_config(args.config)
    print(f"{len(cfg.sources)} sources, {len(cfg.subscribers)} subscribers")
    for s in cfg.subscribers:
        names = ", ".join(x.name for x in cfg.sources_for(s)) or "(none!)"
        print(f"  {s.email} at {s.send_at} {s.timezone}: {names}")
    if not args.feeds:
        return 0
    from .health import check_feeds, report

    table, ok = report(check_feeds(list(cfg.sources.values()), probe_text=cfg.fetch_articles and args.probe > 0,
                                   probes=args.probe),
                       stale_hours=args.stale_hours)
    print()
    print(table)
    return 0 if ok else 3


def _csv(v: str | None) -> list[str]:
    return [x.strip() for x in (v or "").split(",") if x.strip()]


def cmd_subscribers(args) -> int:
    raw = load_raw(args.config)
    subs = list(raw.get("subscribers") or [])
    idx = {str(s.get("email", "")).lower(): i for i, s in enumerate(subs)}
    if args.action == "list":
        cfg = load_config(args.config)
        st = State(cfg.state_db)
        try:
            for s in cfg.subscribers:
                flags = [f"topics={','.join(s.topics)}" if s.topics else "", f"sources={','.join(s.sources)}" if s.sources else "",
                         "UNSUBSCRIBED" if st.is_unsubscribed(s.email) else ""]
                print(f"{s.email:<32} {s.send_at} {s.timezone:<20} {s.name:<12} {' '.join(f for f in flags if f)}".rstrip())
        finally:
            st.close()
        print(f"{len(cfg.subscribers)} subscribers")
        return 0
    key = args.email.lower()
    if args.action == "remove":
        if key not in idx:
            print(f"no subscriber {args.email}", file=sys.stderr)
            return 1
        del subs[idx[key]]
        save_subscribers(args.config, subs)
        print(f"removed {args.email}")
        return 0
    if key in idx:
        print(f"{args.email} is already subscribed", file=sys.stderr)
        return 1
    new = {"email": args.email, "name": args.name, "timezone": args.timezone, "send_at": args.send_at,
           "topics": _csv(args.topics), "sources": _csv(args.sources)}
    save_subscribers(args.config, subs + [{k: v for k, v in new.items() if v}])  # validates tz, HH:MM, topics
    print(f"added {args.email}: {args.send_at} {args.timezone}")
    return 0


def cmd_archive(args) -> int:
    from .archive import build_site

    cfg = load_config(args.config)
    st = State(cfg.state_db)
    try:
        paths = build_site(st, args.out, subscriber=args.subscriber, title=args.title)
    finally:
        st.close()
    print(f"wrote {len(paths) - 1} day pages + index to {paths[0]}")
    return 0


def cmd_eval(args) -> int:
    from .evaluate import DEFAULT_SET, evaluate, load_set

    r = evaluate(load_set(args.set or DEFAULT_SET))
    print(f"{r.items} items, {r.gold_pairs} labeled same-story pairs, {r.predicted_pairs} predicted")
    print(f"precision {r.precision:.3f}  recall {r.recall:.3f}  f1 {r.f1:.3f}")
    for label, pairs in (("false merge", r.false_merges), ("missed", r.misses)):
        for a, b in pairs[: args.show]:
            print(f"  {label}: [{a.source}] {a.title}\n{' ' * (len(label) + 4)}[{b.source}] {b.title}")
        if len(pairs) > args.show:
            print(f"  ... {len(pairs) - args.show} more {label} pairs (--show N)")
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

    sm = sub.add_parser("subscribers", help="list, add or remove subscribers in the config file")
    sma = sm.add_subparsers(dest="action", required=True)
    sma.add_parser("list", help="show subscribers and their schedule")
    add = sma.add_parser("add", help="add a subscriber (validates timezone and send time)")
    add.add_argument("email")
    add.add_argument("--name", default="")
    add.add_argument("--timezone", "--tz", default="UTC", help="IANA zone, e.g. Europe/London")
    add.add_argument("--send-at", default="07:00", help="local HH:MM")
    add.add_argument("--topics", help="comma-separated topic filter")
    add.add_argument("--sources", help="comma-separated source filter")
    rm = sma.add_parser("remove", help="remove a subscriber")
    rm.add_argument("email")
    sm.set_defaults(func=cmd_subscribers)

    u = sub.add_parser("unsubscribe", help="unsubscribe an email given its token")
    u.add_argument("email")
    u.add_argument("token")
    u.set_defaults(func=cmd_unsubscribe)

    v = sub.add_parser("serve", help="serve the /unsubscribe endpoint")
    v.add_argument("--host", default="127.0.0.1")
    v.add_argument("--port", type=int, default=8025)
    v.set_defaults(func=cmd_serve)

    c = sub.add_parser("check", help="validate config and show who gets what; --feeds for feed health")
    c.add_argument("--feeds", action="store_true", help="fetch every source and report freshness and failures")
    c.add_argument("--stale-hours", type=float, default=24, help="flag feeds whose newest item is older (default 24)")
    c.add_argument("--probe", type=int, default=3, metavar="N",
                   help="article pages to fetch per feed to test access (default 3, 0 to skip)")
    c.set_defaults(func=cmd_check)

    a = sub.add_parser("archive", help="build a static HTML archive of past briefs (e.g. for GitHub Pages)")
    a.add_argument("--out", default="site", help="output directory (default: site)")
    a.add_argument("--subscriber", help="only this subscriber's briefs (default: the fullest brief each day)")
    a.add_argument("--title", default="The Daily Brief archive")
    a.set_defaults(func=cmd_archive)

    e = sub.add_parser("eval", help="score story clustering against a labeled set")
    e.add_argument("--set", help="labeled JSON set (default: the bundled 2026-09-25 feed snapshot)")
    e.add_argument("--show", type=int, default=10, help="list up to N false merges and misses each")
    e.set_defaults(func=cmd_eval)

    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        return args.func(args)
    except (ConfigError, FileNotFoundError) as e:
        print(f"config error: {e}", file=sys.stderr)
        return 1
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
