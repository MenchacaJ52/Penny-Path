# -*- coding: utf-8 -*-
"""
app.py  —  PennyPath GUI
Run:  py app.py

Dark-mode, Gen-Z aesthetic built on standard tkinter (no extra deps).
"""
import sys, os, io, re, hashlib, datetime, threading
sys.path.insert(0, os.path.dirname(__file__))

import tkinter as tk
from tkinter import ttk, messagebox

from database          import Database
from accounts          import SavingsAccount, CheckingAccount, WageAccount
from wages             import Wages
from expenses          import Needs, Wants
from budget            import Budget, BudgetAdvisor
from home_savings_plan import HomeSavingsPlan

# ══════════════════════════════════════════════════════════════════════════════
#  Design tokens
# ══════════════════════════════════════════════════════════════════════════════
C = {
    "bg":      "#0d0d14",
    "card":    "#1a1a2e",
    "sidebar": "#13131f",
    "border":  "#2d2d44",
    "purple":  "#a855f7",
    "pink":    "#ec4899",
    "green":   "#22c55e",
    "amber":   "#f59e0b",
    "red":     "#ef4444",
    "text":    "#e2e8f0",
    "muted":   "#64748b",
    "input":   "#0f0f1a",
    "hover":   "#22223a",
}

F = {
    "title": ("Segoe UI", 24, "bold"),
    "h2":    ("Segoe UI", 15, "bold"),
    "h3":    ("Segoe UI", 11, "bold"),
    "body":  ("Segoe UI", 10),
    "small": ("Segoe UI", 9),
    "mono":  ("Consolas", 10),
    "logo":  ("Segoe UI", 17, "bold"),
}

NEEDS_SUBS = ["groceries", "rent/mortgage", "utilities", "gas/transport",
              "insurance", "bills", "healthcare", "childcare", "other"]
WANTS_SUBS = ["dining out", "entertainment", "shopping", "subscriptions",
              "hobbies", "travel", "personal care", "gifts", "other"]
FREQS      = ["Monthly", "Weekly", "Biweekly", "One Time"]

REGIONS = {
    "United States": "MSPUS",
    "Northeast":     "MSPNE",
    "Midwest":       "MSPMW",
    "South":         "MSPS",
    "West":          "MSPW",
}
DOWN_PCTS = {
    "3%  — Conventional (PMI)":   0.03,
    "5%  — Low down payment":     0.05,
    "10% — Moderate":             0.10,
    "20% — Avoid PMI (recommended)": 0.20,
    "25% — Strong equity":        0.25,
}

NAV_ITEMS = [
    ("dashboard", "  📊  Dashboard"),
    ("expenses",  "  💸  Expenses"),
    ("wages",     "  💵  Wages"),
    ("afford",    "  🏦  Affordability"),
    ("advisor",   "  🤖  Budget AI"),
    ("home",      "  🏠  Home Plan"),
]


# ══════════════════════════════════════════════════════════════════════════════
#  Shared widget helpers
# ══════════════════════════════════════════════════════════════════════════════

def _bg(widget):
    try:
        return widget.cget("bg")
    except Exception:
        return C["bg"]


class StyledEntry(tk.Entry):
    def __init__(self, parent, **kw):
        kw.setdefault("bg",                C["input"])
        kw.setdefault("fg",                C["text"])
        kw.setdefault("insertbackground",  C["text"])
        kw.setdefault("relief",            "flat")
        kw.setdefault("font",              F["body"])
        kw.setdefault("highlightthickness", 1)
        kw.setdefault("highlightbackground", C["border"])
        kw.setdefault("highlightcolor",    C["green"])
        super().__init__(parent, **kw)


class PillBtn(tk.Button):
    def __init__(self, parent, text="", command=None, color=None, **kw):
        c = color or C["green"]
        kw.setdefault("bg",               c)
        kw.setdefault("fg",               "#ffffff")
        kw.setdefault("activebackground", c)
        kw.setdefault("activeforeground", "#ffffff")
        kw.setdefault("font",             F["body"])
        kw.setdefault("relief",           "flat")
        kw.setdefault("cursor",           "hand2")
        kw.setdefault("padx",             20)
        kw.setdefault("pady",             9)
        super().__init__(parent, text=text, command=command, **kw)


def Lbl(parent, text, style="body", fg=None, **kw):
    kw.setdefault("bg", _bg(parent))
    return tk.Label(parent, text=text, font=F.get(style, F["body"]),
                    fg=fg or C["text"], **kw)


def _divider(parent, color=None, pady=8):
    tk.Frame(parent, bg=color or C["border"], height=1).pack(
        fill="x", padx=0, pady=pady)


def _styled_combo(parent, var, values, width=18):
    cb = ttk.Combobox(parent, textvariable=var, values=values,
                      width=width, state="readonly", font=F["body"])
    return cb


def _hash_pw(pw: str) -> str:
    return hashlib.sha256(f"pennypath_salt_2024{pw}".encode()).hexdigest()


def _strip_ansi(s: str) -> str:
    return re.sub(r'\x1b\[[0-9;]*m', '', s)


# ══════════════════════════════════════════════════════════════════════════════
#  Scrollable canvas wrapper
# ══════════════════════════════════════════════════════════════════════════════

class ScrollFrame(tk.Frame):
    """A frame that scrolls vertically."""
    def __init__(self, parent, **kw):
        kw.setdefault("bg", C["bg"])
        super().__init__(parent, **kw)

        self._canvas = tk.Canvas(self, bg=self.cget("bg"),
                                  highlightthickness=0)
        self._sb = ttk.Scrollbar(self, orient="vertical",
                                  command=self._canvas.yview)
        self.inner = tk.Frame(self._canvas, bg=self.cget("bg"))

        self._win = self._canvas.create_window((0, 0), window=self.inner,
                                                anchor="nw")
        self._canvas.configure(yscrollcommand=self._sb.set)

        self._sb.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        self.inner.bind("<Configure>", self._on_configure)
        self._canvas.bind("<Configure>", self._on_canvas_resize)
        self._canvas.bind_all("<MouseWheel>",
                               lambda e: self._canvas.yview_scroll(
                                   -1 if e.delta > 0 else 1, "units"))

    def _on_configure(self, _):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_resize(self, e):
        self._canvas.itemconfig(self._win, width=e.width)


# ══════════════════════════════════════════════════════════════════════════════
#  Balance card
# ══════════════════════════════════════════════════════════════════════════════

class BalCard(tk.Frame):
    def __init__(self, parent, title, accent):
        super().__init__(parent, bg=C["card"], padx=20, pady=16)
        Lbl(self, title, "small", C["muted"]).pack(anchor="w")
        self._val = tk.Label(self, text="$0.00",
                             font=("Segoe UI", 20, "bold"),
                             bg=C["card"], fg=accent)
        self._val.pack(anchor="w", pady=(4, 0))
        # colored bottom stripe
        tk.Frame(self, bg=accent, height=3).pack(
            fill="x", side="bottom")

    def update_val(self, v: float):
        self._val.config(text=f"${v:,.2f}")


# ══════════════════════════════════════════════════════════════════════════════
#  Auth screen
# ══════════════════════════════════════════════════════════════════════════════

