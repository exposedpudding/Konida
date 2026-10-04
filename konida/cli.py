import argparse

from . import db
from .config import load_fleet, parse_toner_args
from .portal import PortalError, place_order


def main(argv=None):
    ap = argparse.ArgumentParser(prog="konida", description="Order Konica Minolta toner as a guest, logged per machine.")
    ap.add_argument("--fleet", default="fleet.yaml")
    sub = ap.add_subparsers(dest="cmd", required=True)

    o = sub.add_parser("order", help="Order toner for one machine")
    o.add_argument("machine", help="label from fleet.yaml")
    o.add_argument("--toner", nargs="+", metavar="CODE=QTY", help="override the machine's default toner order")
    o.add_argument("--confirm", action="store_true", help="actually submit (default is dry run)")
    o.add_argument("--discover", action="store_true", help="save HTML/screenshots to ./discovery to tune selectors")

    sub.add_parser("list", help="List machines in the fleet")
    h = sub.add_parser("history", help="Show logged orders")
    h.add_argument("machine", nargs="?")

    a = ap.parse_args(argv)
    fleet = load_fleet(a.fleet)
    con = db.connect()

    if a.cmd == "list":
        for m in fleet.values():
            print(f"{m.label:25} {m.equipment_number:15} {m.toner}")
        return
    if a.cmd == "history":
        eq = fleet[a.machine].equipment_number if a.machine else None
        for row in db.history(con, eq):
            print(" | ".join(str(c) for c in row))
        return

    if a.machine not in fleet:
        raise SystemExit(f"Unknown machine {a.machine!r}. Known: {', '.join(fleet)}")
    m = fleet[a.machine]
    items = parse_toner_args(a.toner) if a.toner else m.toner
    if not items:
        raise SystemExit("No toner specified (use --toner CODE=QTY or set defaults in fleet.yaml).")
    print(f"{m.label} ({m.equipment_number}): {items}  [{'LIVE' if a.confirm else 'dry run'}]")
    try:
        status, ref = place_order(m, items, confirm=a.confirm, discover=a.discover)
    except PortalError as e:
        db.log_order(con, m, items, "failed", note=str(e))
        raise SystemExit(f"FAILED: {e}")
    db.log_order(con, m, items, status, reference=ref)
    print(f"{status}" + (f" ref={ref}" if ref else ""))


if __name__ == "__main__":
    main()
