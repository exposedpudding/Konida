import json
import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    machine_label TEXT NOT NULL,
    equipment_number TEXT NOT NULL,
    items TEXT NOT NULL,          -- JSON {code: qty}
    status TEXT NOT NULL,         -- dry-run | submitted | failed
    portal_reference TEXT,
    note TEXT
)
"""


def connect(path: str = "orders.db") -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.execute(SCHEMA)
    return con


def log_order(con, machine, items, status, reference=None, note=None):
    con.execute(
        "INSERT INTO orders (created_at, machine_label, equipment_number, items,"
        " status, portal_reference, note) VALUES (?,?,?,?,?,?,?)",
        (datetime.now(timezone.utc).isoformat(timespec="seconds"), machine.label,
         machine.equipment_number, json.dumps(items), status, reference, note),
    )
    con.commit()


def history(con, equipment_number=None):
    q = "SELECT created_at, machine_label, equipment_number, items, status, portal_reference FROM orders"
    args = ()
    if equipment_number:
        q += " WHERE equipment_number = ?"
        args = (equipment_number,)
    return con.execute(q + " ORDER BY id DESC", args).fetchall()