class AuthScreen(tk.Frame):
    def __init__(self, parent, db: Database, on_success):
        super().__init__(parent, bg=C["bg"])
        self._db = db
        self._on_success = on_success
        self._mode = "login"
        self._build()

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        wrap = tk.Frame(self, bg=C["bg"])
        wrap.grid(row=0, column=0)

        # Branding
        Lbl(wrap, "PennyPath", "title", C["green"]).pack(pady=(0, 4))
        # Mini sparkline decoration
        _spark = tk.Canvas(wrap, width=228, height=34, bg=C["bg"],
                           highlightthickness=0)
        _spark.pack(pady=(0, 6))
        _bars = [5, 9, 7, 13, 10, 18, 14, 22, 17, 28]
        _bw, _gap = 14, 8
        for _i, _h in enumerate(_bars):
            _x0 = _i * (_bw + _gap) + 8
            _x1 = _x0 + _bw
            _clr = C["green"] if _i >= len(_bars) - 4 else "#2d5a3d"
            _spark.create_rectangle(_x0, 34 - _h, _x1, 34,
                                    fill=_clr, outline="", width=0)
        Lbl(wrap, "your money, understood.", "small", C["muted"]).pack(pady=(0, 28))

        # Card
        card = tk.Frame(wrap, bg=C["card"], padx=40, pady=36)
        card.pack()

        # Tab buttons
        tabs = tk.Frame(card, bg=C["card"])
        tabs.pack(fill="x", pady=(0, 24))
        self._ltab = tk.Button(tabs, text="Log In",  **self._tstyle(True),
                               command=lambda: self._switch("login"))
        self._rtab = tk.Button(tabs, text="Sign Up", **self._tstyle(False),
                               command=lambda: self._switch("register"))
        self._ltab.pack(side="left", expand=True, fill="x")
        self._rtab.pack(side="left", expand=True, fill="x")

        # Fields
        fields = tk.Frame(card, bg=C["card"])
        fields.pack(fill="x")

        Lbl(fields, "Username", "small", C["muted"], anchor="w").pack(fill="x")
        self._uname = StyledEntry(fields, width=30)
        self._uname.pack(fill="x", pady=(2, 14))

        Lbl(fields, "Password", "small", C["muted"], anchor="w").pack(fill="x")
        self._pw = StyledEntry(fields, show="•", width=30)
        self._pw.pack(fill="x", pady=(2, 14))

        # Confirm password (hidden by default)
        self._conf_wrap = tk.Frame(fields, bg=C["card"])
        Lbl(self._conf_wrap, "Confirm Password", "small", C["muted"],
            anchor="w").pack(fill="x")
        self._conf = StyledEntry(self._conf_wrap, show="•", width=30)
        self._conf.pack(fill="x", pady=(2, 14))

        self._err_lbl = Lbl(card, "", "small", C["red"])
        self._err_lbl.pack(fill="x", pady=(0, 10))

        self._submit = PillBtn(card, text="Log In", command=self._submit)
        self._submit.pack(fill="x", ipady=2)

        self._pw.bind("<Return>",   lambda _: self._submit())
        self._conf.bind("<Return>", lambda _: self._submit())
        self._uname.focus()

    def _tstyle(self, active: bool) -> dict:
        return dict(
            bg=C["green"] if active else C["card"],
            fg="#fff"      if active else C["muted"],
            activebackground=C["green"], activeforeground="#fff",
            relief="flat", font=F["h3"], padx=12, pady=8, cursor="hand2",
        )

    def _switch(self, mode: str):
        self._mode = mode
        is_login = (mode == "login")
        self._ltab.config(**self._tstyle(is_login))
        self._rtab.config(**self._tstyle(not is_login))
        if is_login:
            self._conf_wrap.pack_forget()
            self._submit.config(text="Log In")
        else:
            self._conf_wrap.pack(fill="x")
            self._submit.config(text="Create Account")
        self._err_lbl.config(text="")

    def _err(self, msg: str):
        self._err_lbl.config(text=msg)

    def _submit(self):
        u = self._uname.get().strip()
        p = self._pw.get().strip()
        self._err_lbl.config(text="")

        if self._mode == "login":
            row = self._db.get_user(u)
            if row is None:
                self._err("User not found.")
                return
            if _hash_pw(p) != row[2]:
                self._err("Incorrect password.")
                return
            self._on_success({"id": row[0], "username": row[1]})
        else:
            c = self._conf.get().strip()
            if not u:
                self._err("Username cannot be empty.")
                return
            if len(p) < 4:
                self._err("Password must be at least 4 characters.")
                return
            if p != c:
                self._err("Passwords do not match.")
                return
            if not self._db.create_user(u, _hash_pw(p)):
                self._err("Username already taken.")
                return
            row = self._db.get_user(u)
            self._on_success({"id": row[0], "username": row[1]})


# ══════════════════════════════════════════════════════════════════════════════
#  Sidebar
# ══════════════════════════════════════════════════════════════════════════════

class Sidebar(tk.Frame):
    def __init__(self, parent, on_nav, on_logout, username, on_toggle):
        super().__init__(parent, bg=C["sidebar"], width=210)
        self.pack_propagate(False)
        self._on_nav    = on_nav
        self._on_toggle = on_toggle
        self._btns: dict[str, tk.Button] = {}
        self._active: str | None = None
        self._build(on_logout, username)

    def _build(self, on_logout, username):
        # Logo row with collapse arrow
        logo_f = tk.Frame(self, bg=C["sidebar"])
        logo_f.pack(fill="x", pady=(24, 4))
        Lbl(logo_f, "PennyPath", "logo", C["green"]).pack(
            padx=20, anchor="w", side="left")
        tk.Button(
            logo_f, text="◀", font=("Segoe UI", 9),
            bg=C["sidebar"], fg=C["muted"],
            activebackground=C["sidebar"], activeforeground=C["green"],
            relief="flat", cursor="hand2", bd=0,
            command=self._on_toggle,
        ).pack(side="right", padx=10)

        Lbl(self, f"@{username}", "small", C["muted"]).pack(
            anchor="w", padx=22, pady=(0, 18))

        _divider(self, pady=0)
        tk.Frame(self, bg=C["sidebar"], height=10).pack()

        # Nav items
        for key, label in NAV_ITEMS:
            btn = tk.Button(
                self, text=label, font=F["body"], anchor="w",
                relief="flat", bg=C["sidebar"], fg=C["muted"],
                activebackground=C["hover"], activeforeground=C["text"],
                cursor="hand2", padx=14, pady=10,
                command=lambda k=key: self._go(k),
            )
            btn.pack(fill="x", padx=8, pady=1)
            self._btns[key] = btn

        # Logout pinned to bottom
        tk.Frame(self, bg=C["sidebar"]).pack(fill="both", expand=True)
        _divider(self, pady=4)
        tk.Button(
            self, text="  Log Out", font=F["body"], anchor="w",
            relief="flat", bg=C["sidebar"], fg=C["muted"],
            activebackground=C["hover"], activeforeground=C["red"],
            cursor="hand2", padx=14, pady=10, command=on_logout,
        ).pack(fill="x", padx=8, pady=(0, 14))

    def _go(self, key: str):
        if self._active:
            self._btns[self._active].config(bg=C["sidebar"], fg=C["muted"])
        self._active = key
        self._btns[key].config(bg=C["hover"], fg=C["green"])
        self._on_nav(key)

    def set_active(self, key: str):
        if self._active and self._active in self._btns:
            self._btns[self._active].config(bg=C["sidebar"], fg=C["muted"])
        self._active = key
        if key in self._btns:
            self._btns[key].config(bg=C["hover"], fg=C["green"])


# ══════════════════════════════════════════════════════════════════════════════
#  Page base
# ══════════════════════════════════════════════════════════════════════════════

class PageBase(tk.Frame):
    def __init__(self, parent, app, title, subtitle=""):
        super().__init__(parent, bg=C["bg"])
        self._app = app
        # Scrollable content
        self._scroll = ScrollFrame(self, bg=C["bg"])
        self._scroll.pack(fill="both", expand=True)
        self.body = self._scroll.inner
        # Header
        hdr = tk.Frame(self.body, bg=C["bg"])
        hdr.pack(fill="x", padx=32, pady=(28, 4))
        Lbl(hdr, title, "title").pack(anchor="w")
        if subtitle:
            Lbl(hdr, subtitle, "body", C["muted"]).pack(anchor="w", pady=(2, 0))
        _divider(self.body, pady=(12, 16))

    def refresh(self):
        pass


# ══════════════════════════════════════════════════════════════════════════════
#  Dashboard
# ══════════════════════════════════════════════════════════════════════════════

