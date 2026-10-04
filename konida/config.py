from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Machine:
    label: str
    equipment_number: str
    postcode: str
    toner: dict[str, int] = field(default_factory=dict)


def load_fleet(path: str | Path = "fleet.yaml") -> dict[str, Machine]:
    data = yaml.safe_load(Path(path).read_text())
    fleet = {}
    for label, m in (data.get("machines") or {}).items():
        fleet[label] = Machine(
            label=label,
            equipment_number=str(m["equipment_number"]).strip(),
            postcode=str(m["postcode"]).strip(),
            toner={str(k): int(v) for k, v in (m.get("toner") or {}).items()},
        )
    return fleet


def parse_toner_args(pairs: list[str]) -> dict[str, int]:
    """['TN-328K=2', 'TN-328C=1'] -> {'TN-328K': 2, 'TN-328C': 1}"""
    out = {}
    for p in pairs:
        code, _, qty = p.partition("=")
        if not code or not qty.isdigit() or int(qty) < 1:
            raise SystemExit(f"Bad --toner value {p!r}; use CODE=QTY, e.g. TN-328K=2")
        out[code.strip()] = int(qty)
    return out


def app_dir() -> Path:
    """Folder holding fleet.yaml / orders.db: next to the exe when frozen."""
    import sys
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path.cwd()


def save_machine(path, label, equipment_number, postcode):
    p = Path(path)
    data = yaml.safe_load(p.read_text()) if p.exists() else {}
    data = data or {}
    data.setdefault("machines", {})[label] = {
        "equipment_number": equipment_number, "postcode": postcode, "toner": {}}
    p.write_text(yaml.safe_dump(data, sort_keys=False))


def save_toner_defaults(path, label, toner: dict[str, int]):
    p = Path(path)
    data = yaml.safe_load(p.read_text())
    data["machines"][label]["toner"] = toner
    p.write_text(yaml.safe_dump(data, sort_keys=False))
