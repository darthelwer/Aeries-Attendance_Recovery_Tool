import csv
import datetime
import hashlib
import json
import os
import sys
import traceback
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import pyodbc


BASE_DIR = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
CONFIG_FILE = os.path.join(BASE_DIR, "aeries_sql_config.json")
LOG_DIR = os.path.join(BASE_DIR, "Logs")

APP_NAME = "Attendance Recovery Tool"
APP_VERSION = "1.0.2"
GITHUB_URL = "https://github.com/darthelwer/Attendance-Recovery-In-Aeries"
ISSUES_URL = "https://github.com/darthelwer/Attendance-Recovery-In-Aeries/issues"
VENMO_HANDLE = "@darthelwer"
ACO_MAX_LENGTH = 50
REQUIRED_ODBC_DRIVER = "ODBC Driver 18 for SQL Server"
ODBC_DRIVER_DOWNLOAD_URL = "https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server"

DEFAULT_CONFIG = {
    "school_year": "25-26",
    "query_folder": "",
    "server_name": "",
    "driver": "{ODBC Driver 18 for SQL Server}",
    "username": "",
    "database_template": "DST{yy}000YourDistrict",
    "db_nickname": "",
    "attendance_recovery_absence_codes": [],
    "attendance_recovery_absence_code_scope": "district",
    "attendance_recovery_absence_code_signature": "",
    "attendance_recovery_ada_code": "M"
}

def normalize_odbc_driver_name(driver_name):
    return str(driver_name or "").strip().replace("{", "").replace("}", "")


def get_installed_odbc_drivers():
    try:
        return list(pyodbc.drivers())
    except Exception:
        return []


def has_required_odbc_driver(config_driver=None):
    required = normalize_odbc_driver_name(config_driver or REQUIRED_ODBC_DRIVER)
    installed = [normalize_odbc_driver_name(driver) for driver in get_installed_odbc_drivers()]
    return required in installed, required, installed


class MissingODBCDriverDialog(tk.Toplevel):
    def __init__(self, parent, required_driver, installed_drivers):
        super().__init__(parent)
        self.title("Missing ODBC Driver")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        main = ttk.Frame(self, padding=14)
        main.pack(fill="both", expand=True)

        ttk.Label(
            main,
            text="Microsoft ODBC Driver 18 for SQL Server was not found.",
            font=("TkDefaultFont", 10, "bold")
        ).pack(anchor="w", pady=(0, 8))

        message = (
            "This application cannot connect to Aeries SQL until the required SQL Server ODBC driver is installed.\n\n"
            f"Required driver: {required_driver}\n\n"
            "Install the driver, then restart this application."
        )
        ttk.Label(main, text=message, wraplength=460, justify="left").pack(anchor="w")

        if installed_drivers:
            ttk.Label(main, text="\nInstalled ODBC drivers found:", font=("TkDefaultFont", 9, "bold")).pack(anchor="w")
            shown = "\n".join(f"- {driver}" for driver in installed_drivers[:8])
            if len(installed_drivers) > 8:
                shown += f"\n- ...and {len(installed_drivers) - 8} more"
            ttk.Label(main, text=shown, wraplength=460, justify="left").pack(anchor="w")

        buttons = ttk.Frame(main)
        buttons.pack(fill="x", pady=(14, 0))
        ttk.Button(buttons, text="Close", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="Download Driver", command=self.open_download).pack(side="right")

        self.bind("<Escape>", lambda event: self.destroy())
        self.update_idletasks()
        self.center_on_parent(parent)

    def open_download(self):
        webbrowser.open(ODBC_DRIVER_DOWNLOAD_URL)

    def center_on_parent(self, parent):
        parent.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() // 2) - (self.winfo_reqwidth() // 2)
        y = parent.winfo_rooty() + (parent.winfo_height() // 2) - (self.winfo_reqheight() // 2)
        self.geometry(f"+{x}+{y}")


class StartupDiagnosticsDialog(tk.Toplevel):
    def __init__(self, parent, diagnostics):
        super().__init__(parent)
        self.title("Startup Diagnostics")
        self.geometry("620x420")
        self.minsize(540, 340)
        self.transient(parent)

        main = ttk.Frame(self, padding=12)
        main.pack(fill="both", expand=True)

        ttk.Label(main, text="Startup Diagnostics", font=("TkDefaultFont", 11, "bold")).pack(anchor="w", pady=(0, 8))

        tree_frame = ttk.Frame(main)
        tree_frame.pack(fill="both", expand=True)

        columns = ("Status", "Check", "Details")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=10)
        for col in columns:
            self.tree.heading(col, text=col)
        self.tree.column("Status", width=70, anchor="center")
        self.tree.column("Check", width=170, anchor="w")
        self.tree.column("Details", width=340, anchor="w")

        y_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=y_scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        for item in diagnostics:
            status_symbol = "OK" if item["ok"] else "WARN"
            self.tree.insert("", "end", values=(status_symbol, item["check"], item["details"]))

        buttons = ttk.Frame(main)
        buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(buttons, text="Close", command=self.destroy).pack(side="right")

        self.bind("<Escape>", lambda event: self.destroy())

class ToolTip:
    def __init__(self, widget, text_func):
        self.widget = widget
        self.text_func = text_func if callable(text_func) else lambda: text_func
        self.tip_window = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, event=None):
        if self.tip_window is not None:
            return
        text = self.text_func()
        if not text:
            return
        x = self.widget.winfo_rootx() + 18
        y = self.widget.winfo_rooty() + 22
        self.tip_window = tk.Toplevel(self.widget)
        self.tip_window.wm_overrideredirect(True)
        self.tip_window.wm_geometry(f"+{x}+{y}")
        tk.Label(
            self.tip_window,
            text=text,
            background="#fff8c6",
            relief="solid",
            borderwidth=1,
            padx=6,
            pady=2
        ).pack()

    def hide(self, event=None):
        if self.tip_window is not None:
            self.tip_window.destroy()
            self.tip_window = None


class ConnectionDot(tk.Canvas):
    COLORS = {
        "disconnected": "#c62828",
        "connected": "#2e7d32",
        "timeout": "#f9a825"
    }

    def __init__(self, parent, size=12):
        super().__init__(parent, width=size, height=size, highlightthickness=0)
        self.size = size
        self.dot = self.create_oval(2, 2, size - 2, size - 2, fill=self.COLORS["disconnected"], outline="")

    def set_state(self, state):
        self.itemconfigure(self.dot, fill=self.COLORS.get(state, self.COLORS["disconnected"]))