class DashboardPage(PageBase):
    def __init__(self, parent, app):
        super().__init__(parent, app, "Dashboard")
        self._build()

    def _build(self):
        b = self.body

        self._greet = Lbl(b, "Hey! ", "h2", C["green"])
        self._greet.pack(anchor="w", padx=32, pady=(0, 16))

        # Balance cards
        cards_f = tk.Frame(b, bg=C["bg"])
        cards_f.pack(fill="x", padx=32, pady=(0, 20))
        cards_f.columnconfigure((0, 1, 2, 3, 4), weight=1, uniform="c")

        self._c_check  = BalCard(cards_f, "Checking",       C["green"])
        self._c_save   = BalCard(cards_f, "Savings",         C["purple"])
        self._c_income = BalCard(cards_f, "Monthly Income",  C["green"])
        self._c_needs  = BalCard(cards_f, "Total Needs",     C["amber"])
        self._c_wants  = BalCard(cards_f, "Total Wants",     C["red"])

        for i, c in enumerate((self._c_check, self._c_save, self._c_income,
                                self._c_needs, self._c_wants)):
            c.grid(row=0, column=i, padx=5, sticky="nsew")

        # Budget bar
        bbar_lbl_f = tk.Frame(b, bg=C["bg"])
        bbar_lbl_f.pack(fill="x", padx=32, pady=(4, 6))
        Lbl(bbar_lbl_f, "📈  Budget Breakdown", "h3").pack(side="left")
        self._status_lbl = Lbl(bbar_lbl_f, "", "small", C["muted"])
        self._status_lbl.pack(side="right")

        self._bbar = tk.Canvas(b, height=22, bg=C["card"],
                                highlightthickness=0)
        self._bbar.pack(fill="x", padx=32)

        self._bbar_leg = Lbl(b, "", "small", C["muted"])
        self._bbar_leg.pack(anchor="w", padx=32, pady=(4, 0))

        # Recent expenses
        _divider(b, pady=(20, 8))
        Lbl(b, "🧾  Recent Expenses", "h3").pack(anchor="w", padx=32, pady=(0, 8))
        self._recent_f = tk.Frame(b, bg=C["bg"])
        self._recent_f.pack(fill="x", padx=32, pady=(0, 24))

    def refresh(self):
        a = self._app
        self._greet.config(text=f"💰  Hey, {a.current_user['username']}!")

        income = a.wages.weekly_wage * 4
        self._c_check.update_val(a.checking.balance)
        self._c_save.update_val(a.savings.balance)
        self._c_income.update_val(income)
        self._c_needs.update_val(a.necessary_total)
        self._c_wants.update_val(a.nonnecessary_total)

        # Budget bar
        total_exp = a.necessary_total + a.nonnecessary_total
        denom = income if income > 0 else max(total_exp, 1)

        self._bbar.update_idletasks()
        W = max(self._bbar.winfo_width(), 300)
        nw = min(int(W * a.necessary_total / denom), W)
        ww = min(int(W * a.nonnecessary_total / denom), W - nw)
        sw = max(0, W - nw - ww)

        self._bbar.delete("all")
        if nw: self._bbar.create_rectangle(0,  0, nw,       22, fill=C["amber"], outline="")
        if ww: self._bbar.create_rectangle(nw, 0, nw + ww,  22, fill=C["red"],   outline="")
        if sw: self._bbar.create_rectangle(nw + ww, 0, W,   22, fill=C["green"], outline="")

        saved = income - total_exp
        self._bbar_leg.config(
            text=f"Needs  ${a.necessary_total:,.0f}   |   "
                 f"Wants  ${a.nonnecessary_total:,.0f}   |   "
                 f"Saved  ${saved:,.0f}")

        if income <= 0:
            st, sc = "Set your wage to see insights.", C["muted"]
        elif saved < 0:
            st, sc = "Spending exceeds income!", C["red"]
        elif saved / income < 0.10:
            st, sc = "Tight budget — try trimming wants", C["amber"]
        else:
            st, sc = f"Saving {saved/income*100:.0f}% of income", C["green"]
        self._status_lbl.config(text=st, fg=sc)

        # Recent expenses
        for w in self._recent_f.winfo_children():
            w.destroy()
        recent = a.expenses[-5:][::-1]
        if not recent:
            Lbl(self._recent_f, "No expenses logged yet.", "small",
                C["muted"]).pack(anchor="w", pady=6)
        for exp in recent:
            row = tk.Frame(self._recent_f, bg=C["card"], padx=16, pady=10)
            row.pack(fill="x", pady=2)
            accent = C["amber"] if isinstance(exp, Needs) else C["red"]
            Lbl(row, exp.name.title(), fg=C["text"]).pack(side="left")
            Lbl(row, exp.subcategory.title(), "small", C["muted"]).pack(
                side="left", padx=12)
            Lbl(row, f"${exp.monthly_amount():,.2f}/mo", "h3",
                accent).pack(side="right")


# ══════════════════════════════════════════════════════════════════════════════
#  Expenses
# ══════════════════════════════════════════════════════════════════════════════

class ExpensesPage(PageBase):
    def __init__(self, parent, app):
        super().__init__(parent, app, "Expenses",
                         "Log your needs and wants.")
        self._cat = "needs"
        self._build()

    def _build(self):
        b = self.body

        # Tab switcher
        tabs = tk.Frame(b, bg=C["bg"])
        tabs.pack(fill="x", padx=32, pady=(0, 16))
        self._ntab = self._tbtn(tabs, "Needs", "needs", True)
        self._wtab = self._tbtn(tabs, "Wants", "wants", False)
        self._ntab.pack(side="left", padx=(0, 6))
        self._wtab.pack(side="left")

        # Add-expense form
        form = tk.Frame(b, bg=C["card"], padx=24, pady=20)
        form.pack(fill="x", padx=32, pady=(0, 16))
        Lbl(form, "Add Expense", "h3").pack(anchor="w", pady=(0, 12))

        row0 = tk.Frame(form, bg=C["card"])
        row0.pack(fill="x")

        # Name
        nf = tk.Frame(row0, bg=C["card"])
        nf.pack(side="left", fill="x", expand=True, padx=(0, 10))
        Lbl(nf, "Name", "small", C["muted"], anchor="w").pack(fill="x")
        self._name_e = StyledEntry(nf)
        self._name_e.pack(fill="x", pady=(2, 0), ipady=3)

        # Amount
        af = tk.Frame(row0, bg=C["card"])
        af.pack(side="left", padx=(0, 10))
        Lbl(af, "Amount ($)", "small", C["muted"], anchor="w").pack(fill="x")
        self._ammt_e = StyledEntry(af, width=10)
        self._ammt_e.pack(pady=(2, 0), ipady=3)

        # Frequency
        ff = tk.Frame(row0, bg=C["card"])
        ff.pack(side="left", padx=(0, 10))
        Lbl(ff, "Frequency", "small", C["muted"], anchor="w").pack(fill="x")
        self._freq_v = tk.StringVar(value="Monthly")
        self._freq_cb = _styled_combo(ff, self._freq_v, FREQS, width=12)
        self._freq_cb.pack(pady=(2, 0))

        # Subcategory
        sf = tk.Frame(row0, bg=C["card"])
        sf.pack(side="left", padx=(0, 10))
        Lbl(sf, "Subcategory", "small", C["muted"], anchor="w").pack(fill="x")
        self._sub_v = tk.StringVar(value=NEEDS_SUBS[0])
        self._sub_cb = _styled_combo(sf, self._sub_v, NEEDS_SUBS, width=16)
        self._sub_cb.pack(pady=(2, 0))

        PillBtn(row0, text="+ Add", command=self._add).pack(
            side="left", anchor="s", padx=(0, 0), pady=(16, 0))

        self._ferr = Lbl(form, "", "small", C["red"])
        self._ferr.pack(anchor="w", pady=(8, 0))

        # Totals bar
        ctrl = tk.Frame(b, bg=C["bg"])
        ctrl.pack(fill="x", padx=32, pady=(0, 10))
        self._total_lbl = Lbl(ctrl, "", "h3")
        self._total_lbl.pack(side="left")
        PillBtn(ctrl, text="Clear All", color=C["red"],
                command=self._clear).pack(side="right")

        # Expense list
        self._list_sf = ScrollFrame(b, bg=C["bg"])
        self._list_sf.pack(fill="both", expand=True, padx=32, pady=(0, 24))
        self._list_inner = self._list_sf.inner

    def _tbtn(self, parent, text, key, active):
        return tk.Button(
            parent, text=text, font=F["h3"],
            bg=C["green"] if active else C["card"],
            fg="#fff"       if active else C["muted"],
            activebackground=C["green"], activeforeground="#fff",
            relief="flat", padx=20, pady=8, cursor="hand2",
            command=lambda: self._switch(key),
        )

    def _switch(self, key):
        self._cat = key
        is_n = (key == "needs")
        self._ntab.config(bg=C["green"] if is_n else C["card"],
                          fg="#fff"       if is_n else C["muted"])
        self._wtab.config(bg=C["green"] if not is_n else C["card"],
                          fg="#fff"       if not is_n else C["muted"])
        subs = NEEDS_SUBS if is_n else WANTS_SUBS
        self._sub_cb.config(values=subs)
        self._sub_v.set(subs[0])
        self.refresh()

    def _add(self):
        name  = self._name_e.get().strip()
        ammt_s = self._ammt_e.get().strip()
        freq  = self._freq_v.get()
        sub   = self._sub_v.get()
        self._ferr.config(text="")

        if not name:
            self._ferr.config(text="Name is required.")
            return
        try:
            ammt = float(ammt_s)
            if ammt <= 0:
                raise ValueError
        except ValueError:
            self._ferr.config(text="Enter a valid positive amount.")
            return

        a   = self._app
        cls = Needs if self._cat == "needs" else Wants
        exp = object.__new__(cls)
        exp.name = name; exp.ammt = ammt
        exp.freq = freq; exp.subcategory = sub; exp.frm = ""

        a.expenses.append(exp)
        if self._cat == "needs":
            a.necessary_total += exp.monthly_amount()
        else:
            a.nonnecessary_total += exp.monthly_amount()

        a.db.save_expense(self._cat, sub, name, ammt, freq, a.current_user["id"])
        a.autosave()

        self._name_e.delete(0, "end")
        self._ammt_e.delete(0, "end")
        self.refresh()

    def _clear(self):
        if not messagebox.askyesno("Clear All", "Delete all expenses?"):
            return
        a = self._app
        a.expenses.clear()
        a.necessary_total = 0.0; a.nonnecessary_total = 0.0
        a.db.clear_expenses(a.current_user["id"])
        self.refresh()

    def refresh(self):
        a   = self._app
        fil = [e for e in a.expenses
               if (isinstance(e, Needs) if self._cat == "needs"
                   else isinstance(e, Wants))]
        total = sum(e.monthly_amount() for e in fil)
        label = "Needs" if self._cat == "needs" else "Wants"
        self._total_lbl.config(text=f"{label} total:  ${total:,.2f}/mo")

        for w in self._list_inner.winfo_children():
            w.destroy()
        accent = C["amber"] if self._cat == "needs" else C["red"]

        if not fil:
            Lbl(self._list_inner, "No expenses yet. Add one above!",
                "body", C["muted"]).pack(pady=20)
            return

        for exp in fil:
            card = tk.Frame(self._list_inner, bg=C["card"], padx=18, pady=12)
            card.pack(fill="x", pady=3)

            left = tk.Frame(card, bg=C["card"])
            left.pack(side="left", fill="both", expand=True)
            Lbl(left, exp.name.title(), "h3").pack(anchor="w")
            Lbl(left, f"{exp.subcategory.title()}  ·  {exp.freq}",
                "small", C["muted"]).pack(anchor="w")

            right = tk.Frame(card, bg=C["card"])
            right.pack(side="right")
            Lbl(right, f"${exp.monthly_amount():,.2f}/mo", "h3",
                accent).pack(anchor="e")
            Lbl(right, f"${exp.ammt:,.2f} {exp.freq}", "small",
                C["muted"]).pack(anchor="e")


