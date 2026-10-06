"""GUI front end for Derby-PACup-XML.py.

Author: Michael Jacobson, coachmikej@gmail.com
License: MIT (see LICENSE file in this directory)

Pick a directory of Vola XML race files, see them listed, hit Run to
process them (same pipeline as the Derby-PACup-XML.py CLI -- CSVs and
per-sex PDFs written to that directory), and view the generated PDFs
inline in tabs. The Age Up Year field controls the age-class calculations;
leave it blank to use the current year minus 1. The Exclude IDs / Exclude
Clubs fields each take a comma-separated list; any race result matching
one is dropped entirely (no points, not listed in any output).

Requires: reportlab, pymupdf (pip install reportlab pymupdf)
    python Derby-PACup-GUI.pyw
"""

import json
import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import pymupdf

import importlib.util

_spec = importlib.util.spec_from_file_location(
    "derby_pacup_xml", Path(__file__).with_name("Derby-PACup-XML.py")
)
derby_pacup_xml = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(derby_pacup_xml)

ZOOM = 1.4
CONFIG_DIR = Path(os.getenv("APPDATA", Path.home())) / "Derby-PACup"
CONFIG_PATH = CONFIG_DIR / "Derby-PACup-GUI-config.json"
DEFAULT_GEOMETRY = "1100x750"


class PdfViewer(ttk.Frame):
    """One tab: a scrollable page image plus Prev/Next/Open controls."""

    def __init__(self, parent, pdf_path):
        super().__init__(parent)
        self.pdf_path = Path(pdf_path)
        self.doc = pymupdf.open(str(self.pdf_path))
        self.page_index = 0
        self._photo = None  # keep a reference so Tk doesn't garbage-collect it

        toolbar = ttk.Frame(self)
        toolbar.pack(side="top", fill="x", padx=4, pady=4)
        ttk.Button(toolbar, text="< Prev", command=self.prev_page).pack(side="left")
        ttk.Button(toolbar, text="Next >", command=self.next_page).pack(side="left", padx=(4, 0))
        self.page_label = ttk.Label(toolbar, text="")
        self.page_label.pack(side="left", padx=12)
        ttk.Button(toolbar, text="Open in default viewer",
                   command=self.open_external).pack(side="right")

        canvas_frame = ttk.Frame(self)
        canvas_frame.pack(side="top", fill="both", expand=True)
        h_scroll = ttk.Scrollbar(canvas_frame, orient="horizontal")
        v_scroll = ttk.Scrollbar(canvas_frame, orient="vertical")
        self.canvas = tk.Canvas(
            canvas_frame, background="#808080",
            xscrollcommand=h_scroll.set, yscrollcommand=v_scroll.set,
        )
        h_scroll.config(command=self.canvas.xview)
        v_scroll.config(command=self.canvas.yview)
        v_scroll.pack(side="right", fill="y")
        h_scroll.pack(side="bottom", fill="x")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.show_page(0)

    def show_page(self, index):
        index = max(0, min(index, self.doc.page_count - 1))
        self.page_index = index
        page = self.doc[index]
        pix = page.get_pixmap(matrix=pymupdf.Matrix(ZOOM, ZOOM))
        self._photo = tk.PhotoImage(data=pix.tobytes("ppm"))
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self._photo)
        self.canvas.config(scrollregion=(0, 0, pix.width, pix.height))
        self.page_label.config(text=f"Page {index + 1} / {self.doc.page_count}")

    def prev_page(self):
        self.show_page(self.page_index - 1)

    def next_page(self):
        self.show_page(self.page_index + 1)

    def open_external(self):
        import os
        os.startfile(self.pdf_path)


class DerbyPACupGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PA Cup Results")
        self.geometry(DEFAULT_GEOMETRY)

        self.directory = None
        self.log_queue = queue.Queue()
        self.worker = None

        self._build_layout()
        self._load_config()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._poll_log_queue)

    def _build_layout(self):
        top = ttk.Frame(self)
        top.pack(side="top", fill="x", padx=8, pady=8)

        ttk.Button(top, text="Select Directory...", command=self.choose_directory).pack(side="left")
        self.dir_label = ttk.Label(top, text="(no directory selected)")
        self.dir_label.pack(side="left", padx=8)

        self.run_button = ttk.Button(top, text="Run", command=self.run_processing, state="disabled")
        self.run_button.pack(side="right")

        self.effective_age_label = ttk.Label(top, foreground="gray")
        self.effective_age_label.pack(side="right", padx=(0, 8))

        self.age_up_year_var = tk.StringVar()
        self.age_up_year_var.trace_add("write", lambda *_: self._update_effective_age_label())
        age_entry = ttk.Entry(top, width=6, textvariable=self.age_up_year_var, justify="center")
        age_entry.pack(side="right")

        ttk.Label(top, text="Age Up Year:").pack(side="right", padx=(0, 4))

        self._update_effective_age_label()

        filters = ttk.Frame(self)
        filters.pack(side="top", fill="x", padx=8, pady=(0, 8))

        ttk.Label(filters, text="Exclude IDs:").pack(side="left")
        self.exclude_ids_var = tk.StringVar()
        ttk.Entry(filters, textvariable=self.exclude_ids_var, width=30).pack(
            side="left", padx=(4, 16)
        )

        ttk.Label(filters, text="Exclude Clubs:").pack(side="left")
        self.exclude_clubs_var = tk.StringVar()
        ttk.Entry(filters, textvariable=self.exclude_clubs_var, width=30).pack(
            side="left", padx=(4, 0)
        )

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(side="top", fill="both", expand=True, padx=8, pady=(0, 8))

        left = ttk.Frame(body)
        ttk.Label(left, text="XML files").pack(anchor="w")
        tree_frame = ttk.Frame(left)
        tree_frame.pack(fill="both", expand=True)
        self.file_tree = ttk.Treeview(tree_frame, show="tree")
        tree_scroll = ttk.Scrollbar(tree_frame, command=self.file_tree.yview)
        self.file_tree.config(yscrollcommand=tree_scroll.set)
        tree_scroll.pack(side="right", fill="y")
        self.file_tree.pack(side="left", fill="both", expand=True)
        body.add(left, weight=1)

        right = ttk.Frame(body)
        self.notebook = ttk.Notebook(right)
        self.notebook.pack(fill="both", expand=True)
        body.add(right, weight=3)

        self.log_tab = ttk.Frame(self.notebook)
        self.log_text = tk.Text(self.log_tab, state="disabled", wrap="word")
        log_scroll = ttk.Scrollbar(self.log_tab, command=self.log_text.yview)
        self.log_text.config(yscrollcommand=log_scroll.set)
        log_scroll.pack(side="right", fill="y")
        self.log_text.pack(side="left", fill="both", expand=True)
        self.notebook.add(self.log_tab, text="Log")

    def _load_config(self):
        if not CONFIG_PATH.exists():
            # First run: nothing to restore. Write literal defaults rather
            # than self.geometry() -- the window hasn't been drawn yet, so
            # Tk would report a meaningless "1x1+0+0" placeholder size.
            self._write_config({
                "age_up_year": "",
                "window_geometry": DEFAULT_GEOMETRY,
                "directory": "",
                "exclude_ids": "",
                "exclude_clubs": "",
            })
            return

        try:
            config = json.loads(CONFIG_PATH.read_text())
        except (OSError, ValueError) as exc:
            self._log(f"Could not read config file {CONFIG_PATH}: {exc}")
            return

        geometry = config.get("window_geometry")
        if geometry:
            try:
                self.geometry(geometry)
            except tk.TclError:
                pass

        age_up_year = config.get("age_up_year", "")
        if age_up_year:
            self.age_up_year_var.set(str(age_up_year))

        self.exclude_ids_var.set(config.get("exclude_ids", ""))
        self.exclude_clubs_var.set(config.get("exclude_clubs", ""))

        directory = config.get("directory")
        if directory and Path(directory).is_dir():
            self.directory = Path(directory)
            self.dir_label.config(text=str(self.directory))
            self.refresh_file_list()

    def _save_config(self):
        self._write_config({
            "age_up_year": self.age_up_year_var.get().strip(),
            "window_geometry": self.geometry(),
            "directory": str(self.directory) if self.directory else "",
            "exclude_ids": self.exclude_ids_var.get().strip(),
            "exclude_clubs": self.exclude_clubs_var.get().strip(),
        })

    def _write_config(self, config):
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            CONFIG_PATH.write_text(json.dumps(config, indent=2))
        except OSError as exc:
            self._log(f"Could not write config file {CONFIG_PATH}: {exc}")

    def _on_close(self):
        self._save_config()
        self.destroy()

    def choose_directory(self):
        chosen = filedialog.askdirectory(title="Select directory with XML race files")
        if not chosen:
            return
        self.directory = Path(chosen)
        self.dir_label.config(text=str(self.directory))
        self.refresh_file_list()

    def refresh_file_list(self):
        for item in self.file_tree.get_children():
            self.file_tree.delete(item)

        xml_files = sorted(self.directory.glob("*.xml")) if self.directory else []
        for path in xml_files:
            node = self.file_tree.insert("", "end", text=path.name, open=True)
            try:
                info = derby_pacup_xml.read_race_summary(path)
                self.file_tree.insert(node, "end", text=f"Racedate: {info['date']}")
                self.file_tree.insert(node, "end", text=f"Eventname: {info['eventname']}")
                self.file_tree.insert(node, "end", text=f"Place: {info['place']}")
            except Exception as exc:  # noqa: BLE001 -- surface a bad XML file inline
                self.file_tree.insert(node, "end", text=f"(could not read: {exc})")

        self.run_button.config(state="normal" if xml_files else "disabled")
        if self.directory and not xml_files:
            self._log(f"No .xml files found in {self.directory}")

    def _update_effective_age_label(self):
        text = self.age_up_year_var.get().strip()
        if not text:
            self.effective_age_label.config(
                text=f"(blank = {derby_pacup_xml.default_age_up_year()})"
            )
            return
        try:
            int(text)
            self.effective_age_label.config(text=f"(using {text})")
        except ValueError:
            self.effective_age_label.config(text="(must be a year)")

    def run_processing(self):
        if not self.directory or self.worker and self.worker.is_alive():
            return

        age_text = self.age_up_year_var.get().strip()
        if age_text:
            try:
                int(age_text)
            except ValueError:
                messagebox.showerror("Invalid Age Up Year", f"{age_text!r} is not a valid year.")
                return

        self.run_button.config(state="disabled")
        self._clear_pdf_tabs()
        self._log(f"--- Processing {self.directory} ---")

        exclude_ids = self.exclude_ids_var.get().strip()
        exclude_clubs = self.exclude_clubs_var.get().strip()
        self.worker = threading.Thread(
            target=self._run_worker, args=(age_text, exclude_ids, exclude_clubs), daemon=True
        )
        self.worker.start()

    def _run_worker(self, age_up_year, exclude_ids, exclude_clubs):
        try:
            pdf_paths = derby_pacup_xml.process_directory(
                self.directory, age_up_year=age_up_year,
                exclude_ids=exclude_ids, exclude_clubs=exclude_clubs,
                log=lambda msg: self.log_queue.put(("log", msg)),
            )
            self.log_queue.put(("done", pdf_paths))
        except Exception as exc:  # noqa: BLE001 -- surface any failure to the GUI
            self.log_queue.put(("error", str(exc)))

    def _poll_log_queue(self):
        try:
            while True:
                kind, payload = self.log_queue.get_nowait()
                if kind == "log":
                    self._log(payload)
                elif kind == "done":
                    self._log("--- Done ---")
                    self._show_pdfs(payload)
                    self.run_button.config(state="normal")
                elif kind == "error":
                    self._log(f"ERROR: {payload}")
                    messagebox.showerror("Processing failed", payload)
                    self.run_button.config(state="normal")
        except queue.Empty:
            pass
        self.after(100, self._poll_log_queue)

    def _log(self, message):
        self.log_text.config(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _clear_pdf_tabs(self):
        for tab_id in self.notebook.tabs():
            if tab_id != str(self.log_tab):
                self.notebook.forget(tab_id)

    def _show_pdfs(self, pdf_paths):
        if not pdf_paths:
            messagebox.showinfo("No results", "No PDFs were generated (no Men/Women races found).")
            return
        for sex, path in pdf_paths:
            viewer = PdfViewer(self.notebook, path)
            self.notebook.add(viewer, text=sex)
        self.notebook.select(1)


if __name__ == "__main__":
    app = DerbyPACupGUI()
    app.mainloop()