class ScrollableFrame(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self.inner.bind("<Configure>", lambda event: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.inner_window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.canvas.bind("<Configure>", self.on_canvas_configure)
        self.canvas.bind("<Enter>", self._bind_mousewheel)
        self.canvas.bind("<Leave>", self._unbind_mousewheel)
        self.inner.bind("<Enter>", self._bind_mousewheel)
        self.inner.bind("<Leave>", self._unbind_mousewheel)

    def on_canvas_configure(self, event):
        self.canvas.itemconfigure(self.inner_window, width=event.width)

    def _bind_mousewheel(self, event=None):
        self.canvas.bind_all("<MouseWheel>", self.on_mousewheel)
        self.canvas.bind_all("<Button-4>", self.on_mousewheel)
        self.canvas.bind_all("<Button-5>", self.on_mousewheel)

    def _unbind_mousewheel(self, event=None):
        self.canvas.unbind_all("<MouseWheel>")
        self.canvas.unbind_all("<Button-4>")
        self.canvas.unbind_all("<Button-5>")

    def on_mousewheel(self, event):
        try:
            if getattr(event, "num", None) == 4:
                self.canvas.yview_scroll(-1, "units")
            elif getattr(event, "num", None) == 5:
                self.canvas.yview_scroll(1, "units")
            else:
                self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except tk.TclError:
            pass


class PasswordDialog(tk.Toplevel):
    def __init__(self, parent, username=""):
        super().__init__(parent)
        self.title("Database Login")
        self.resizable(False, False)
        self.result = None
        self.transient(parent)
        self.grab_set()

        self.username_var = tk.StringVar(value=username)
        self.password_var = tk.StringVar()

        main = ttk.Frame(self, padding=12)
        main.pack(fill="both", expand=True)

        ttk.Label(main, text="Username:").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
        ttk.Entry(main, textvariable=self.username_var, width=38).grid(row=0, column=1, sticky="ew", pady=(0, 8))

        ttk.Label(main, text="Password:").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
        password_entry = ttk.Entry(main, textvariable=self.password_var, show="*", width=38)
        password_entry.grid(row=1, column=1, sticky="ew", pady=(0, 8))

        buttons = ttk.Frame(main)
        buttons.grid(row=2, column=0, columnspan=2, sticky="e", pady=(8, 0))
        ttk.Button(buttons, text="Cancel", command=self.cancel).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="Connect", command=self.submit).pack(side="right")

        main.columnconfigure(1, weight=1)
        self.bind("<Return>", lambda event: self.submit())
        self.bind("<Escape>", lambda event: self.cancel())
        self.update_idletasks()
        self.center_on_parent(parent)
        password_entry.focus_set()

    def center_on_parent(self, parent):
        parent.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() // 2) - (self.winfo_reqwidth() // 2)
        y = parent.winfo_rooty() + (parent.winfo_height() // 2) - (self.winfo_reqheight() // 2)
        self.geometry(f"+{x}+{y}")

    def submit(self):
        self.result = {
            "username": self.username_var.get().strip(),
            "password": self.password_var.get()
        }
        self.destroy()

    def cancel(self):
        self.result = None
        self.destroy()


class SettingsDialog(tk.Toplevel):
    def __init__(self, parent, config, school_year="25-26"):
        super().__init__(parent)
        self.title("Connection Configuration")
        self.resizable(False, False)
        self.result = None
        self.transient(parent)
        self.grab_set()
        self.school_year = school_year

        self.nickname_var = tk.StringVar(value=config.get("db_nickname", ""))
        self.server_var = tk.StringVar(value=config.get("server_name", ""))
        self.template_var = tk.StringVar(value=config.get("database_template", ""))
        self.username_var = tk.StringVar(value=config.get("username", ""))
        self.driver_var = tk.StringVar(value=config.get("driver", ""))
        self.preview_var = tk.StringVar()
        self.driver_status_var = tk.StringVar()

        main = ttk.Frame(self, padding=12)
        main.pack(fill="both", expand=True)

        display_frame = ttk.LabelFrame(main, text="Display", padding=10)
        display_frame.pack(fill="x", pady=(0, 10))
        self.add_labeled_entry(
            display_frame,
            0,
            "Database Display Name:",
            self.nickname_var,
            "Friendly short name shown in the title bar and status bar. Examples: FUESD, PUSD, MUSD."
        )

        aeries_frame = ttk.LabelFrame(main, text="Provided by Aeries", padding=10)
        aeries_frame.pack(fill="x", pady=(0, 10))
        self.add_labeled_entry(
            aeries_frame,
            0,
            "Server Name:",
            self.server_var,
            "SQL Server address provided by Aeries or your district's Aeries SQL access information."
        )
        self.add_labeled_entry(
            aeries_frame,
            1,
            "Database Name:",
            self.template_var,
            "Aeries SQL database naming pattern. Use {yy} for the starting year. Example: DST{yy}000YourDistrict."
        )
        ttk.Label(aeries_frame, text="Current Database:").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Label(aeries_frame, textvariable=self.preview_var, font=("TkDefaultFont", 9, "bold")).grid(row=2, column=1, sticky="w", pady=4)
        self.add_labeled_entry(
            aeries_frame,
            3,
            "Username:",
            self.username_var,
            "Your Aeries SQL username. Passwords are not saved and are requested when connecting."
        )
        aeries_frame.columnconfigure(1, weight=1)

        driver_frame = ttk.LabelFrame(main, text="Driver", padding=10)
        driver_frame.pack(fill="x", pady=(0, 10))
        self.add_labeled_entry(
            driver_frame,
            0,
            "Driver Name:",
            self.driver_var,
            "Usually {ODBC Driver 18 for SQL Server}. The driver must be installed on this computer."
        )
        ttk.Label(driver_frame, text="Driver Status:").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        status_frame = ttk.Frame(driver_frame)
        status_frame.grid(row=1, column=1, sticky="w", pady=4)
        ttk.Label(status_frame, textvariable=self.driver_status_var).pack(side="left")
        ttk.Button(status_frame, text="Download Driver", command=lambda: webbrowser.open(ODBC_DRIVER_DOWNLOAD_URL)).pack(side="left", padx=(12, 0))
        driver_frame.columnconfigure(1, weight=1)

        buttons = ttk.Frame(main)
        buttons.pack(fill="x", pady=(4, 0))
        ttk.Button(buttons, text="Cancel", command=self.cancel).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="Save", command=self.save).pack(side="right")

        self.template_var.trace_add("write", lambda *_: self.update_preview())
        self.driver_var.trace_add("write", lambda *_: self.update_driver_status())
        self.update_preview()
        self.update_driver_status()

        self.update_idletasks()
        self.center_on_parent(parent)

    def add_labeled_entry(self, parent, row, label_text, variable, tooltip):
        label = ttk.Label(parent, text=label_text)
        label.grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
        ToolTip(label, tooltip)
        entry = ttk.Entry(parent, textvariable=variable, width=54)
        entry.grid(row=row, column=1, sticky="ew", pady=4)
        ToolTip(entry, tooltip)
        return entry

    def update_preview(self):
        template = self.template_var.get().strip() or "DST{yy}000YourDistrict"
        yy = self.school_year.split("-")[0]
        try:
            self.preview_var.set(template.format(yy=yy))
        except Exception:
            self.preview_var.set("Invalid database name format")

    def update_driver_status(self):
        installed, required, _drivers = has_required_odbc_driver(self.driver_var.get())
        self.driver_status_var.set("✓ Installed" if installed else "✕ Not Installed")

    def center_on_parent(self, parent):
        parent.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() // 2) - (self.winfo_reqwidth() // 2)
        y = parent.winfo_rooty() + (parent.winfo_height() // 2) - (self.winfo_reqheight() // 2)
        self.geometry(f"+{x}+{y}")

    def save(self):
        self.result = {
            "server_name": self.server_var.get().strip(),
            "driver": self.driver_var.get().strip(),
            "username": self.username_var.get().strip(),
            "database_template": self.template_var.get().strip(),
            "db_nickname": self.nickname_var.get().strip(),
        }
        self.destroy()

    def cancel(self):
        self.result = None
        self.destroy()


class AttendanceCodeDialog(tk.Toplevel):
    def __init__(self, parent, absence_codes, selected_codes, ada_makeup_code="M"):
        super().__init__(parent)
        self.title("Attendance Recovery Configuration")
        self.geometry("560x640")
        self.minsize(520, 460)
        self.result = None
        self.transient(parent)
        self.grab_set()

        self.absence_codes = absence_codes
        self.selected_codes = set(str(code) for code in selected_codes)
        self.code_vars = {}
        self.ada_code_var = tk.StringVar(value=str(ada_makeup_code or "M").strip().upper()[:1] or "M")

        main = ttk.Frame(self, padding=12)
        main.pack(fill="both", expand=True)

        ttk.Label(
            main,
            text="Attendance Recovery Configuration",
            font=("TkDefaultFont", 11, "bold")
        ).pack(anchor="w")

        ada_frame = ttk.LabelFrame(main, text="ADA Make Up Code (ATT.ADA)", padding=10)
        ada_frame.pack(fill="x", pady=(10, 10))
        ttk.Label(
            ada_frame,
            text="The value that will be written into ATT.ADA when Attendance Recovery is uploaded.",
            wraplength=500
        ).pack(anchor="w", pady=(0, 6))
        row = ttk.Frame(ada_frame)
        row.pack(fill="x")
        ttk.Label(row, text="Code:").pack(side="left", padx=(0, 8))
        entry = ttk.Entry(row, textvariable=self.ada_code_var, width=4)
        entry.pack(side="left")
        ttk.Label(row, text='Default in Aeries is "M".').pack(side="left", padx=(10, 0))
        self.ada_code_var.trace_add("write", self.normalize_ada_code)

        caveat = (
            "Attendance codes below are pulled from the district-level ABS setup where ABS.SC = 0. "
            "Most districts push district-level attendance codes to all schools. If your district needs "
            "school-specific attendance code configuration, please contact the developer."
        )
        ttk.Label(main, text=caveat, wraplength=520, foreground="#555555").pack(anchor="w", pady=(0, 10))

        toolbar = ttk.Frame(main)
        toolbar.pack(fill="x", pady=(0, 6))
        ttk.Label(toolbar, text="Attendance Recovery Eligible for Recovery", font=("TkDefaultFont", 10, "bold")).pack(side="left")
        ttk.Button(toolbar, text="Select All", command=self.select_all).pack(side="right", padx=(8, 0))
        ttk.Button(toolbar, text="Clear All", command=self.clear_all).pack(side="right")

        list_frame = ttk.LabelFrame(main, text="District Attendance Recovery", padding=6)
        list_frame.pack(fill="both", expand=True)

        self.scroll = ScrollableFrame(list_frame)
        self.scroll.pack(fill="both", expand=True)

        if not absence_codes:
            ttk.Label(self.scroll.inner, text="No district-level ABS codes were found.").pack(anchor="w", padx=6, pady=6)
        else:
            for code in absence_codes:
                cd = str(code.get("CD", ""))
                ti = code.get("TI", "") or ""
                ab = code.get("AB", "") or ""
                ty = code.get("TY", "") or ""
                var = tk.BooleanVar(value=cd in self.selected_codes)
                self.code_vars[cd] = var
                label = f"{cd} - {ti}"
                if ab:
                    label += f" ({ab})"
                if ty not in (None, ""):
                    label += f"  Type: {ty}"
                ttk.Checkbutton(self.scroll.inner, text=label, variable=var).pack(anchor="w", padx=6, pady=2)

        buttons = ttk.Frame(main)
        buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(buttons, text="Cancel", command=self.cancel).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="Save", command=self.save).pack(side="right")

        self.update_idletasks()
        self.center_on_parent(parent)

    def normalize_ada_code(self, *args):
        value = self.ada_code_var.get().upper()[:1]
        if self.ada_code_var.get() != value:
            self.ada_code_var.set(value)

    def center_on_parent(self, parent):
        parent.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() // 2) - (self.winfo_width() // 2)
        y = parent.winfo_rooty() + (parent.winfo_height() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")

    def select_all(self):
        for var in self.code_vars.values():
            var.set(True)

    def clear_all(self):
        for var in self.code_vars.values():
            var.set(False)

    def save(self):
        ada_code = self.ada_code_var.get().strip().upper()[:1]
        if not ada_code:
            messagebox.showwarning("ADA Make Up Code Required", "Please enter the ADA Make Up Code (ATT.ADA).", parent=self)
            return

        selected = sorted(code for code, var in self.code_vars.items() if var.get())
        if not selected:
            if not messagebox.askyesno(
                "No Codes Selected",
                "No absence codes are selected. The tool will not be able to generate recovery records.\n\nSave anyway?",
                parent=self
            ):
                return
        self.result = {
            "attendance_recovery_absence_codes": selected,
            "attendance_recovery_absence_code_scope": "district",
            "attendance_recovery_absence_code_signature": build_absence_code_signature(self.absence_codes),
            "attendance_recovery_ada_code": ada_code
        }
        self.destroy()

    def cancel(self):
        self.result = None
        self.destroy()


class AboutDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("About Attendance Recovery Tool")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        main = ttk.Frame(self, padding=14)
        main.pack(fill="both", expand=True)

        ttk.Label(main, text=APP_NAME, font=("TkDefaultFont", 13, "bold")).pack(anchor="center")
        ttk.Label(main, text=f"Version {APP_VERSION}").pack(anchor="center", pady=(2, 12))

        about_text = (
            "Created by Adam Elwer\n"
            "Database Specialist\n"
            "Fallbrook Union Elementary School District\n\n"
            "This application automates California Attendance Recovery processing in Aeries.\n\n"
            "This software is not affiliated with or endorsed by Aeries Software."
        )
        ttk.Label(main, text=about_text, justify="center", wraplength=430).pack(anchor="center", pady=(0, 12))

        repo_frame = ttk.LabelFrame(main, text="GitHub Repository", padding=8)
        repo_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(repo_frame, text=GITHUB_URL, wraplength=430).pack(anchor="w")
        ttk.Button(repo_frame, text="Open GitHub", command=lambda: webbrowser.open(GITHUB_URL)).pack(anchor="e", pady=(6, 0))

        support_frame = ttk.LabelFrame(main, text="Support Development", padding=8)
        support_frame.pack(fill="x", pady=(0, 10))
        support_text = (
            "If this tool saved your district hours of manual work, consider supporting future development.\n\n"
            f"Buy me a Dr Pepper Zero: Venmo {VENMO_HANDLE}"
        )
        ttk.Label(support_frame, text=support_text, wraplength=430).pack(anchor="w")
        ttk.Button(support_frame, text="Copy Venmo", command=self.copy_venmo).pack(anchor="e", pady=(6, 0))

        buttons = ttk.Frame(main)
        buttons.pack(fill="x", pady=(4, 0))
        ttk.Button(buttons, text="Close", command=self.destroy).pack(side="right")

        self.update_idletasks()
        self.center_on_parent(parent)

    def center_on_parent(self, parent):
        parent.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() // 2) - (self.winfo_width() // 2)
        y = parent.winfo_rooty() + (parent.winfo_height() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")

    def copy_venmo(self):
        self.clipboard_clear()
        self.clipboard_append(VENMO_HANDLE)
        messagebox.showinfo("Copied", f"Copied {VENMO_HANDLE} to clipboard.", parent=self)


class Student:
    def __init__(self, student_id, grade, current_school, current_sn):
        self.ID = student_id
        self.GR = grade
        self.SCL = current_school
        self.SN = current_sn
        self.AR_Days = []
        self.ATT_Days = []
        self.ADA_Days = []
        self.AR_PreviousCount = 0
        self.AR_Keys = set()
        self.duplicate_ar_ignored = 0

    def add_AR(self, dt, tm, pg, scl):
        ar_key = (date_key(dt), int(tm), pg, scl)
        if ar_key in self.AR_Keys:
            self.duplicate_ar_ignored += 1
            return
        self.AR_Keys.add(ar_key)
        self.AR_Days.append([dt, int(tm), pg, scl])

    def add_ATT(self, dy, sc, sn):
        self.ATT_Days.append([dy, sc, sn])

    def add_ADA(self, dy, ada, adt, aco):
        self.ADA_Days.append([dy, ada, adt, aco])


def date_key(value):
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    return value


def display_date(value):
    if value is None:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%m/%d/%Y")
    return str(value)


def sql_date(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    return value


def school_year_start_from_label(label):
    start = label.split("-")[0]
    try:
        year = 2000 + int(start)
    except ValueError:
        year = datetime.date.today().year
    return datetime.date(year, 7, 1)


def full_day_minutes(grade):
    if grade in (-1, 0):
        return 180
    if grade in (1, 2, 3):
        return 230
    return 240


def round_down_to_60_min(minutes):
    return (int(minutes) // 60) * 60


def normalize_existing_ada_dates(aco_value):
    if not aco_value or ":" not in str(aco_value):
        return []
    raw = str(aco_value).split(":", 1)[1].strip()
    if not raw:
        return []
    values = []
    for piece in raw.split():
        parsed = None
        for fmt in ("%m/%d/%y", "%m/%d/%Y"):
            try:
                parsed = datetime.datetime.strptime(piece, fmt).date()
                break
            except ValueError:
                pass
        if parsed is not None:
            values.append(parsed)
    return values


def build_program_lookup(ats_sessions):
    return {
        (session["SC"], session["SE"]): session["NM"] + ": "
        for session in ats_sessions
    }


def build_program_info_lookup(ats_sessions):
    return {
        (session["SC"], session["SE"]): {
            "school_name": session.get("SchoolName", ""),
            "program_name": session.get("NM", ""),
        }
        for session in ats_sessions
    }


def get_program_name(program_lookup, school, program):
    return (
        program_lookup.get((school, program))
        or program_lookup.get((0, program))
        or "Unknown: "
    )


def build_absence_code_signature(absence_codes):
    normalized = []
    for code in absence_codes:
        normalized.append({
            "CD": str(code.get("CD", "")),
            "TI": str(code.get("TI", "")),
            "AB": str(code.get("AB", "")),
            "TY": str(code.get("TY", "")),
            "DTS": str(code.get("DTS", ""))
        })
    payload = json.dumps(sorted(normalized, key=lambda row: row["CD"]), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get_saved_absence_codes(config_data):
    codes = config_data.get("attendance_recovery_absence_codes", [])
    if not codes:
        return []
    return [str(code) for code in codes]


def get_saved_ada_makeup_code(config_data):
    code = str(config_data.get("attendance_recovery_ada_code", "M") or "M").strip().upper()
    return code[:1] if code else "M"


class AttendanceRecoveryEngine:
    def __init__(self, conn, school_year_start, log_func=None, absence_codes=None, ada_makeup_code="M", csv_mode="NEW"):
        self.conn = conn
        self.school_year_start = school_year_start
        self.log = log_func or (lambda message: None)
        self.absence_codes = [str(code) for code in (absence_codes or [])]
        self.ada_makeup_code = str(ada_makeup_code or "M").strip().upper()[:1] or "M"
        self.csv_mode = str(csv_mode or "NEW").strip().upper()

    def get_ats_sessions(self):
        cursor = self.conn.cursor()
        query = """
        SELECT
            ATS.SC,
            ISNULL(LOC.NM, 'Districtwide / No School') AS SchoolName,
            ATS.SE,
            ATS.NM AS SessionName
        FROM ATS
        LEFT JOIN LOC
            ON ATS.SC = LOC.CD
        WHERE ATS.DEL = 0
        ORDER BY SchoolName, ATS.NM
        """
        cursor.execute(query)
        sessions = []
        for row in cursor:
            sessions.append({
                "SC": row.SC,
                "SchoolName": row.SchoolName,
                "SE": row.SE,
                "NM": row.SessionName
            })
        return sessions

    def get_absence_codes(self):
        cursor = self.conn.cursor()
        query = """
        SELECT
            CD,
            TI,
            AB,
            TY,
            DEL,
            DTS
        FROM ABS
        WHERE SC = 0
          AND DEL = 0
        ORDER BY CD
        """
        cursor.execute(query)
        codes = []
        for row in cursor:
            codes.append({
                "CD": str(row.CD),
                "TI": row.TI,
                "AB": row.AB,
                "TY": row.TY,
                "DEL": row.DEL,
                "DTS": row.DTS
            })
        return codes

    def get_day_lookup(self):
        cursor = self.conn.cursor()
        query = """
        SELECT
            SC,
            DY,
            DT
        FROM DAY
        """
        cursor.execute(query)
        day_lookup = {}
        for row in cursor:
            day_lookup[(row.SC, row.DY)] = row.DT
        return day_lookup

    def load_students(self):
        students = {}
        self._get_ar(students)
        self._get_att(students)
        self._existing_ar(students)
        return students

    def _get_ar(self, students):
        cursor = self.conn.cursor()
        query = """
        SELECT
            ATD.ID,
            STU.GR,
            STU.SC,
            STU.SN,
            ATD.DT,
            ATD.TM,
            ATD.SE,
            ATD.SCL
        FROM ATD
        LEFT JOIN STU
            ON ATD.ID = STU.ID
        WHERE (STU.TG = '' OR (STU.TG <> '' AND STU.LD > ?))
            AND STU.DEL = 0
            AND ATD.DEL = 0
        ORDER BY ATD.ID, ATD.DT, ATD.SE, ATD.SQ
        """
        self.log("Reading supplemental attendance records...")
        cursor.execute(query, self.school_year_start)
        count = 0
        for row in cursor:
            student_id = row[0]
            if student_id not in students:
                students[student_id] = Student(row[0], row[1], row[2], row[3])
            students[student_id].add_AR(row[4], row[5], row[6], row[7])
            count += 1
        self.log(f"Supplemental attendance rows read: {count}")

    def _get_att(self, students):
        if not self.absence_codes:
            raise ValueError("No Attendance Recovery absence codes are selected. Open Config > Attendance Recovery.")

        cursor = self.conn.cursor()
        placeholders = ",".join("?" for _ in self.absence_codes)
        query = f"""
        SELECT
            STU.ID,
            ATT.DY,
            ATT.SC,
            ATT.SN,
            ATT.DT,
            ATT.AL,
            ATT.ADA,
            ATT.ADT,
            ATT.ACO
        FROM ATT
        LEFT JOIN STU
            ON ATT.SC = STU.SC AND ATT.SN = STU.SN
        WHERE (STU.TG = '' OR (STU.TG <> '' AND STU.LD > ?))
            AND STU.DEL = 0
            AND ATT.DEL = 0
            AND ATT.AL IN ({placeholders})
        ORDER BY STU.ID, ATT.DY
        """
        self.log("Reading absence records...")
        self.log("Using absence codes: " + ", ".join(self.absence_codes))
        cursor.execute(query, self.school_year_start, *self.absence_codes)
        count = 0
        for row in cursor:
            student_id = row[0]
            if student_id in students:
                if str(row[6] or "").upper() == self.ada_makeup_code:
                    students[student_id].add_ADA(row[1], row[6], row[7], row[8])
                    if self.csv_mode == "ALL":
                        students[student_id].add_ATT(row[1], row[2], row[3])
                else:
                    students[student_id].add_ATT(row[1], row[2], row[3])
            count += 1
        self.log(f"Absence rows read: {count}")

    def _existing_ar(self, students):
        for stu in students.values():
            if not stu.ADA_Days:
                continue
            stu.AR_PreviousCount = len(stu.ADA_Days)
            existing_dates = []
            for days in stu.ADA_Days:
                existing_dates.extend(normalize_existing_ada_dates(days[3]))
            stu.ADA_Days = existing_dates

    def build_output_records(self, selected_school_sessions, ats_sessions):
        program_lookup = build_program_lookup(ats_sessions)
        program_info_lookup = build_program_info_lookup(ats_sessions)
        day_lookup = self.get_day_lookup()
        students = self.load_students()
        output_records = []
        stats = {
            "students_loaded": len(students),
            "duplicate_ar_ignored": 0,
            "records_generated": 0,
            "students_with_output": 0,
            "duplicate_absence_dates_skipped": 0,
            "reused_ar_dates_skipped": 0,
            "existing_ada_skipped": 0,
        }

        self.log("Matching supplemental attendance to absences...")

        for stu in students.values():
            stats["duplicate_ar_ignored"] += stu.duplicate_ar_ignored
            if not stu.AR_Days or not stu.ATT_Days:
                continue

            full_ar_days = []
            partial_ar_days = []
            used_ar_dates = set()
            existing_ada_dates = set(date_key(d) for d in stu.ADA_Days)
            required_minutes = full_day_minutes(stu.GR)

            for ar_date, ar_min, ar_prog, ar_school in stu.AR_Days:
                ar_key = date_key(ar_date)

                if (ar_school, ar_prog) not in selected_school_sessions:
                    continue

                if self.csv_mode == "NEW" and ar_key in existing_ada_dates:
                    stats["existing_ada_skipped"] += 1
                    continue

                if ar_key in used_ar_dates:
                    stats["reused_ar_dates_skipped"] += 1
                    continue

                if int(ar_min) >= required_minutes:
                    used_ar_dates.add(ar_key)
                    program_info = program_info_lookup.get((ar_school, ar_prog), {})
                    program_label = get_program_name(program_lookup, ar_school, ar_prog)
                    date_side = display_date(ar_date)
                    full_ar_days.append({
                        "ADA": self.ada_makeup_code,
                        "ADT": sql_date(ar_date),
                        "ACO": program_label + date_side,
                        "AR_SCHOOL": ar_school,
                        "AR_SE": ar_prog,
                        "AR_SCHOOL_NAME": program_info.get("school_name", ""),
                        "AR_PROGRAM_NAME": program_info.get("program_name", program_label.rstrip(": ")),
                        "ACO_DATE_SIDE": date_side,
                    })
                    continue

                rounded_minutes = round_down_to_60_min(ar_min)
                if rounded_minutes <= 0:
                    continue

                partial_ar_days.append([ar_date, rounded_minutes, ar_prog, ar_school])

                total_min = sum(row[1] for row in partial_ar_days)
                if total_min < required_minutes:
                    continue

                date_texts = []
                last_date = None
                last_program = None
                last_school = None
                minutes_used = 0
                used_partial_keys = []

                while partial_ar_days and minutes_used < required_minutes:
                    par_date, par_min, par_prog, par_school = partial_ar_days.pop(0)
                    par_key = date_key(par_date)

                    if par_key in used_ar_dates:
                        stats["reused_ar_dates_skipped"] += 1
                        continue

                    minutes_used += par_min
                    used_partial_keys.append(par_key)
                    date_texts.append(display_date(par_date))
                    last_date = par_date
                    last_program = par_prog
                    last_school = par_school

                if minutes_used >= required_minutes:
                    for used_key in used_partial_keys:
                        used_ar_dates.add(used_key)
                    program_info = program_info_lookup.get((last_school, last_program), {})
                    program_label = get_program_name(program_lookup, last_school, last_program)
                    date_side = " ".join(date_texts)
                    full_ar_days.append({
                        "ADA": self.ada_makeup_code,
                        "ADT": sql_date(last_date),
                        "ACO": program_label + date_side,
                        "AR_SCHOOL": last_school,
                        "AR_SE": last_program,
                        "AR_SCHOOL_NAME": program_info.get("school_name", ""),
                        "AR_PROGRAM_NAME": program_info.get("program_name", program_label.rstrip(": ")),
                        "ACO_DATE_SIDE": date_side,
                    })

            ar_remaining = 10 if self.csv_mode == "ALL" else max(0, 10 - stu.AR_PreviousCount)
            written_att_dates = set()
            output_count = 0
            student_had_output = False

            for att_record, full_ar in zip(stu.ATT_Days, full_ar_days):
                if output_count >= ar_remaining:
                    break

                att_day, att_school, att_sn = att_record
                att_key = date_key(att_day)

                if att_key in written_att_dates:
                    stats["duplicate_absence_dates_skipped"] += 1
                    continue

                written_att_dates.add(att_key)
                output_count += 1
                student_had_output = True

                day_dt = day_lookup.get((att_school, att_day)) or day_lookup.get((0, att_day))

                output_records.append({
                    "STU_ID": stu.ID,
                    "GR": stu.GR,
                    "SC": att_school,
                    "SN": att_sn,
                    "DY": att_day,
                    "DY_DT": day_dt,
                    "ADA": full_ar["ADA"],
                    "ADT": full_ar["ADT"],
                    "ACO": full_ar["ACO"],
                    "AR_SCHOOL": full_ar.get("AR_SCHOOL"),
                    "AR_SE": full_ar.get("AR_SE"),
                    "AR_SCHOOL_NAME": full_ar.get("AR_SCHOOL_NAME", ""),
                    "AR_PROGRAM_NAME": full_ar.get("AR_PROGRAM_NAME", ""),
                    "ACO_DATE_SIDE": full_ar.get("ACO_DATE_SIDE", ""),
                })

            if student_had_output:
                stats["students_with_output"] += 1

        stats["records_generated"] = len(output_records)
        self.log(f"Generated {len(output_records)} output record(s).")
        return output_records, stats


def write_output_csv(filename, output_records):
    with open(filename, "w", newline="", encoding="utf-8-sig") as output_csv:
        writer = csv.writer(output_csv)
        writer.writerow([
            "STU.ID", "STU.GR", "STU.SC", "STU.SN",
            "ATT.DY", "ATT.DY(DT)", "ATT.ADA", "ATT.ADT", "ATT.ACO"
        ])
        for record in output_records:
            writer.writerow([
                record["STU_ID"],
                record["GR"],
                record["SC"],
                record["SN"],
                record["DY"],
                display_date(record.get("DY_DT")),
                record["ADA"],
                display_date(record["ADT"]),
                record["ACO"]
            ])


def safe_log_value(value):
    if value is None:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%m/%d/%Y")
    return str(value)


def format_record_for_log(record):
    if not record:
        return "<no record>"
    ordered_keys = [
        "STU_ID", "GR", "SC", "SN", "DY", "DY_DT",
        "ADA", "ADT", "ACO", "AR_SCHOOL", "AR_SE",
        "AR_SCHOOL_NAME", "AR_PROGRAM_NAME"
    ]
    lines = []
    for key in ordered_keys:
        if key in record:
            lines.append(f"{key}: {safe_log_value(record.get(key))}")
    for key in sorted(record.keys()):
        if key not in ordered_keys:
            lines.append(f"{key}: {safe_log_value(record.get(key))}")
    return "\n".join(lines)


class App:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_NAME} {APP_VERSION}")
        self.root.geometry("760x690")
        self.root.minsize(680, 560)

        self.conn = None
        self.connection_state = "disconnected"
        self.config_data = self.load_config()
        self.school_year_var = tk.StringVar(value=self.config_data.get("school_year", "25-26"))
        self.status_message_var = tk.StringVar(value="Ready")
        self.db_display_var = tk.StringVar()
        self.school_year_start_var = tk.StringVar(value=str(school_year_start_from_label(self.school_year_var.get())))

        self.ats_sessions = []
        self.program_vars = {}
        self.school_groups = {}
        self.last_output_records = []
        self.last_output_file = None
        self.last_stats = None
        self.last_csv_mode = "NEW"
        self.csv_mode_var = tk.StringVar(value="NEW")
        self.log_expanded = tk.BooleanVar(value=True)
        self.log_file_path = self.create_run_log_file()
        self.log_lines = []

        self.build_menu()
        self.build_ui()
        self.write_run_log_header()
        self.set_connection_state("disconnected", "Ready")
        self.root.after(300, self.run_startup_diagnostics)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def build_menu(self):
        self.menu_bar = tk.Menu(self.root)

        self.file_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.file_menu.add_command(label="Save Log As...", command=self.save_log_as)
        self.file_menu.add_separator()
        self.file_menu.add_command(label="Exit", command=self.on_close)
        self.menu_bar.add_cascade(label="File", menu=self.file_menu)

        self.connection_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.connection_menu.add_command(label="Connect", command=self.connect_to_db)
        self.connection_menu.add_command(label="Disconnect", command=self.disconnect_from_db)
        self.connection_menu.add_separator()
        self.connection_menu.add_command(label="Reload Supplemental Attendance Sessions", command=self.load_programs)
        self.menu_bar.add_cascade(label="Connection", menu=self.connection_menu)

        self.settings_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.settings_menu.add_command(label="Connection...", command=self.open_settings)
        self.settings_menu.add_command(label="Attendance Recovery...", command=self.open_attendance_codes)
        self.menu_bar.add_cascade(label="Config", menu=self.settings_menu)


        self.help_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.help_menu.add_command(label="Walkthrough / Help", command=self.show_walkthrough)
        self.help_menu.add_command(label="Startup Diagnostics", command=self.show_startup_diagnostics)
        self.help_menu.add_separator()
        self.help_menu.add_command(label="GitHub Repository", command=lambda: webbrowser.open(GITHUB_URL))
        self.help_menu.add_command(label="Report Issue / Request Feature", command=lambda: webbrowser.open(ISSUES_URL))
        self.help_menu.add_command(label="Support Development", command=self.show_support)
        self.help_menu.add_separator()
        self.help_menu.add_command(label="About", command=self.show_about)
        self.menu_bar.add_cascade(label="Help", menu=self.help_menu)

        self.root.config(menu=self.menu_bar)

    def build_ui(self):
        top_frame = ttk.Frame(self.root, padding=(8, 8, 8, 4))
        top_frame.pack(fill="x")

        ttk.Label(top_frame, text="School Year:").pack(side="left", padx=(0, 6))
        self.year_combo = ttk.Combobox(
            top_frame,
            textvariable=self.school_year_var,
            values=["24-25", "25-26", "26-27"],
            state="readonly",
            width=8
        )
        self.year_combo.pack(side="left")
        self.year_combo.bind("<<ComboboxSelected>>", self.on_year_changed)

        ttk.Label(top_frame, text="Year Start:").pack(side="left", padx=(16, 6))
        ttk.Label(top_frame, textvariable=self.school_year_start_var).pack(side="left")

        ttk.Button(top_frame, text="Connect", command=self.connect_to_db).pack(side="right", padx=(6, 0))

        main_pane = ttk.PanedWindow(self.root, orient="vertical")
        main_pane.pack(fill="both", expand=True, padx=8, pady=4)

        selection_frame = ttk.Frame(main_pane, padding=8)
        main_pane.add(selection_frame, weight=4)

        header = ttk.Frame(selection_frame)
        header.pack(fill="x", pady=(0, 6))
        ttk.Label(header, text="Schools / Supplemental Attendance Sessions", font=("TkDefaultFont", 10, "bold")).pack(side="left")
        ttk.Button(header, text="Select All", command=self.select_all_programs).pack(side="right", padx=(6, 0))
        ttk.Button(header, text="Clear All", command=self.clear_all_programs).pack(side="right")

        self.program_scroll = ScrollableFrame(selection_frame)
        self.program_scroll.pack(fill="both", expand=True)

        ttk.Separator(self.root, orient="horizontal").pack(fill="x", padx=8, pady=(4, 2))

        action_frame = ttk.Frame(self.root, padding=(8, 4, 8, 4))
        action_frame.pack(fill="x")

        mode_frame = ttk.LabelFrame(action_frame, text="CSV Mode", padding=(8, 4))
        mode_frame.pack(side="left", padx=(0, 10))
        ttk.Radiobutton(mode_frame, text="NEW Records Only", variable=self.csv_mode_var, value="NEW", command=self.on_csv_mode_changed).pack(anchor="w")
        ttk.Radiobutton(mode_frame, text="ALL Matching Records", variable=self.csv_mode_var, value="ALL", command=self.on_csv_mode_changed).pack(anchor="w")

        self.generate_button = ttk.Button(action_frame, text="Generate CSV", command=self.generate_csv, state="disabled")
        self.generate_button.pack(side="left")
        self.open_button = ttk.Button(action_frame, text="Open Last CSV", command=self.open_last_csv, state="disabled")
        self.open_button.pack(side="left", padx=(8, 0))
        self.upload_button = ttk.Button(action_frame, text="Upload to Aeries", command=self.upload_to_aeries, state="disabled")
        self.upload_button.pack(side="right")

        self.progress = ttk.Progressbar(self.root, mode="indeterminate")
        self.progress.pack(fill="x", padx=8, pady=(0, 4))

        self.log_frame = ttk.Frame(self.root, padding=(8, 4, 8, 4))
        self.log_frame.pack(fill="both", expand=False)
        log_header = ttk.Frame(self.log_frame)
        log_header.pack(fill="x")
        self.log_toggle_button = ttk.Button(log_header, text="▼ Log", command=self.toggle_log)
        self.log_toggle_button.pack(side="left", anchor="w")
        ttk.Button(log_header, text="Save Log", command=self.save_log_as).pack(side="right")
        self.log_text = tk.Text(self.log_frame, height=8, wrap="word")
        self.log_text.pack(fill="both", expand=True)

        self.build_status_bar()
        self.show_empty_program_message("Connect to database to load Supplemental Attendance Sessions.")


    def toggle_log(self):
        if self.log_expanded.get():
            self.log_text.pack_forget()
            self.log_toggle_button.config(text="▶ Log")
            self.log_expanded.set(False)
        else:
            self.log_text.pack(fill="both", expand=True)
            self.log_toggle_button.config(text="▼ Log")
            self.log_expanded.set(True)

    def on_csv_mode_changed(self):
        self.upload_button.config(state="disabled")
        self.last_output_records = []
        self.last_output_file = None
        self.last_stats = None
        self.last_csv_mode = self.csv_mode_var.get().upper()
        mode_text = "NEW Records Only" if self.last_csv_mode == "NEW" else "ALL Matching Records"
        self.set_connection_state(self.connection_state, f"CSV mode set to {mode_text}")

    def set_busy(self, busy=True):
        if busy:
            for widget in [self.generate_button, self.open_button, self.upload_button]:
                try:
                    widget.config(state="disabled")
                except Exception:
                    pass
            self.progress.start(10)
            self.root.config(cursor="watch")
        else:
            self.progress.stop()
            self.root.config(cursor="")
            self.generate_button.config(state="normal" if self.connection_state == "connected" and self.program_vars else "disabled")
            self.open_button.config(state="normal" if self.last_output_file else "disabled")
            self.upload_button.config(state="normal" if self.last_output_records and self.last_csv_mode == "NEW" else "disabled")
        self.root.update_idletasks()

    def show_walkthrough(self):
        win = tk.Toplevel(self.root)
        win.title("Attendance Recovery Walkthrough")
        win.geometry("720x560")
        win.minsize(620, 460)
        main = ttk.Frame(win, padding=12)
        main.pack(fill="both", expand=True)
        ttk.Label(main, text="Attendance Recovery Tool Walkthrough", font=("TkDefaultFont", 12, "bold")).pack(anchor="w", pady=(0, 8))
        text = tk.Text(main, wrap="word", height=24)
        text.pack(fill="both", expand=True)
        help_text = """
1. Config > Connection
   Enter the values provided by Aeries: Server Name, Database Name, and Username.
   Database Display Name is only a short label shown in the app, such as FUESD.
   Database Name can use {yy}; for school year 25-26, {yy} becomes 25.

2. Connection > Connect
   Connect to the Aeries SQL database. Passwords are not saved.

3. Config > Attendance Recovery
   Set the ADA Make Up Code (ATT.ADA). The Aeries default is M.
   Select which attendance codes are eligible for recovery. These are read from ABS where SC = 0.

4. Select Schools / Supplemental Attendance Sessions
   Choose the Supplemental Attendance sessions to include. Choices are not remembered on purpose so each run is reviewed.

5. Choose CSV Mode
   NEW Records Only excludes records already applied to ATT and is the mode used for upload.
   ALL Matching Records is for audit/review only. Upload is disabled in ALL mode.

6. Generate CSV
   Review the CSV before uploading. The tool also validates ATT.ACO length before creating the file.

7. Upload to Aeries
   Upload uses a SQL transaction. If any record fails or cannot be matched to ATT, all changes are rolled back.

8. Logs
   The log records configuration, selections, CSV path, upload results, warnings, and rollback details.
""".strip()
        text.insert("1.0", help_text)
        text.config(state="disabled")
        buttons = ttk.Frame(main)
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="Close", command=win.destroy).pack(side="right")
    def build_status_bar(self):
        status_frame = ttk.Frame(self.root, relief="sunken", padding=(5, 2))
        status_frame.pack(side="bottom", fill="x")
        self.status_connection_dot = ConnectionDot(status_frame, size=12)
        self.status_connection_dot.pack(side="left", padx=(0, 8))
        ToolTip(self.status_connection_dot, self.get_connection_tooltip)
        ttk.Label(status_frame, textvariable=self.status_message_var, anchor="center").pack(side="left", fill="x", expand=True)
        self.db_status_label = ttk.Label(status_frame, textvariable=self.db_display_var, anchor="e")
        self.db_status_label.pack(side="right", padx=(8, 0))
        ToolTip(self.db_status_label, self.get_database_name)

    def load_config(self):
        config = DEFAULT_CONFIG.copy()

        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                config.update(loaded)
            except Exception as e:
                messagebox.showwarning(
                    "Config File Error",
                    f"Could not read aeries_sql_config.json.\n\n"
                    f"The app will continue with blank/default settings.\n\n{e}"
                )
            return config

        create_file = messagebox.askyesno(
            "Create Config File?",
            "aeries_sql_config.json was not found.\n\n"
            "Would you like this app to create a blank config file now?"
        )

        if create_file:
            try:
                with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(config, f, indent=4)
                messagebox.showinfo(
                    "Config File Created",
                    f"Created blank config file:\n{CONFIG_FILE}\n\n"
                    "Open Config > Connection to enter your district connection information."
                )
            except Exception as e:
                messagebox.showerror("Config File Error", f"Could not create config file:\n\n{e}")
        else:
            messagebox.showwarning(
                "Config Required",
                "The app can open, but you will need a valid config file or connection settings before connecting."
            )

        return config

    def save_config(self):
        self.config_data["school_year"] = self.school_year_var.get()
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.config_data, f, indent=4)

    def get_database_name(self):
        school_year = self.school_year_var.get()
        start_year = school_year.split("-")[0]
        template = self.config_data.get("database_template", "DST{yy}000YourDistrict")
        return template.format(yy=start_year)

    def get_database_short_name(self):
        db_name = self.get_database_name()
        if len(db_name) >= 8 and db_name.startswith("DST"):
            return db_name[:8]
        return db_name

    def get_database_display(self):
        nickname = self.config_data.get("db_nickname", "").strip()
        db_label = nickname if nickname else self.get_database_short_name()
        return f"{db_label} | {self.school_year_var.get()}"

    def get_connection_tooltip(self):
        if self.connection_state == "connected":
            return "Connected"
        if self.connection_state == "timeout":
            return "Connection timed out"
        return "Not connected"

    def create_run_log_file(self):
        try:
            os.makedirs(LOG_DIR, exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H-%M-%S")
            return os.path.join(LOG_DIR, f"Attendance Recovery {timestamp}.log")
        except Exception:
            return None

    def write_run_log_header(self):
        self.log_block(
            "APPLICATION START",
            f"{APP_NAME}\nVersion: {APP_VERSION}\nStarted: {datetime.datetime.now().strftime('%m/%d/%Y %I:%M:%S %p')}\nConfig: {CONFIG_FILE}"
        )

    def log_message(self, message):
        line = f"{datetime.datetime.now().strftime('%H:%M:%S')}  {message}"
        self.log_lines.append(line)
        try:
            self.log_text.insert("end", line + "\n")
            self.log_text.see("end")
        except Exception:
            pass
        if self.log_file_path:
            try:
                with open(self.log_file_path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except Exception:
                pass
        self.root.update_idletasks()

    def log_block(self, title, body=""):
        self.log_message("=" * 60)
        self.log_message(title)
        if body:
            for line in str(body).splitlines():
                self.log_message(line)
        self.log_message("=" * 60)

    def save_log_as(self):
        default_name = f"Attendance Recovery Log {datetime.date.today().strftime('%Y-%m-%d')}.log"
        filename = filedialog.asksaveasfilename(
            title="Save Log As",
            defaultextension=".log",
            filetypes=[("Log Files", "*.log"), ("Text Files", "*.txt"), ("All Files", "*.*")],
            initialfile=default_name
        )
        if not filename:
            return
        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write("\n".join(self.log_lines))
                f.write("\n")
            messagebox.showinfo("Log Saved", f"Log saved to:\n{filename}")
        except Exception as e:
            messagebox.showerror("Save Log Error", str(e))

    def set_window_title(self):
        if self.connection_state == "connected":
            nickname = self.config_data.get("db_nickname", "").strip()
            label = nickname if nickname else self.get_database_short_name()
            self.root.title(f"{APP_NAME} {APP_VERSION} - {label}")
        else:
            self.root.title(f"{APP_NAME} {APP_VERSION}")

    def set_connection_state(self, state, message=None):
        self.connection_state = state
        self.status_connection_dot.set_state(state)
        self.db_display_var.set(self.get_database_display())
        if message is not None:
            self.status_message_var.set(message)
        self.set_window_title()
        self.generate_button.config(state="normal" if state == "connected" and self.ats_sessions else "disabled")

    def is_connection_config_complete(self):
        missing = []

        for key, label in [
            ("server_name", "Server Name"),
            ("driver", "Driver"),
            ("username", "Username"),
            ("database_template", "Database Name"),
        ]:
            if not self.config_data.get(key, "").strip():
                missing.append(label)

        if self.config_data.get("database_template", "") == "DST{yy}000YourDistrict":
            missing.append("District-specific Database Name")

        if missing:
            messagebox.showwarning(
                "Connection Settings Needed",
                "Please complete these settings before connecting:\n\n"
                + "\n".join(f"- {item}" for item in missing)
                + "\n\nOpen Config > Connection."
            )
            self.open_settings()
            return False

        return True

    def collect_startup_diagnostics(self):
        diagnostics = []

        config_exists = os.path.exists(CONFIG_FILE)
        diagnostics.append({
            "ok": config_exists,
            "check": "Config file",
            "details": CONFIG_FILE if config_exists else "aeries_sql_config.json was not found"
        })

        required_keys = ["server_name", "driver", "username", "database_template"]
        missing_keys = [key for key in required_keys if not self.config_data.get(key, "").strip()]
        default_template = self.config_data.get("database_template", "") == "DST{yy}000YourDistrict"
        diagnostics.append({
            "ok": not missing_keys and not default_template,
            "check": "Connection settings",
            "details": "Complete" if not missing_keys and not default_template else "Needs review: " + ", ".join(missing_keys + (["database_template"] if default_template else []))
        })

        driver_ok, required_driver, installed_drivers = has_required_odbc_driver(self.config_data.get("driver"))
        diagnostics.append({
            "ok": driver_ok,
            "check": "ODBC Driver",
            "details": f"Found {required_driver}" if driver_ok else f"Missing {required_driver}"
        })

        selected_codes = get_saved_absence_codes(self.config_data)
        diagnostics.append({
            "ok": bool(selected_codes),
            "check": "Absence codes",
            "details": ", ".join(selected_codes) if selected_codes else "No Attendance Recovery absence codes selected"
        })

        diagnostics.append({
            "ok": True,
            "check": "Application version",
            "details": APP_VERSION
        })

        return diagnostics, driver_ok, required_driver, installed_drivers

    def run_startup_diagnostics(self):
        diagnostics, driver_ok, required_driver, installed_drivers = self.collect_startup_diagnostics()

        for item in diagnostics:
            prefix = "OK" if item["ok"] else "WARN"
            self.log_message(f"Startup check - {prefix}: {item['check']} - {item['details']}")

        if not driver_ok:
            self.set_connection_state("disconnected", "Missing ODBC Driver")
            MissingODBCDriverDialog(self.root, required_driver, installed_drivers)
        else:
            self.set_connection_state(self.connection_state, "Startup checks complete")

    def show_startup_diagnostics(self):
        diagnostics, driver_ok, required_driver, installed_drivers = self.collect_startup_diagnostics()
        StartupDiagnosticsDialog(self.root, diagnostics)
        if not driver_ok:
            MissingODBCDriverDialog(self.root, required_driver, installed_drivers)

    def connect_to_db(self):
        if not self.is_connection_config_complete():
            return

        driver_ok, required_driver, installed_drivers = has_required_odbc_driver(self.config_data.get("driver"))
        if not driver_ok:
            self.set_connection_state("disconnected", "Missing ODBC Driver")
            MissingODBCDriverDialog(self.root, required_driver, installed_drivers)
            return

        dialog = PasswordDialog(self.root, username=self.config_data.get("username", ""))
        self.root.wait_window(dialog)
        if not dialog.result:
            self.set_connection_state(self.connection_state, "Connection cancelled")
            return

        username = dialog.result["username"]
        password = dialog.result["password"]
        if not username:
            messagebox.showwarning("Missing Username", "Please enter a username.")
            return

        connection_string = (
            f"DRIVER={self.config_data.get('driver', '')};"
            f"SERVER={self.config_data.get('server_name', '')};"
            f"DATABASE={self.get_database_name()};"
            f"UID={username};"
            f"PWD={password};"
            "Encrypt=yes;"
            "TrustServerCertificate=yes;"
        )

        try:
            self.close_connection()
            self.conn = pyodbc.connect(connection_string)
            self.config_data["username"] = username
            self.save_config()
            self.set_connection_state("connected", "Connected")
            self.log_message("Connected to database.")
            self.check_attendance_code_config()
            self.load_programs()
        except Exception as e:
            self.conn = None
            self.set_connection_state("disconnected", "Connection failed")
            error_text = str(e)
            if "data source name not found" in error_text.lower() or "driver" in error_text.lower():
                driver_ok, required_driver, installed_drivers = has_required_odbc_driver(self.config_data.get("driver"))
                if not driver_ok:
                    MissingODBCDriverDialog(self.root, required_driver, installed_drivers)
                    return
            messagebox.showerror("Connection Error", error_text)

    def disconnect_from_db(self):
        self.close_connection()
        self.ats_sessions = []
        self.clear_program_area()
        self.show_empty_program_message("Connect to database to load Supplemental Attendance Sessions.")
        self.set_connection_state("disconnected", "Disconnected")
        self.generate_button.config(state="disabled")
        self.upload_button.config(state="disabled")

    def close_connection(self):
        if self.conn is not None:
            try:
                self.conn.close()
            except Exception:
                pass
            self.conn = None

    def is_connection_alive(self):
        if self.conn is None:
            return False
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            return True
        except Exception:
            self.close_connection()
            self.set_connection_state("timeout", "Connection timed out. Please reconnect.")
            return False

    def on_year_changed(self, event=None):
        self.school_year_start_var.set(str(school_year_start_from_label(self.school_year_var.get())))
        self.close_connection()
        self.save_config()
        self.ats_sessions = []
        self.clear_program_area()
        self.show_empty_program_message("School year changed. Reconnect to load Supplemental Attendance Sessions.")
        self.set_connection_state("disconnected", "School year changed. Reconnect required.")
        self.generate_button.config(state="disabled")
        self.upload_button.config(state="disabled")

    def open_settings(self):
        dialog = SettingsDialog(self.root, self.config_data, self.school_year_var.get())
        self.root.wait_window(dialog)
        if not dialog.result:
            return
        self.config_data.update(dialog.result)
        self.save_config()
        self.close_connection()
        self.ats_sessions = []
        self.clear_program_area()
        self.show_empty_program_message("Configuration saved. Reconnect to load Supplemental Attendance Sessions.")
        self.set_connection_state("disconnected", "Configuration saved. Reconnect required.")

    def fetch_district_absence_codes(self):
        engine = AttendanceRecoveryEngine(
            self.conn,
            school_year_start_from_label(self.school_year_var.get()),
            self.log_message,
            get_saved_absence_codes(self.config_data),
            get_saved_ada_makeup_code(self.config_data),
            self.csv_mode_var.get() if hasattr(self, "csv_mode_var") else "NEW"
        )
        return engine.get_absence_codes()

    def open_attendance_codes(self):
        if not self.is_connection_alive():
            messagebox.showwarning(
                "Connection Required",
                "Please connect to the database before configuring attendance codes."
            )
            return

        try:
            absence_codes = self.fetch_district_absence_codes()
        except Exception as e:
            messagebox.showerror("Attendance Recovery Error", str(e))
            self.log_message(f"Could not load attendance codes: {e}")
            return

        dialog = AttendanceCodeDialog(
            self.root,
            absence_codes,
            get_saved_absence_codes(self.config_data),
            get_saved_ada_makeup_code(self.config_data)
        )
        self.root.wait_window(dialog)

        if not dialog.result:
            return

        self.config_data.update(dialog.result)
        self.save_config()
        self.log_message("Attendance Recovery absence code selections saved.")
        self.set_connection_state(self.connection_state, "Attendance Recovery settings saved")

    def check_attendance_code_config(self):
        try:
            absence_codes = self.fetch_district_absence_codes()
            current_signature = build_absence_code_signature(absence_codes)
            saved_signature = self.config_data.get("attendance_recovery_absence_code_signature", "")
            selected_codes = get_saved_absence_codes(self.config_data)

            if not selected_codes:
                message = (
                    "No Attendance Recovery absence codes are selected.\n\n"
                    "Open the Attendance Recovery settings now?"
                )
            elif saved_signature != current_signature:
                message = (
                    "District-level ABS attendance codes have changed since the last review.\n\n"
                    "Please review your Attendance Recovery absence code selections.\n\n"
                    "Open Attendance Recovery settings now?"
                )
            else:
                self.log_message("Attendance code selections are current.")
                return

            if messagebox.askyesno("Review Attendance Recovery", message):
                dialog = AttendanceCodeDialog(self.root, absence_codes, selected_codes, get_saved_ada_makeup_code(self.config_data))
                self.root.wait_window(dialog)
                if dialog.result:
                    self.config_data.update(dialog.result)
                    self.save_config()
                    self.log_message("Attendance Recovery absence code selections saved.")
            else:
                self.log_message("Attendance code review was skipped.")
        except Exception as e:
            self.log_message(f"Attendance code check failed: {e}")
            messagebox.showwarning(
                "Attendance Code Check Failed",
                f"The tool could not check district-level ABS attendance codes.\n\n{e}"
            )

    def clear_program_area(self):
        for widget in self.program_scroll.inner.winfo_children():
            widget.destroy()
        self.program_vars = {}
        self.school_groups = {}

    def show_empty_program_message(self, message):
        ttk.Label(self.program_scroll.inner, text=message).pack(anchor="w", padx=6, pady=6)

    def load_programs(self):
        if not self.is_connection_alive():
            messagebox.showwarning("Connection Required", "Please connect to the database first.")
            return
        try:
            engine = AttendanceRecoveryEngine(
                self.conn,
                school_year_start_from_label(self.school_year_var.get()),
                self.log_message,
                get_saved_absence_codes(self.config_data)
            )
            self.ats_sessions = engine.get_ats_sessions()
            self.render_programs()
            self.set_connection_state("connected", f"Loaded {len(self.ats_sessions)} Supplemental Attendance Session(s)")
        except Exception as e:
            messagebox.showerror("Load Supplemental Attendance Sessions Error", str(e))
            self.log_message(f"Load Supplemental Attendance Sessions failed: {e}")

    def render_programs(self):
        self.clear_program_area()
        if not self.ats_sessions:
            self.show_empty_program_message("No Supplemental Attendance Sessions found.")
            self.generate_button.config(state="disabled")
            return

        schools = {}
        for session in self.ats_sessions:
            schools.setdefault(session["SchoolName"], []).append(session)
        for school in schools:
            schools[school] = sorted(schools[school], key=lambda row: row["NM"])
        self.school_groups = schools

        for school_name in sorted(schools.keys()):
            group = ttk.LabelFrame(self.program_scroll.inner, text=school_name, padding=6)
            group.pack(fill="x", padx=4, pady=5)

            top = ttk.Frame(group)
            top.pack(fill="x", pady=(0, 3))
            ttk.Label(top, text=f"Sessions Available: {len(schools[school_name])}").pack(side="left")
            ttk.Button(top, text="All", width=8, command=lambda s=school_name: self.set_school_programs(s, True)).pack(side="right", padx=(4, 0))
            ttk.Button(top, text="None", width=8, command=lambda s=school_name: self.set_school_programs(s, False)).pack(side="right")

            for session in schools[school_name]:
                var = tk.BooleanVar(value=False)
                key = (session["SC"], session["SE"])
                self.program_vars[key] = var
                text = session["NM"]
                ttk.Checkbutton(group, text=text, variable=var).pack(anchor="w", padx=18, pady=1)

        self.generate_button.config(state="normal" if self.connection_state == "connected" else "disabled")

    def set_school_programs(self, school_name, value):
        for session in self.school_groups.get(school_name, []):
            key = (session["SC"], session["SE"])
            if key in self.program_vars:
                self.program_vars[key].set(value)

    def select_all_programs(self):
        for var in self.program_vars.values():
            var.set(True)

    def clear_all_programs(self):
        for var in self.program_vars.values():
            var.set(False)

    def get_selected_sessions(self):
        return {key for key, var in self.program_vars.items() if var.get()}

    def show_about(self):
        AboutDialog(self.root)

    def show_support(self):
        messagebox.showinfo(
            "Support Development",
            "If this tool saved your district hours of manual work, consider supporting future development.\n\n"
            f"Buy me a Dr Pepper Zero: Venmo {VENMO_HANDLE}"
        )

    def validate_aco_lengths(self, output_records):
        problems = []
        for record in output_records:
            aco = str(record.get("ACO", ""))
            if len(aco) <= ACO_MAX_LENGTH:
                continue

            date_side = str(record.get("ACO_DATE_SIDE", ""))
            # The tool builds ACO as: ATS.NM + ': ' + date_side.
            max_program_name_length = ACO_MAX_LENGTH - len(date_side) - 2
            if max_program_name_length < 0:
                max_program_name_length = 0

            problems.append({
                "school_name": record.get("AR_SCHOOL_NAME") or "Unknown School",
                "school_code": record.get("AR_SCHOOL"),
                "session": record.get("AR_SE"),
                "program_name": record.get("AR_PROGRAM_NAME") or "Unknown Program",
                "aco_length": len(aco),
                "max_program_name_length": max_program_name_length,
                "date_side": date_side,
                "aco": aco,
            })

        if not problems:
            return True

        grouped = {}
        for problem in problems:
            key = (
                problem["school_name"],
                problem["school_code"],
                problem["session"],
                problem["program_name"],
                problem["max_program_name_length"],
            )
            grouped.setdefault(key, 0)
            grouped[key] += 1

        lines = [
            f"ATT.ACO is limited to {ACO_MAX_LENGTH} characters in Aeries.",
            "",
            "The CSV was not created because one or more Supplemental Attendance program names are too long once the AR date list is added.",
            "",
            "Please shorten these ATS Supplemental Attendance session names, then run the tool again:",
            "",
        ]

        for (school_name, school_code, session, program_name, max_len), count in sorted(grouped.items()):
            lines.append(f"School: {school_name} (SC {school_code})")
            lines.append(f"Session SE: {session}")
            lines.append(f"Current Program Name: {program_name}")
            lines.append(f"Max Program Name Length for affected rows: {max_len} character(s)")
            lines.append(f"Affected output row(s): {count}")
            lines.append("")

        messagebox.showerror("ATT.ACO Too Long", "\n".join(lines))
        self.log_message("CSV blocked: one or more ATT.ACO values would exceed 50 characters.")
        return False

    def generate_csv(self):
        if not self.is_connection_alive():
            messagebox.showwarning("Connection Required", "Please reconnect and try again.")
            return
        selected = self.get_selected_sessions()
        if not selected:
            messagebox.showwarning("No Sessions Selected", "Please select at least one Supplemental Attendance Session.")
            return

        if not get_saved_absence_codes(self.config_data):
            messagebox.showwarning(
                "No Attendance Recovery Selected",
                "No Attendance Recovery absence codes are selected.\n\nOpen Config > Attendance Recovery before generating the CSV."
            )
            return

        csv_mode = self.csv_mode_var.get().upper()
        today_text = datetime.date.today().strftime("%Y-%m-%d")
        filename = filedialog.asksaveasfilename(
            title="Save Attendance Recovery Audit CSV",
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
            initialfile=f"Attendance Recovery {today_text} ({csv_mode}).csv"
        )
        if not filename:
            self.set_connection_state(self.connection_state, "CSV generation cancelled")
            return

        try:
            self.set_busy(True)
            self.log_block("CSV GENERATION START")
            self.log_message(f"CSV mode: {csv_mode}")
            self.log_message(f"ADA Make Up Code (ATT.ADA): {get_saved_ada_makeup_code(self.config_data)}")
            self.log_message("Absence codes: " + ", ".join(get_saved_absence_codes(self.config_data)))
            for line in self.format_selected_programs_for_log(selected).splitlines():
                self.log_message(line)

            engine = AttendanceRecoveryEngine(
                self.conn,
                school_year_start_from_label(self.school_year_var.get()),
                self.log_message,
                get_saved_absence_codes(self.config_data),
                get_saved_ada_makeup_code(self.config_data),
                csv_mode
            )
            output_records, stats = engine.build_output_records(selected, self.ats_sessions)
            if not self.validate_aco_lengths(output_records):
                self.last_output_records = []
                self.last_output_file = None
                self.last_stats = stats
                self.upload_button.config(state="disabled")
                self.set_connection_state("connected", "CSV blocked: ATT.ACO value too long")
                return
            write_output_csv(filename, output_records)

            self.last_output_records = output_records
            self.last_output_file = filename
            self.last_stats = stats
            self.last_csv_mode = self.csv_mode_var.get().upper()
            self.open_button.config(state="normal")
            self.upload_button.config(state="normal" if output_records and self.last_csv_mode == "NEW" else "disabled")
            self.set_connection_state("connected", f"CSV generated: {len(output_records)} record(s)")
            self.log_message(f"CSV saved: {filename}")
            self.log_message(f"CSV mode: {self.last_csv_mode}")
            self.log_message(f"ADA Make Up Code (ATT.ADA): {get_saved_ada_makeup_code(self.config_data)}")
            self.log_message(self.format_stats(stats).replace("\n", " | "))

            try:
                os.startfile(filename)
            except Exception as e:
                self.log_message(f"Could not auto-open CSV: {e}")

            messagebox.showinfo(
                "CSV Created",
                f"Audit CSV created with {len(output_records)} record(s).\n\n"
                "The file has been opened for review if Windows has an associated CSV app.\n\n"
                f"{filename}"
            )
        except Exception as e:
            self.last_output_records = []
            self.last_output_file = None
            self.last_stats = None
            self.upload_button.config(state="disabled")
            self.set_connection_state(self.connection_state, "CSV generation failed")
            self.log_message(f"CSV generation failed: {e}")
            messagebox.showerror("Generate CSV Error", f"{e}\n\n{traceback.format_exc()}")
        finally:
            self.set_busy(False)

    def format_selected_programs_for_log(self, selected_sessions):
        if not selected_sessions:
            return "Supplemental Attendance Sessions selected: None"
        lookup = {(session.get("SC"), session.get("SE")): session for session in self.ats_sessions}
        grouped = {}
        for key in sorted(selected_sessions):
            session = lookup.get(key, {})
            school_name = session.get("SchoolName") or f"School {key[0]}"
            program_name = session.get("NM") or f"SE {key[1]}"
            grouped.setdefault(school_name, []).append(program_name)
        lines = ["Supplemental Attendance Sessions selected:"]
        for school_name in sorted(grouped.keys()):
            lines.append(f"  {school_name}")
            for program_name in sorted(grouped[school_name]):
                lines.append(f"    - {program_name}")
        return "\n".join(lines)

    def format_stats(self, stats):
        if not stats:
            return "No stats available."
        return (
            f"Students loaded: {stats.get('students_loaded', 0)}\n"
            f"Students with output: {stats.get('students_with_output', 0)}\n"
            f"Records generated: {stats.get('records_generated', 0)}\n"
            f"Duplicate ATD records ignored: {stats.get('duplicate_ar_ignored', 0)}\n"
            f"Existing ADA dates skipped: {stats.get('existing_ada_skipped', 0)}\n"
            f"Reused AR dates skipped: {stats.get('reused_ar_dates_skipped', 0)}\n"
            f"Duplicate absence dates skipped: {stats.get('duplicate_absence_dates_skipped', 0)}"
        )

    def open_last_csv(self):
        if not self.last_output_file or not os.path.exists(self.last_output_file):
            messagebox.showwarning("No CSV", "No CSV file is available to open.")
            return
        try:
            os.startfile(self.last_output_file)
        except Exception as e:
            messagebox.showerror("Open CSV Error", str(e))

    def upload_to_aeries(self):
        if not self.last_output_records:
            messagebox.showwarning("No Records", "Generate an audit CSV before uploading.")
            return
        if self.last_csv_mode != "NEW":
            messagebox.showwarning("Upload Disabled", "Upload is only available for NEW Records Only CSV mode.")
            return
        if not self.is_connection_alive():
            messagebox.showwarning("Connection Required", "Please reconnect and try again.")
            return

        review_ok = messagebox.askyesno(
            "CSV Review",
            "Have you reviewed the audit CSV and does the data look correct?"
        )
        if not review_ok:
            self.set_connection_state(self.connection_state, "Upload cancelled: CSV not approved")
            return

        ready = messagebox.askyesno(
            "Upload to Aeries SQL",
            f"Ready to upload {len(self.last_output_records)} ADA makeup record(s) to ATT?\n\n"
            "This will update ATT.ADA, ATT.ADT, and ATT.ACO."
        )
        if not ready:
            self.set_connection_state(self.connection_state, "Upload cancelled")
            return

        try:
            self.set_busy(True)
            result = self.perform_upload(self.last_output_records)
            self.set_busy(False)

            if result.get("rows_not_matched", 0) > 0 or result.get("errors"):
                self.conn.rollback()
                self.log_upload_failure_details(result)
                first_problem = ""
                if result.get("not_matched_records"):
                    index, record = result["not_matched_records"][0]
                    first_problem = f"First unmatched output row: {index}\n{format_record_for_log(record)}"
                elif result.get("errors"):
                    index, record, error_text = result["errors"][0]
                    first_problem = f"First SQL error output row: {index}\n{format_record_for_log(record)}\n\nSQL error: {error_text}"
                messagebox.showerror(
                    "Upload Rolled Back",
                    "Upload failed. No records were changed.\n\n" + first_problem
                )
                self.set_connection_state("connected", "Upload failed and was rolled back")
                return

            commit = messagebox.askyesno(
                "Commit Changes?",
                "Upload transaction has finished.\n\n"
                f"Records in CSV: {len(self.last_output_records)}\n"
                f"Rows updated: {result['rows_updated']}\n"
                f"Rows already correct / no change: {result['rows_no_change']}\n"
                f"Rows not matched in ATT: {result['rows_not_matched']}\n"
                f"Errors: {len(result['errors'])}\n\n"
                "Commit these changes to ATT?"
            )

            if commit:
                self.conn.commit()
                self.log_message("Upload committed.")
                self.set_connection_state("connected", f"Upload committed: {result['rows_updated']} row(s) updated")
                messagebox.showinfo("Upload Complete", f"Changes committed.\n\nRows updated: {result['rows_updated']}")
            else:
                self.conn.rollback()
                self.log_message("Upload rolled back.")
                self.set_connection_state("connected", "Upload rolled back")
                messagebox.showinfo("Rolled Back", "No changes were committed.")
        except Exception as e:
            try:
                self.conn.rollback()
            except Exception:
                pass
            self.set_busy(False)
            self.set_connection_state(self.connection_state, "Upload failed and was rolled back")
            self.log_message(f"Upload failed: {e}")
            messagebox.showerror("Upload Error", f"Upload failed and was rolled back.\n\n{e}\n\n{traceback.format_exc()}")

    def log_upload_failure_details(self, result):
        self.log_block("UPLOAD FAILED - ROLLBACK COMPLETE")
        self.log_message(f"Rows updated before rollback: {result.get('rows_updated', 0)}")
        self.log_message(f"Rows already correct / no change: {result.get('rows_no_change', 0)}")
        self.log_message(f"Rows not matched in ATT: {len(result.get('not_matched_records', []))}")
        self.log_message(f"SQL errors: {len(result.get('errors', []))}")

        if result.get("not_matched_records"):
            index, record = result["not_matched_records"][0]
            self.log_block(
                "First unmatched record",
                f"Output row: {index}\n{format_record_for_log(record)}\nReason: No matching ATT row found for SC + SN + DY where DEL = 0."
            )

        if result.get("errors"):
            index, record, error_text = result["errors"][0]
            self.log_block(
                "First SQL error record",
                f"Output row: {index}\n{format_record_for_log(record)}\nSQL error: {error_text}"
            )

    def perform_upload(self, output_records):
        cursor = self.conn.cursor()
        self.conn.autocommit = False

        exists_query = """
        SELECT COUNT(*)
        FROM ATT
        WHERE SC = ?
          AND SN = ?
          AND DY = ?
          AND DEL = 0
        """

        update_query = """
        UPDATE ATT
        SET
            ADA = ?,
            ADT = ?,
            ACO = ?
        WHERE SC = ?
          AND SN = ?
          AND DY = ?
          AND DEL = 0
          AND (
               ISNULL(ADA,'') <> ISNULL(?,'')
            OR ISNULL(ADT,'1900-01-01') <> ISNULL(?,'1900-01-01')
            OR ISNULL(ACO,'') <> ISNULL(?,'')
          )
        """

        result = {
            "rows_updated": 0,
            "rows_no_change": 0,
            "rows_not_matched": 0,
            "not_matched_records": [],
            "errors": []
        }

        self.log_message("Beginning upload transaction...")
        for index, record in enumerate(output_records, start=1):
            try:
                cursor.execute(
                    update_query,
                    record["ADA"],
                    record["ADT"],
                    record["ACO"],
                    record["SC"],
                    record["SN"],
                    record["DY"],
                    record["ADA"],
                    record["ADT"],
                    record["ACO"]
                )
                if cursor.rowcount and cursor.rowcount > 0:
                    result["rows_updated"] += cursor.rowcount
                else:
                    cursor.execute(exists_query, record["SC"], record["SN"], record["DY"])
                    exists_count = cursor.fetchone()[0]
                    if exists_count > 0:
                        result["rows_no_change"] += 1
                    else:
                        result["rows_not_matched"] += 1
                        result["not_matched_records"].append((index, record))
            except Exception as e:
                result["errors"].append((index, record, str(e)))

        self.log_message(
            f"Upload staged. Updated: {result['rows_updated']}; "
            f"No change: {result['rows_no_change']}; "
            f"Not matched: {result['rows_not_matched']}; "
            f"Errors: {len(result['errors'])}"
        )
        return result

    def on_close(self):
        try:
            self.log_message("Application closed")
        except Exception:
            pass
        self.close_connection()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