# ══════════════════════════════════════════════════════════════════════════════
#  Wages
# ══════════════════════════════════════════════════════════════════════════════

class WagesPage(PageBase):
    def __init__(self, parent, app):
        super().__init__(parent, app, "Wages")
        self._build()

    def _build(self):
        b = self.body

        # Big wage card
        wcard = tk.Frame(b, bg=C["card"], padx=28, pady=24)
        wcard.pack(fill="x", padx=32, pady=(0, 16))

        Lbl(wcard, "Weekly Wage", "small", C["muted"]).pack(anchor="w")
        self._wage_lbl = tk.Label(wcard, text="$0.00",
                                   font=("Segoe UI", 36, "bold"),
                                   bg=C["card"], fg=C["green"])
        self._wage_lbl.pack(anchor="w", pady=(4, 0))
        self._monthly_lbl = Lbl(wcard, "~ $0.00 / month", "body", C["muted"])
        self._monthly_lbl.pack(anchor="w", pady=(2, 8))
        PillBtn(wcard, text="Set Weekly Wage",
                command=self._set_wage_dialog).pack(anchor="w")

        # Deposit
        dcard = tk.Frame(b, bg=C["card"], padx=28, pady=20)
        dcard.pack(fill="x", padx=32, pady=(0, 12))
        Lbl(dcard, "Deposit to Wage Account", "h3").pack(anchor="w", pady=(0, 12))
        drow = tk.Frame(dcard, bg=C["card"])
        drow.pack(fill="x")
        Lbl(drow, "Weeks:", fg=C["muted"]).pack(side="left")
        self._weeks_e = StyledEntry(drow, width=5)
        self._weeks_e.insert(0, "1")
        self._weeks_e.pack(side="left", padx=8, ipady=3)
        PillBtn(drow, text="Deposit", command=self._deposit).pack(side="left")
        self._wacct_lbl = Lbl(dcard, "Wage Account: $0.00", "small", C["muted"])
        self._wacct_lbl.pack(anchor="w", pady=(10, 0))

        # Transfer
        xcard = tk.Frame(b, bg=C["card"], padx=28, pady=20)
        xcard.pack(fill="x", padx=32, pady=(0, 12))
        Lbl(xcard, "Transfer Wages to Savings", "h3").pack(anchor="w", pady=(0, 12))
        xrow = tk.Frame(xcard, bg=C["card"])
        xrow.pack(fill="x")
        Lbl(xrow, "Amount: $", fg=C["muted"]).pack(side="left")
        self._xfer_e = StyledEntry(xrow, width=10)
        self._xfer_e.pack(side="left", padx=8, ipady=3)
        PillBtn(xrow, text="Transfer", command=self._transfer).pack(side="left")

        self._msg = Lbl(b, "", "small", C["green"])
        self._msg.pack(anchor="w", padx=32, pady=6)

    def _set_wage_dialog(self):
        dlg = tk.Toplevel(self)
        dlg.title("Set Weekly Wage")
        dlg.configure(bg=C["card"])
        dlg.resizable(False, False)
        dlg.grab_set()

        tk.Frame(dlg, bg=C["card"], height=12).pack()
        Lbl(dlg, "Weekly Wage ($)", "h3").pack(padx=36, pady=(8, 8))
        e = StyledEntry(dlg, width=16)
        e.pack(padx=36, pady=(0, 8), ipady=4)
        e.focus()

        def _save():
            try:
                v = float(e.get())
                if v <= 0:
                    raise ValueError
            except ValueError:
                return
            self._app.wages.weekly_wage = v
            self._app.autosave()
            dlg.destroy()
            self.refresh()

        e.bind("<Return>", lambda _: _save())
        PillBtn(dlg, text="Save", command=_save).pack(pady=(0, 24), padx=36, fill="x")

    def _deposit(self):
        try:
            weeks = int(self._weeks_e.get())
            if weeks <= 0:
                raise ValueError
        except ValueError:
            self._msg.config(text="Enter a valid number of weeks.", fg=C["red"])
            return
        if self._app.wages.weekly_wage <= 0:
            self._msg.config(text="Set your weekly wage first.", fg=C["red"])
            return
        self._app.wages.deposit_wage(self._app.wage_acct, weeks)
        self._msg.config(text=f"Deposited {weeks} week(s) of wages!", fg=C["green"])
        self.refresh()

    def _transfer(self):
        try:
            amt = float(self._xfer_e.get())
            if amt <= 0:
                raise ValueError
        except ValueError:
            self._msg.config(text="Enter a valid amount.", fg=C["red"])
            return
        self._app.wage_acct.withdraw_wage(amt, self._app.savings)
        self._app.autosave()
        self._msg.config(text=f"Transferred ${amt:,.2f} to Savings!", fg=C["green"])
        self._xfer_e.delete(0, "end")
        self.refresh()

    def refresh(self):
        w = self._app.wages.weekly_wage
        self._wage_lbl.config(text=f"${w:,.2f}")
        self._monthly_lbl.config(text=f"~ ${w * 4.33:,.2f} / month")
        self._wacct_lbl.config(
            text=f"Wage Account Balance:  ${self._app.wage_acct.balance:,.2f}")


# ══════════════════════════════════════════════════════════════════════════════
#  Affordability
# ══════════════════════════════════════════════════════════════════════════════

