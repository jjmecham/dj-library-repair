"""UI mockup only — for reviewing the proposed menu/stage layout with Jeremy.

No file system access. No real repair logic. Every button just writes a line
to the log panel so the navigation and interaction pattern (multi-screen,
preview -> confirm -> execute, per Decision 11 in plan/00-decisions.md) can be
seen and discussed before any application code is written.

Stage order and labels come from INSTRUCTIONS.md Section 7 and the decisions
recorded in plan/00-decisions.md (ghost-folder cleanup first, then extension
repair, then samples/duplicates/etc.). Items marked "(pending decision N)"
are not yet confirmed by Jeremy.
"""

import tkinter as tk
from tkinter import ttk

FONT = ("Segoe UI", 14, "bold")

STAGES = [
    ("1 Ghost folders", [
        "Move desktop.ini and thumbs.db to archive",
        "Unhide other hidden items",
        "Remove empty folders only",
    ], "#e06666"),
    ("2 Extension repair", [
        "Detect real type from file contents",
        "Rename to corrected extension",
        "Collisions to copies folder, name pending",
    ], "#f6b26b"),
    ("3 Samples", [
        "30 seconds or less is a sample",
        "30 to 60 seconds is scored, threshold 6",
        "Over 60 seconds is never a sample",
    ], "#ffd966"),
    ("4 Duplicates exact", [
        "Match by MD5 hash",
        "Match by Title and size",
        "Keeper picked by art, key fields, total tags",
    ], "#93c47d"),
    ("5 Duplicates weak, pending decision 4", [
        "Name based candidates",
        "Destination pending, review or automatic",
    ], "#76a5af"),
    ("6 Validate and repair", [
        "20 or more runs of 20 random files",
        "Check equal or better copy remains",
        "Repair offered only on failure",
    ], "#6fa8dc"),
    ("7 Layout, pending decision 3", [
        "Flatten to repaired music folder, or",
        "Keep artist and album folder structure",
    ], "#8e7cc3"),
    ("8 Renaming, pending decisions 5 and 8", [
        "Winners only, confirmation required",
        "Collisions resolved inside the library",
    ], "#c27ba0"),
    ("9 Rehash and recheck", [
        "Rehash after tag edits",
        "Final exact duplicate pass",
    ], "#a9a9a9"),
    ("10 Final cleanup", [
        "Repeat empty folder cleanup",
        "Balance file counts, write report",
    ], "#b4a7d6"),
]


class MockApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Music Repair App menu mockup, not functional")
        self.geometry("1100x520")

        sidebar = ttk.Frame(self, padding=4)
        sidebar.pack(side="left", fill="y")

        self.content = ttk.Frame(self, padding=12)
        self.content.pack(side="left", fill="both", expand=True)

        self.log = tk.Text(self, width=34, font=FONT, state="disabled",
                            background="#111", foreground="#0f0")
        self.log.pack(side="right", fill="y")

        self.buttons = []
        for label, substeps, color in STAGES:
            b = tk.Button(sidebar, text=label, font=FONT, bg=color, fg="black",
                          anchor="w", justify="left", relief="flat", padx=10, pady=6,
                          width=34, wraplength=320,
                          command=lambda l=label, s=substeps: self.show_stage(l, s))
            b.pack(fill="x", pady=1)
            self.buttons.append(b)

        self.show_stage(*STAGES[0][:2])

    def _write_log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def show_stage(self, label, substeps):
        for w in self.content.winfo_children():
            w.destroy()

        ttk.Label(self.content, text=label, font=FONT, foreground="black").pack(anchor="w")
        ttk.Separator(self.content).pack(fill="x", pady=6)

        for s in substeps:
            ttk.Label(self.content, text=s, font=FONT, foreground="black").pack(anchor="w")

        btns = ttk.Frame(self.content)
        btns.pack(anchor="w", pady=16)
        tk.Button(btns, text="Preview", font=FONT, anchor="w",
                  command=lambda: self._write_log(f"{label}: preview, no changes made")).pack(side="left", padx=4)
        tk.Button(btns, text="Confirm", font=FONT, anchor="w",
                  command=lambda: self._write_log(f"{label}: confirmed")).pack(side="left", padx=4)
        tk.Button(btns, text="Execute", font=FONT, anchor="w",
                  command=lambda: self._write_log(f"{label}: execute, mock only")).pack(side="left", padx=4)

        self._write_log(f"viewing: {label}")


if __name__ == "__main__":
    MockApp().mainloop()

