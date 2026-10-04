import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from . import db
from .config import (app_dir, load_fleet, save_machine, save_toner_defaults)
from .portal import PortalError, place_order

ROWS = 6


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Konida - Konica Minolta toner orders")
        self.geometry("760x640")
        os.chdir(app_dir())
        self.fleet_path = app_dir() / "fleet.yaml"
        self.q = queue.Queue()
        self.busy = False

        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")
        ttk.Label(top, text="Machine:").pack(side="left")
        self.machine = ttk.Combobox(top, state="readonly", width=32)
        self.machine.pack(side="left", padx=6)
        self.machine.bind("<<ComboboxSelected>>", lambda e: self.fill_toner())
        ttk.Button(top, text="Add machine", command=self.add_machine).pack(side="left")
        ttk.Button(top, text="Order history", command=self.show_history).pack(side="left", padx=6)

        self.info = ttk.Label(self, padding=(10, 0))
        self.info.pack(anchor="w")

        grid = ttk.LabelFrame(self, text="Toner (product code on the portal, quantity)", padding=10)
        grid.pack(fill="x", padx=10, pady=8)
        self.codes, self.qtys = [], []
        for i in range(ROWS):
            c, q = tk.StringVar(), tk.StringVar()
            ttk.Entry(grid, textvariable=c, width=28).grid(row=i, column=0, padx=4, pady=2)
            ttk.Spinbox(grid, from_=0, to=99, textvariable=q, width=5).grid(row=i, column=1, padx=4)
            self.codes.append(c); self.qtys.append(q)
        ttk.Button(grid, text="Save as this machine's default", command=self.save_defaults).grid(
            row=0, column=2, padx=12)

        opts = ttk.Frame(self, padding=(10, 0))
        opts.pack(fill="x")
        self.live = tk.BooleanVar(value=False)
        self.discover = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts, text="Place the order for real (untick = dry run, stops at checkout)",
                        variable=self.live).pack(anchor="w")
        ttk.Checkbutton(opts, text="Save page snapshots to 'discovery' folder (for fixing selectors)",
                        variable=self.discover).pack(anchor="w")
        self.btn = ttk.Button(opts, text="Run order", command=self.run)
        self.btn.pack(anchor="w", pady=8)

        self.log = tk.Text(self, height=14, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.reload()
        self.after(150, self.pump)

    # -- data
    def reload(self, select=None):
        if not self.fleet_path.exists():
            self.fleet_path.write_text("machines: {}\n")
        self.fleet = load_fleet(self.fleet_path)
        self.machine["values"] = list(self.fleet)
        if self.fleet:
            self.machine.set(select if select in self.fleet else list(self.fleet)[0])
        else:
            self.machine.set("")
        self.fill_toner()

    def cur(self):
        return self.fleet.get(self.machine.get())

    def fill_toner(self):
        m = self.cur()
        self.info.config(text=f"Equipment no: {m.equipment_number}   Postcode: {m.postcode}" if m else
                         "No machines yet - click 'Add machine'.")
        items = list((m.toner if m else {}).items())
        for i in range(ROWS):
            code, qty = items[i] if i < len(items) else ("", "")
            self.codes[i].set(code); self.qtys[i].set(qty)

    def items(self):
        out = {}
        for c, q in zip(self.codes, self.qtys):
            code, qty = c.get().strip(), q.get().strip()
            if code and qty.isdigit() and int(qty) > 0:
                out[code] = int(qty)
        return out

    # -- actions
    def add_machine(self):
        label = simpledialog.askstring("Add machine", "Label (e.g. Reception C360i):", parent=self)
        if not label: return
        eq = simpledialog.askstring("Add machine", "Equipment / serial number:", parent=self)
        if not eq: return
        pc = simpledialog.askstring("Add machine", "Postcode (as registered with Konica Minolta):", parent=self)
        if not pc: return
        save_machine(self.fleet_path, label.strip(), eq.strip(), pc.strip())
        self.reload(select=label.strip())

    def save_defaults(self):
        if self.cur():
            save_toner_defaults(self.fleet_path, self.machine.get(), self.items())
            self.say("Saved defaults.")
            self.reload(select=self.machine.get())

    def show_history(self):
        m = self.cur()
        rows = db.history(db.connect(), m.equipment_number if m else None)
        w = tk.Toplevel(self); w.title("Order history")
        t = tk.Text(w, width=110, height=20); t.pack(fill="both", expand=True)
        t.insert("end", "\n".join(" | ".join(str(c) for c in r) for r in rows) or "No orders logged yet.")

    def say(self, msg):
        self.log.config(state="normal"); self.log.insert("end", msg + "\n")
        self.log.see("end"); self.log.config(state="disabled")

    def pump(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "log": self.say(val)
                elif kind == "done":
                    self.busy = False; self.btn.config(state="normal")
        except queue.Empty:
            pass
        self.after(150, self.pump)

    def run(self):
        m, items = self.cur(), self.items()
        if self.busy or not m: return
        if not items:
            messagebox.showwarning("Nothing to order", "Enter at least one toner code with quantity."); return
        live = self.live.get()
        if live and not messagebox.askyesno(
                "Confirm", f"Place a REAL order for {m.label} ({m.equipment_number})?\n\n"
                + "\n".join(f"{q} x {c}" for c, q in items.items())):
            return
        self.busy = True; self.btn.config(state="disabled")
        threading.Thread(target=self.work, args=(m, items, live, self.discover.get()), daemon=True).start()

    def work(self, m, items, live, discover):
        class W:  # route print() from portal.py into the log pane
            def write(s, t):
                if t.strip(): self.q.put(("log", t.rstrip()))
            def flush(s): pass
        old, sys.stdout = sys.stdout, W()
        con = db.connect()
        try:
            print(f"{m.label}: {items} [{'LIVE' if live else 'dry run'}]")
            print("A browser window will open. Solve the captcha if shown.")
            status, ref = place_order(m, items, confirm=live, discover=discover)
            db.log_order(con, m, items, status, reference=ref)
            print(f"Result: {status}" + (f"  ref={ref}" if ref else ""))
        except PortalError as e:
            db.log_order(con, m, items, "failed", note=str(e)); print(f"FAILED: {e}")
        except Exception as e:
            db.log_order(con, m, items, "failed", note=repr(e)); print(f"ERROR: {e!r}")
        finally:
            sys.stdout = old
            self.q.put(("done", None))


def main():
    App().mainloop()