class AffordabilityPage(PageBase):
    def __init__(self, parent, app):
        super().__init__(parent, app, "Affordability Check",
                         "Find out if you can handle that loan.")
        self._build()

    def _build(self):
        b = self.body

        form = tk.Frame(b, bg=C["card"], padx=28, pady=24)
        form.pack(fill="x", padx=32, pady=(0, 16))

        fields_cfg = [
            ("Monthly Income ($)",       "_inc_e",  False),
            ("Item / Loan Price ($)",     "_ammt_e", False),
            ("Annual Interest Rate (%)",  "_rate_e", False),
            ("Loan Duration (months)",    "_mnth_e", False),
        ]
        for lbl, attr, _ in fields_cfg:
            Lbl(form, lbl, "small", C["muted"], anchor="w").pack(
                fill="x", pady=(8, 2))
            e = StyledEntry(form, width=24)
            e.pack(fill="x", ipady=4, pady=(0, 4))
            setattr(self, attr, e)

        PillBtn(form, text="Check Affordability",
                command=self._check).pack(fill="x", pady=(16, 0), ipady=2)

        self._result_f = tk.Frame(b, bg=C["bg"])
        self._result_f.pack(fill="x", padx=32, pady=(0, 24))

    def _check(self):
        for w in self._result_f.winfo_children():
            w.destroy()
        try:
            inc  = float(self._inc_e.get())
            ammt = float(self._ammt_e.get())
            rate = float(self._rate_e.get())
            mnth = int(self._mnth_e.get())
        except ValueError:
            Lbl(self._result_f,
                "Fill in all fields with valid numbers.",
                "body", C["red"]).pack(anchor="w", pady=8)
            return

        intrt = rate / 100 / 12
        monthly = (ammt * (intrt * (1 + intrt) ** mnth) /
                   ((1 + intrt) ** mnth - 1)) if intrt > 0 else ammt / max(mnth, 1)
        max_pay = inc * 0.36
        ok = monthly <= max_pay

        card = tk.Frame(self._result_f, bg=C["card"], padx=24, pady=20)
        card.pack(fill="x")

        color = C["green"] if ok else C["red"]
        icon  = "  You can afford this loan!" if ok else "  Cannot afford this loan."
        Lbl(card, icon, "h2", color).pack(anchor="w")
        _divider(card, pady=10)

        rows = [
            ("Monthly Payment",           f"${monthly:,.2f}"),
            ("Max Allowable (36% rule)",  f"${max_pay:,.2f}"),
            ("Your Monthly Income",       f"${inc:,.2f}"),
        ]
        for lbl, val in rows:
            r = tk.Frame(card, bg=C["card"])
            r.pack(fill="x", pady=3)
            Lbl(r, lbl, fg=C["muted"]).pack(side="left")
            Lbl(r, val, "h3",
                color if "Payment" in lbl else C["text"]).pack(side="right")

    def refresh(self):
        inc = self._app.wages.weekly_wage * 4
        if inc > 0:
            self._inc_e.delete(0, "end")
            self._inc_e.insert(0, f"{inc:.2f}")


# ══════════════════════════════════════════════════════════════════════════════
#  Budget AI
# ══════════════════════════════════════════════════════════════════════════════

class BudgetAIPage(PageBase):
    def __init__(self, parent, app):
        super().__init__(parent, app, "Budget AI",
                         "ML-powered 50/30/20 personalised recommendations.")
        self._build()

    def _build(self):
        b = self.body
        PillBtn(b, text="  Run Analysis",
                command=self._run).pack(anchor="w", padx=32, pady=(0, 16))

        self._out = tk.Text(
            b, bg=C["card"], fg=C["text"], font=F["mono"], relief="flat",
            padx=18, pady=18, wrap="word", state="disabled",
            highlightthickness=0, height=24,
        )
        self._out.pack(fill="both", expand=True, padx=32, pady=(0, 24))
        self._out.tag_config("head",   foreground=C["green"],
                              font=("Segoe UI", 11, "bold"))
        self._out.tag_config("green",  foreground=C["green"])
        self._out.tag_config("red",    foreground=C["red"])
        self._out.tag_config("amber",  foreground=C["amber"])
        self._out.tag_config("muted",  foreground=C["muted"])

    def _write(self, text, tag=""):
        self._out.insert("end", text, tag)

    def _run(self):
        a = self._app
        income = a.wages.weekly_wage * 4
        self._out.config(state="normal")
        self._out.delete("1.0", "end")

        if income <= 0:
            self._write("Set your weekly wage first (Wages page).\n", "red")
            self._out.config(state="disabled")
            return

        rec = a.advisor.recommend(income, a.necessary_total,
                                   a.nonnecessary_total, a.expenses)
        if not rec:
            self._write("Could not generate recommendation.\n", "red")
            self._out.config(state="disabled")
            return

        r = rec

        def ln(text="", tag=""):
            self._write(text + "\n", tag)

        ln("BUDGET RECOMMENDATION REPORT", "head")
        ln("=" * 52, "muted")
        ln(f"  Monthly Income    ${r['monthly_income']:>12,.2f}")
        ln()
        ln(f"  {'Category':<20} {'Recommended':>12}  {'Actual':>10}")
        ln("  " + "-" * 46, "muted")

        for cat, rk, ak in [("Needs  (50%)", "rec_needs",   "actual_needs"),
                             ("Wants  (30%)", "rec_wants",   "actual_wants"),
                             ("Savings(20%)", "rec_savings", "actual_savings")]:
            rv, av = r[rk], r[ak]
            is_savings = "Savings" in cat
            over = (av < rv) if is_savings else (av > rv)
            tag  = "red" if over else "green"
            self._write(f"  {cat:<20} ${rv:>10,.2f}  ", "")
            self._write(f"${av:>9,.2f}\n", tag)

        ln()
        ln("  Subcategory Breakdown:", "head")
        ln("  " + "-" * 46, "muted")

        for sub, info in r["subcategories"].items():
            if info["actual"] > 0:
                over = info["actual"] > info["recommended"]
                tag  = "red" if over else "green"
                self._write(f"  {sub.title():<24} ${info['recommended']:>8,.2f}  ")
                self._write(f"${info['actual']:>8,.2f}\n", tag)

        ln()
        ln("  Insights:", "head")

        shown = False
        if r["actual_needs"] > r["rec_needs"]:
            ln(f"  Needs are ${r['actual_needs']-r['rec_needs']:.2f} over target.", "red")
            shown = True
        if r["actual_wants"] > r["rec_wants"]:
            ln(f"  Wants are ${r['actual_wants']-r['rec_wants']:.2f} over target.", "red")
            shown = True
        if r["actual_savings"] < r["rec_savings"]:
            ln(f"  Savings are ${r['rec_savings']-r['actual_savings']:.2f} below target.", "amber")
            shown = True
        if not shown:
            ln("  All spending within recommended limits — great job!", "green")

        self._out.config(state="disabled")

    def refresh(self):
        pass


# ══════════════════════════════════════════════════════════════════════════════
#  Home Savings Plan
# ══════════════════════════════════════════════════════════════════════════════

class HomePlanPage(PageBase):
    def __init__(self, parent, app):
        super().__init__(parent, app, "Home Savings Plan",
                         "ML forecast of home prices + your savings roadmap.")
        self._build()

    def _build(self):
        b = self.body

        form = tk.Frame(b, bg=C["card"], padx=28, pady=24)
        form.pack(fill="x", padx=32, pady=(0, 16))
        form.columnconfigure((0, 1), weight=1, uniform="h")

        # Region
        Lbl(form, "Region", "small", C["muted"]).grid(
            row=0, column=0, sticky="w")
        self._region_v = tk.StringVar(value=list(REGIONS.keys())[0])
        _styled_combo(form, self._region_v, list(REGIONS.keys()),
                      width=26).grid(row=1, column=0, sticky="ew",
                                      padx=(0, 12), pady=(4, 14))

        # Target year
        Lbl(form, "Target Year", "small", C["muted"]).grid(
            row=0, column=1, sticky="w")
        self._year_e = StyledEntry(form, width=10)
        self._year_e.insert(0, str(datetime.date.today().year + 5))
        self._year_e.grid(row=1, column=1, sticky="ew", pady=(4, 14))

        # Down payment
        Lbl(form, "Down Payment %", "small", C["muted"]).grid(
            row=2, column=0, sticky="w")
        self._dp_v = tk.StringVar(value=list(DOWN_PCTS.keys())[3])
        _styled_combo(form, self._dp_v, list(DOWN_PCTS.keys()),
                      width=26).grid(row=3, column=0, sticky="ew",
                                      padx=(0, 12), pady=(4, 14))

        # Current savings
        Lbl(form, "Current Savings ($)", "small", C["muted"]).grid(
            row=2, column=1, sticky="w")
        self._sav_e = StyledEntry(form, width=12)
        self._sav_e.grid(row=3, column=1, sticky="ew", pady=(4, 14))

        # Interest rate
        Lbl(form, "Interest Rate (%)", "small", C["muted"]).grid(
            row=4, column=0, sticky="w", pady=(6, 0))
        self._rate_e = StyledEntry(form, width=10)
        self._rate_e.insert(0, "6.5")
        self._rate_e.grid(row=5, column=0, sticky="ew", padx=(0, 12), pady=(4, 14))

        # Loan term
        Lbl(form, "Loan Term (years)", "small", C["muted"]).grid(
            row=4, column=1, sticky="w", pady=(6, 0))
        self._term_v = tk.StringVar(value="30")
        _styled_combo(form, self._term_v, ["10", "15", "20", "30"],
                      width=10).grid(row=5, column=1, sticky="ew", pady=(4, 14))

        btn_row = tk.Frame(form, bg=C["card"])
        btn_row.grid(row=6, column=0, columnspan=2, sticky="w", pady=(4, 0))
        PillBtn(btn_row, text="Calculate", command=self._calc).pack(side="left")
        self._ferr = Lbl(btn_row, "", "small", C["red"])
        self._ferr.pack(side="left", padx=12)

        self._res_f = tk.Frame(b, bg=C["bg"])
        self._res_f.pack(fill="x", padx=32, pady=(0, 24))

    def _calc(self):
        for w in self._res_f.winfo_children():
            w.destroy()
        self._ferr.config(text="")

        hp = self._app.home_plan
        if not hp._trained:
            self._ferr.config(text="fredgraph.csv not found — feature unavailable.")
            return

        col = REGIONS[self._region_v.get()]
        try:
            year = int(self._year_e.get())
            if year < datetime.date.today().year:
                raise ValueError
        except ValueError:
            self._ferr.config(text="Enter a valid future year.")
            return

        dp = DOWN_PCTS[self._dp_v.get()]
        try:
            sav_txt = self._sav_e.get().strip()
            sav = float(sav_txt) if sav_txt else self._app.savings.balance
        except ValueError:
            self._ferr.config(text="Enter a valid savings amount.")
            return

        try:
            annual_rate = float(self._rate_e.get().strip()) / 100
            if annual_rate < 0:
                raise ValueError
        except ValueError:
            self._ferr.config(text="Enter a valid interest rate.")
            return

        loan_term = int(self._term_v.get())

        today = datetime.date.today()
        months = max(1, (year - today.year) * 12 + (1 - today.month))
        income = self._app.wages.weekly_wage * 4

        prices = hp._predict_price(col, year)
        lr_p, knn_p = prices["lr"], prices["knn"]
        avg_p = (lr_p + knn_p) / 2

        plans = [
            ("Linear Regression", lr_p,  hp._savings_plan(lr_p,  dp, sav, months, annual_rate, loan_term)),
            ("KNN",               knn_p, hp._savings_plan(knn_p, dp, sav, months, annual_rate, loan_term)),
            ("Average",           avg_p, hp._savings_plan(avg_p, dp, sav, months, annual_rate, loan_term)),
        ]

        # Header
        hdr = tk.Frame(self._res_f, bg=C["card"], padx=20, pady=14)
        hdr.pack(fill="x", pady=(0, 10))
        Lbl(hdr, f"{self._region_v.get()}  ·  Target {year}  ·  {self._dp_v.get().split('—')[0].strip()}",
            "h3", C["green"]).pack(anchor="w")
        Lbl(hdr, f"Savings: ${sav:,.0f}  ·  {months} months away",
            "small", C["muted"]).pack(anchor="w", pady=(4, 0))

        def _make_card(parent, model, price, plan):
            feasible = income > 0 and plan["monthly_needed"] <= income * 0.20
            mc = C["green"] if feasible else C["red"]
            card = tk.Frame(parent, bg=C["card"], padx=20, pady=14)
            card.pack(fill="x", pady=3)
            top = tk.Frame(card, bg=C["card"])
            top.pack(fill="x")
            Lbl(top, model, "h3").pack(side="left")
            Lbl(top, f"${price:,.0f}", "h3", C["green"]).pack(side="right")
            _divider(card, pady=6)
            for lbl, val, vc in [
                ("Down Payment Needed",  f"${plan['down_payment']:,.0f}",   C["text"]),
                ("Still Needed",         f"${plan['still_needed']:,.0f}",   C["text"]),
                ("Monthly Savings Req",  f"${plan['monthly_needed']:,.2f}",  mc),
                ("Est. Monthly Payment", f"${plan['monthly_payment']:,.2f}", C["amber"]),
            ]:
                r = tk.Frame(card, bg=C["card"])
                r.pack(fill="x", pady=1)
                Lbl(r, lbl, "small", C["muted"]).pack(side="left")
                Lbl(r, val, "body", vc).pack(side="right")

        # Always show Average
        _make_card(self._res_f, *plans[2])

        # LR + KNN hidden behind a toggle
        detail_frame = tk.Frame(self._res_f, bg=C["bg"])
        _expanded = [False]

        def _toggle():
            if _expanded[0]:
                detail_frame.pack_forget()
                toggle_btn.config(text="▶  Show Model Details (LR & KNN)")
            else:
                detail_frame.pack(fill="x", before=toggle_btn)
                toggle_btn.config(text="▼  Hide Model Details")
            _expanded[0] = not _expanded[0]

        toggle_btn = tk.Button(
            self._res_f, text="▶  Show Model Details (LR & KNN)",
            font=F["small"], fg=C["muted"], bg=C["bg"],
            activeforeground=C["text"], activebackground=C["bg"],
            relief="flat", cursor="hand2", anchor="w",
            command=_toggle,
        )
        toggle_btn.pack(anchor="w", pady=(6, 0))

        for model, price, plan in plans[:2]:
            _make_card(detail_frame, model, price, plan)

        PillBtn(self._res_f, text="Show Price Chart", color=C["muted"],
                command=lambda: hp._show_chart(
                    col, self._region_v.get(), year,
                    plans[0][1], plans[1][1], sav, dp)
                ).pack(anchor="w", pady=(14, 0))

    def refresh(self):
        sav = self._app.savings.balance
        if sav > 0:
            self._sav_e.delete(0, "end")
            self._sav_e.insert(0, f"{sav:.2f}")


# ══════════════════════════════════════════════════════════════════════════════
#  Finance Chat
# ══════════════════════════════════════════════════════════════════════════════

class FinanceChatPage(tk.Frame):
    """
    Retrieval-based chatbot with a reinforcement-learning feedback loop.

    RL loop
    -------
    1. TF-IDF finds the best-matching tip from a 200-pair dataset.
    2. User rates it 👍 (+1) or 👎 (-1)  →  reward signal.
    3. Rating + Q&A pair saved to SQLite  →  experience replay buffer.
    4. Next question: high-rated past answers get a similarity score boost,
       surfacing them more often  →  policy improvement over sessions.
    No API key, no model download — works fully offline.
    """

    # Class-level TF-IDF cache (built once, shared across instances)
    _tips: list        = []
    _vectorizer        = None
    _tip_matrix        = None

    def __init__(self, parent, app, on_close):
        super().__init__(parent, bg=C["sidebar"],
                         highlightthickness=1,
                         highlightbackground=C["border"])
        self._app      = app
        self._on_close = on_close
        self._history  = []
        self._last_q   = ""   # tracks the most recent user question for rating
        self._build()

    # ── UI ────────────────────────────────────────────────────────────────

    def _build(self):
        tk.Frame(self, bg=C["green"], height=3).pack(fill="x")

        hdr = tk.Frame(self, bg=C["card"], padx=14, pady=12)
        hdr.pack(fill="x")
        Lbl(hdr, "💬  Finance Chat", "h3", C["green"]).pack(side="left")
        tk.Button(
            hdr, text="✕", font=("Segoe UI", 7),
            bg=C["card"], fg=C["muted"],
            activebackground=C["card"], activeforeground=C["text"],
            relief="flat", cursor="hand2", bd=0,
            command=self._on_close,
        ).pack(side="right")
        Lbl(hdr, "200 financial tips · learns from your feedback",
            "small", C["muted"]).pack(anchor="w")

        self._chat = tk.Text(
            self, bg=C["bg"], fg=C["text"], font=F["body"],
            relief="flat", wrap="word", state="disabled",
            highlightthickness=0, padx=12, pady=12,
        )
        sb = ttk.Scrollbar(self, command=self._chat.yview)
        self._chat.config(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._chat.pack(fill="both", expand=True)

        self._chat.tag_config("you",    foreground=C["green"],  font=F["h3"])
        self._chat.tag_config("ai",     foreground=C["purple"], font=F["h3"])
        self._chat.tag_config("body",   foreground=C["text"],   font=F["body"])
        self._chat.tag_config("err",    foreground=C["red"],    font=F["small"])
        self._chat.tag_config("muted",  foreground=C["muted"],  font=F["small"])

        inp_f = tk.Frame(self, bg=C["card"], padx=12, pady=10)
        inp_f.pack(fill="x")
        self._entry = StyledEntry(inp_f, font=F["body"])
        self._entry.pack(fill="x", ipady=4, pady=(0, 8))
        self._entry.bind("<Return>", lambda _: self._send())
        row = tk.Frame(inp_f, bg=C["card"])
        row.pack(fill="x")
        self._send_btn = PillBtn(row, text="Send ➤", command=self._send)
        self._send_btn.pack(side="left")
        self._status = Lbl(row, "", "small", C["muted"])
        self._status.pack(side="left", padx=10)

        self._write_ai("Hey! I'm your personal finance assistant. "
                       "Ask me anything about budgeting, saving, or debt. "
                       "Rate my answers to help me improve over time!")

    # ── Text helpers ──────────────────────────────────────────────────────

    def _write(self, text, tag="body"):
        self._chat.config(state="normal")
        self._chat.insert("end", text, tag)
        self._chat.config(state="disabled")
        self._chat.see("end")

    @staticmethod
    def _make_avatar(parent) -> tk.Canvas:
        """Draw a small bot avatar using Canvas primitives."""
        S = 34
        cv = tk.Canvas(parent, width=S, height=S,
                       bg=C["bg"], highlightthickness=0)
        # Head circle
        cv.create_oval(1, 1, S - 1, S - 1, fill=C["card"], outline=C["green"], width=2)
        # Antenna stem
        cv.create_line(S // 2, 1, S // 2, 8, fill=C["green"], width=2)
        # Antenna tip
        cv.create_oval(S // 2 - 3, 0, S // 2 + 3, 6,
                       fill=C["amber"], outline="")
        # Eyes
        cv.create_oval(8,  13, 14, 19, fill=C["green"], outline="")
        cv.create_oval(20, 13, 26, 19, fill=C["green"], outline="")
        # Pupils
        cv.create_oval(10, 15, 12, 17, fill=C["bg"], outline="")
        cv.create_oval(22, 15, 24, 17, fill=C["bg"], outline="")
        # Mouth
        cv.create_arc(9, 19, 25, 30, start=200, extent=140,
                      style="arc", outline=C["green"], width=2)
        return cv

    def _write_ai(self, text):
        """Append an AI message with avatar header and embedded 👍/👎 buttons."""
        self._chat.config(state="normal")

        # Avatar + name row
        hdr = tk.Frame(self._chat, bg=C["bg"])
        self._make_avatar(hdr).pack(side="left", padx=(0, 7), anchor="center")
        tk.Label(hdr, text="PennyPath AI", font=F["h3"],
                 fg=C["purple"], bg=C["bg"]).pack(side="left", anchor="center")
        self._chat.window_create("end", window=hdr)
        self._chat.insert("end", "\n")

        self._chat.insert("end", f"{text}\n", "body")

        # Capture question at time of writing (not later via closure)
        question = self._last_q
        response = text

        fb = tk.Frame(self._chat, bg=C["bg"])
        Lbl(fb, "Helpful?", "small", C["muted"]).pack(side="left", padx=(0, 6))
        for icon, reward in (("👍", +1), ("👎", -1)):
            tk.Button(
                fb, text=icon, font=("Segoe UI", 10),
                bg=C["bg"], fg="#ffffff", activeforeground="#ffffff",
                relief="flat", cursor="hand2", bd=0,
                command=lambda q=question, r=response, v=reward, f=fb:
                    self._rate(q, r, v, f),
            ).pack(side="left", padx=2)

        self._chat.window_create("end", window=fb)
        self._chat.insert("end", "\n\n")
        self._chat.config(state="disabled")
        self._chat.see("end")

    def _rate(self, question, response, reward, fb_frame):
        """Save feedback (reward signal) and update the button UI."""
        if not self._app.current_user:
            return
        self._app.db.save_feedback(
            self._app.current_user["id"], question, response, reward
        )
        for w in fb_frame.winfo_children():
            w.destroy()
        label = "✓ Thanks — I'll do more of that!" if reward > 0 else "✓ Got it — I'll improve."
        Lbl(fb_frame, label, "small", C["green"] if reward > 0 else C["muted"]).pack(side="left")

    # ── RL: few-shot retrieval ─────────────────────────────────────────────

    def _get_few_shot_examples(self, current_question: str) -> list:
        """
        Experience replay: find past 👍 Q&A pairs similar to the current question.
        Uses TF-IDF cosine similarity — no extra dependencies needed.
        Returns up to 3 (question, response) pairs ordered by similarity.
        """
        if not self._app.current_user:
            return []
        past = self._app.db.get_positive_feedback(
            self._app.current_user["id"], limit=60
        )
        if not past:
            return []

        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity
            import numpy as np

            questions = [q for q, _ in past]
            corpus    = questions + [current_question]
            mat       = TfidfVectorizer(stop_words="english").fit_transform(corpus)
            sims      = cosine_similarity(mat[-1:], mat[:-1])[0]

            top = sorted(enumerate(sims), key=lambda x: x[1], reverse=True)[:3]
            return [(past[i][0], past[i][1]) for i, score in top if score > 0.08]
        except Exception:
            return []

    # ── Tips dataset ──────────────────────────────────────────────────────

    def _load_tips(self):
        """Load dataset and build TF-IDF index once (cached at class level)."""
        if FinanceChatPage._tips:
            return
        import json
        from sklearn.feature_extraction.text import TfidfVectorizer
        tips_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "financial_tips.json"
        )
        with open(tips_path, "r", encoding="utf-8") as f:
            FinanceChatPage._tips = json.load(f)
        questions = [t["question"] for t in FinanceChatPage._tips]
        FinanceChatPage._vectorizer = TfidfVectorizer(
            stop_words="english", ngram_range=(1, 2)
        )
        FinanceChatPage._tip_matrix = FinanceChatPage._vectorizer.fit_transform(questions)

    def _find_best_tip(self, question: str) -> tuple:
        """Return (answer, confidence_score) for the best matching tip."""
        from sklearn.metrics.pairwise import cosine_similarity
        import numpy as np

        self._load_tips()
        q_vec = FinanceChatPage._vectorizer.transform([question])
        sims  = cosine_similarity(q_vec, FinanceChatPage._tip_matrix)[0].copy()

        # RL boost: past 👍 answers get a score bump so they surface more often
        examples = self._get_few_shot_examples(question)
        for _, past_a in examples:
            for i, tip in enumerate(FinanceChatPage._tips):
                if tip["answer"] == past_a:
                    sims[i] = min(1.0, sims[i] + 0.15)
                    break

        best_idx = int(np.argmax(sims))
        return FinanceChatPage._tips[best_idx]["answer"], float(sims[best_idx])

    def _personalize(self, answer: str, question: str, score: float) -> str:
        """Append a brief personalized note based on the user's live financial data."""
        a       = self._app
        income  = a.wages.weekly_wage * 4
        surplus = income - a.necessary_total - a.nonnecessary_total
        q_l     = question.lower()

        note = ""
        if income > 0:
            if any(w in q_l for w in ("emergency", "fund", "buffer", "cushion")):
                target = (a.necessary_total + a.nonnecessary_total) * 3
                note = (
                    f"Your numbers: monthly expenses ${a.necessary_total + a.nonnecessary_total:,.0f} "
                    f"→ 3-month emergency fund target: ${target:,.0f}."
                )
            elif any(w in q_l for w in ("50/30/20", "budget", "budgeting", "rule")):
                note = (
                    f"Your 50/30/20 on ${income:,.0f}/mo: "
                    f"needs ${income * .5:,.0f} / wants ${income * .3:,.0f} / savings ${income * .2:,.0f}. "
                    f"Currently spending ${a.necessary_total:,.0f} on needs, "
                    f"${a.nonnecessary_total:,.0f} on wants."
                )
            elif any(w in q_l for w in ("save", "saving", "savings rate")):
                rate = (surplus / income * 100) if income > 0 else 0
                note = (
                    f"Your current savings rate: {rate:.0f}% "
                    f"(${surplus:,.0f}/mo surplus on ${income:,.0f} income)."
                )
            elif any(w in q_l for w in ("invest", "investing", "retirement", "401k", "ira", "compound")):
                monthly = min(surplus, 500) if surplus > 0 else 100
                future  = monthly * 12 * ((1.07 ** 10 - 1) / 0.07)
                note = (
                    f"With your ${surplus:,.0f}/mo surplus, investing "
                    f"${monthly:,.0f}/mo at 7%/yr grows to ~${future:,.0f} in 10 years."
                )

        if score < 0.12:
            answer = "I don't have an exact match, but here's something related:\n\n" + answer

        if note:
            answer += f"\n\n📊 {note}"

        return answer

    # ── Local retrieval call ──────────────────────────────────────────────

    def _send(self):
        msg = self._entry.get().strip()
        if not msg:
            return
        self._last_q = msg
        self._entry.delete(0, "end")
        self._write("You\n", "you")
        self._write(f"{msg}\n\n")
        self._send_btn.config(state="disabled")
        self._status.config(text="Searching…")
        threading.Thread(target=self._call_local, daemon=True).start()

    def _call_local(self):
        try:
            answer, score = self._find_best_tip(self._last_q)
            answer = self._personalize(answer, self._last_q, score)
            self._app.root.after(0, lambda r=answer: self._on_reply(r))
        except Exception as e:
            self._app.root.after(0, lambda m=str(e): self._on_error(m))

    def _on_reply(self, text):
        self._write_ai(text)
        self._send_btn.config(state="normal")
        self._status.config(text="")
        self._entry.focus()

    def _on_error(self, msg):
        self._write(f"Error: {msg}\n\n", "err")
        if self._history and self._history[-1]["role"] == "user":
            self._history.pop()
        self._send_btn.config(state="normal")
        self._status.config(text="")

    def refresh(self):
        pass


# ══════════════════════════════════════════════════════════════════════════════
#  Application root
# ══════════════════════════════════════════════════════════════════════════════

class PennyPathApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("PennyPath")
        self.root.geometry("1150x740")
        self.root.minsize(900, 620)
        self.root.configure(bg=C["bg"])
        self._apply_ttk_theme()

        # Backend state
        self.db          = Database()
        self.checking    = CheckingAccount()
        self.savings     = SavingsAccount()
        self.wages       = Wages()
        self.wage_acct   = WageAccount()
        self.expenses: list = []
        self.necessary_total    = 0.0
        self.nonnecessary_total = 0.0
        self.budget              = None
        self.advisor             = BudgetAdvisor()
        self.advisor.train()
        self.home_plan           = HomeSavingsPlan()
        self.current_user: dict | None = None

        self._main_frame: tk.Frame | None = None
        self._auth_frame = AuthScreen(self.root, self.db, self._on_login)
        self._auth_frame.pack(fill="both", expand=True)

    # ── TTK theme ─────────────────────────────────────────────────────────────
    def _apply_ttk_theme(self):
        st = ttk.Style()
        st.theme_use("clam")
        st.configure("TCombobox",
                      fieldbackground=C["input"], background=C["input"],
                      foreground=C["text"], bordercolor=C["border"],
                      arrowcolor=C["green"], selectbackground=C["green"],
                      selectforeground="#fff")
        st.map("TCombobox",
               fieldbackground=[("readonly", C["input"])],
               foreground=[("readonly", C["text"])])
        st.configure("Vertical.TScrollbar",
                      background=C["card"], troughcolor=C["bg"],
                      bordercolor=C["bg"], arrowcolor=C["muted"])

    # ── Auth ──────────────────────────────────────────────────────────────────
    def _on_login(self, user: dict):
        self.current_user = user
        self._load_session()
        self._auth_frame.pack_forget()
        self._build_main()

    def _logout(self):
        self.autosave()
        self.checking    = CheckingAccount()
        self.savings     = SavingsAccount()
        self.wages       = Wages()
        self.wage_acct   = WageAccount()
        self.expenses.clear()
        self.necessary_total = 0.0; self.nonnecessary_total = 0.0
        self.budget = None; self.current_user = None

        if self._main_frame:
            self._main_frame.pack_forget()
            self._main_frame.destroy()
            self._main_frame = None

        self._auth_frame = AuthScreen(self.root, self.db, self._on_login)
        self._auth_frame.pack(fill="both", expand=True)

    # ── Session ───────────────────────────────────────────────────────────────
    def _load_session(self):
        s = self.db.load_session(self.current_user["id"])
        self.savings.balance   = s["savings"]
        self.checking.balance  = s["checking"]
        self.wages.weekly_wage = s["wage"]
        self.expenses.clear()
        self.necessary_total = 0.0; self.nonnecessary_total = 0.0

        for cat, sub, name, amount, freq in s["expenses"]:
            cls = Needs if cat == "needs" else Wants
            exp = object.__new__(cls)
            exp.name = name; exp.ammt = amount
            exp.freq = freq; exp.subcategory = sub; exp.frm = ""
            self.expenses.append(exp)
            if cat == "needs":
                self.necessary_total += exp.monthly_amount()
            else:
                self.nonnecessary_total += exp.monthly_amount()

        if s["budget"] > 0:
            self.budget = Budget(self.checking.balance)
            self.budget.bd = s["budget"]

    def autosave(self):
        if not self.current_user:
            return
        self.db.save_session(
            self.savings.balance, self.checking.balance,
            self.wages.weekly_wage,
            self.budget.bd if self.budget else None,
            self.current_user["id"],
        )

    # ── Main shell ────────────────────────────────────────────────────────────
    def _build_main(self):
        self._main_frame = tk.Frame(self.root, bg=C["bg"])
        self._main_frame.pack(fill="both", expand=True)

        # Collapsed sidebar tab (shown when sidebar is hidden)
        self._sb_tab = tk.Frame(self._main_frame, bg=C["sidebar"], width=28)
        self._sb_tab.pack_propagate(False)
        tk.Button(
            self._sb_tab, text="▶", font=("Segoe UI", 9),
            bg=C["sidebar"], fg=C["muted"],
            activebackground=C["sidebar"], activeforeground=C["green"],
            relief="flat", cursor="hand2", bd=0,
            command=self._toggle_sidebar,
        ).pack(pady=20)

        self._sidebar_visible = True
        self._sidebar = Sidebar(
            self._main_frame,
            on_nav=self._navigate,
            on_logout=self._logout,
            username=self.current_user["username"],
            on_toggle=self._toggle_sidebar,
        )
        self._sidebar.pack(side="left", fill="y")

        self._content = tk.Frame(self._main_frame, bg=C["bg"])
        self._content.pack(side="left", fill="both", expand=True)

        self._pages: dict[str, tk.Frame] = {
            "dashboard": DashboardPage(self._content, self),
            "expenses":  ExpensesPage(self._content, self),
            "wages":     WagesPage(self._content, self),
            "afford":    AffordabilityPage(self._content, self),
            "advisor":   BudgetAIPage(self._content, self),
            "home":      HomePlanPage(self._content, self),
        }
        self._cur_page: str | None = None
        self._navigate("dashboard")

        # Chat panel (hidden by default, overlays the right side of content)
        self._chat_visible = False
        self._chat_panel = FinanceChatPage(
            self._content, self, on_close=self._toggle_chat
        )

        # Floating action button — bottom-right of content area
        self._fab = tk.Button(
            self._content,
            text="💬",
            font=("Segoe UI", 16),
            bg=C["green"], fg="#ffffff",
            activebackground="#16a34a", activeforeground="#ffffff",
            relief="flat", cursor="hand2",
            padx=14, pady=10,
            command=self._toggle_chat,
        )
        self._fab.place(relx=1.0, rely=1.0, anchor="se", x=-20, y=-20)
        self._fab.lift()

    def _toggle_sidebar(self):
        if self._sidebar_visible:
            self._sidebar.pack_forget()
            self._sb_tab.pack(side="left", fill="y", before=self._content)
            self._sidebar_visible = False
        else:
            self._sb_tab.pack_forget()
            self._sidebar.pack(side="left", fill="y", before=self._content)
            self._sidebar_visible = True

    def _navigate(self, key: str):
        if self._cur_page:
            self._pages[self._cur_page].pack_forget()
        self._pages[key].pack(fill="both", expand=True)
        self._pages[key].refresh()
        self._cur_page = key
        self._sidebar.set_active(key)

    def _toggle_chat(self):
        if self._chat_visible:
            self._chat_panel.place_forget()
            self._fab.place(relx=1.0, rely=1.0, anchor="se", x=-20, y=-20)
            self._fab.lift()
            self._chat_visible = False
        else:
            self._chat_panel.place(
                relx=1.0, rely=0.0, anchor="ne",
                relheight=1.0, width=360,
            )
            self._chat_panel.lift()
            self._fab.place_forget()
            self._chat_visible = True
            self._chat_panel._entry.focus()


# ══════════════════════════════════════════════════════════════════════════════
#  Entry point
# ══════════════════════════════════════════════════════════════════════════════

def main():
    root = tk.Tk()
    PennyPathApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
