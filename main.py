"""
render_farm_gui_with_eta.py
Server + Client GUI (Artist & Worker) dengan:
- parsing progress & ETA dari log blender
- UI multiple workers + pilih worker manual saat submit

Requirements:
pip install Flask PySide6 requests
"""

import sys
import os
import threading
import time
import uuid
import subprocess
import json
import re
from datetime import datetime
from functools import partial

# --------- CONFIG ----------
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 5000
SERVER_URL = f"http://127.0.0.1:{SERVER_PORT}"  # jika ingin jaringan, ganti ke IP server
POLL_INTERVAL = 1.0  # detik polling GUI
FRAME_TIME_WINDOW = 8  # number of recent frames to average
# ---------------------------

# ---- Backend (Flask) ----
from flask import Flask, request, jsonify
app = Flask(__name__)

# In-memory store (simple)
WORKERS = {}  # worker_id -> {id, name, on, last_seen, info}
TASKS = {}    # task_id -> {id, path, start, end, artist, status, assigned_worker, logs[], created_at, updated_at, progress...}

LOCK = threading.Lock()

def now_iso():
    return datetime.utcnow().isoformat() + "Z"

@app.route("/register_worker", methods=["POST"])
def register_worker():
    payload = request.json
    wid = payload.get("id")
    with LOCK:
        WORKERS[wid] = {
            "id": wid,
            "name": payload.get("name", "worker"),
            "on": payload.get("on", True),
            "info": payload.get("info", {}),
            "last_seen": now_iso()
        }
    return jsonify({"ok": True})

@app.route("/update_worker", methods=["POST"])
def update_worker():
    payload = request.json
    wid = payload.get("id")
    with LOCK:
        if wid in WORKERS:
            WORKERS[wid]["on"] = payload.get("on", WORKERS[wid]["on"])
            WORKERS[wid]["info"] = payload.get("info", WORKERS[wid]["info"])
            # allow name update
            if payload.get("name"):
                WORKERS[wid]["name"] = payload.get("name")
            WORKERS[wid]["last_seen"] = now_iso()
            return jsonify({"ok": True})
        else:
            return jsonify({"ok": False, "error": "unknown worker"}), 404

@app.route("/list_workers", methods=["GET"])
def list_workers():
    with LOCK:
        return jsonify({"workers": list(WORKERS.values())})

@app.route("/submit_task", methods=["POST"])
def submit_task():
    payload = request.json
    path = payload.get("path")
    start = int(payload.get("start", 1))
    end = int(payload.get("end", start))
    artist = payload.get("artist", "unknown")
    assigned = payload.get("assigned_worker")  # can be None or worker id or 'auto'
    with LOCK:
        task_id = str(uuid.uuid4())
        # if explicitly requested assigned worker but that worker is OFF -> still accept but mark assigned_worker as given (worker won't accept until on)
        assigned_worker = None
        if assigned and assigned != "auto":
            # if that worker exists, keep assigned (even if off)
            if assigned in WORKERS:
                assigned_worker = assigned
            else:
                assigned_worker = None
        else:
            # auto: pick first ON worker
            for w in WORKERS.values():
                if w.get("on"):
                    assigned_worker = w["id"]
                    break
        TASKS[task_id] = {
            "id": task_id,
            "path": path,
            "start": start,
            "end": end,
            "artist": artist,
            "status": "queued",
            "assigned_worker": assigned_worker,
            "logs": [],
            "created_at": now_iso(),
            "updated_at": now_iso(),
            # progress fields
            "current_frame": None,
            "total_frames": end - start + 1,
            "progress_percent": 0.0,
            "eta_seconds": None
        }
    return jsonify({"ok": True, "task_id": task_id, "assigned_worker": assigned_worker})

@app.route("/get_task", methods=["GET"])
def get_task():
    wid = request.args.get("worker_id")
    with LOCK:
        # Prefer tasks explicitly assigned to this worker first
        for t in TASKS.values():
            if t["status"] == "queued" and (t["assigned_worker"] == wid):
                t["status"] = "assigned"
                t["assigned_worker"] = wid
                t["updated_at"] = now_iso()
                return jsonify({"task": t})
        # Otherwise, give first queued unassigned or assigned to None
        for t in TASKS.values():
            if t["status"] == "queued" and (t["assigned_worker"] is None):
                # ensure this worker is ON (caller should be a worker that is on)
                t["assigned_worker"] = wid
                t["status"] = "assigned"
                t["updated_at"] = now_iso()
                return jsonify({"task": t})
    return jsonify({"task": None})

@app.route("/update_task", methods=["POST"])
def update_task():
    payload = request.json
    tid = payload.get("task_id")
    status = payload.get("status")
    log = payload.get("log")
    extra = payload.get("extra", {})  # can contain progress fields
    with LOCK:
        if tid not in TASKS:
            return jsonify({"ok": False, "error": "unknown task"}), 404
        t = TASKS[tid]
        if status:
            t["status"] = status
        if log:
            t["logs"].append({"t": now_iso(), "line": log})
            if len(t["logs"]) > 5000:
                t["logs"] = t["logs"][-5000:]
        # update progress fields if present
        if extra:
            if "current_frame" in extra:
                t["current_frame"] = extra["current_frame"]
            if "total_frames" in extra:
                t["total_frames"] = extra["total_frames"]
            if "progress_percent" in extra:
                t["progress_percent"] = extra["progress_percent"]
            if "eta_seconds" in extra:
                t["eta_seconds"] = extra["eta_seconds"]
        t["updated_at"] = now_iso()
    return jsonify({"ok": True})

@app.route("/tasks", methods=["GET"])
def tasks():
    with LOCK:
        return jsonify({"tasks": list(TASKS.values())})

def run_server():
    app.run(host=SERVER_HOST, port=SERVER_PORT, threaded=True)

# ---- CLIENT GUI (PySide6) ----
from PySide6 import QtCore, QtWidgets, QtGui
import requests

# --------- Stylesheet dark modern ----------
DARK_STYLE = """
QWidget { background: #0f1115; color: #e6eef3; font-family: "Segoe UI", Roboto, Arial; }
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QComboBox { background: #111216; border: 1px solid #22262b; padding: 6px; border-radius: 6px; }
QPushButton { background: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:1, stop:0 #2c6fdb, stop:1 #1b5ed7); border-radius: 8px; padding: 8px; color: white; font-weight:600; }
QPushButton:disabled { background: #3a3f45; color: #999; }
QLabel#title { font-size:18px; font-weight:700; }
QGroupBox { border: 1px solid #1a1d22; border-radius:8px; margin-top:8px; padding:10px; }
QScrollArea { background: transparent; }
QCheckBox { padding:4px; }
QComboBox { padding:6px; border-radius:6px; }
QTableWidget { background: #0f1115; gridline-color: #222; }
QHeaderView::section { background: #0f1115; color: #bfcbd8; padding:6px; }
QProgressBar { background: #111216; border-radius:6px; height:12px; }
#small { font-size:11px; color:#9fb3c8; }
.toggle-btn { background: #2b2f34; border-radius:18px; padding:4px; min-width:64px; min-height:28px; color:#cfe9ff; }
"""

# --------- Utility functions ----------
def api_post(path, data):
    try:
        r = requests.post(SERVER_URL + path, json=data, timeout=4)
        return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}

def api_get(path, params=None):
    try:
        r = requests.get(SERVER_URL + path, params=params, timeout=4)
        return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}

def format_eta(seconds):
    if seconds is None:
        return "-"
    try:
        s = int(round(float(seconds)))
    except:
        return "-"
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    if h > 0:
        return f"{h}h{m:02d}m"
    if m > 0:
        return f"{m}m{sec:02d}s"
    return f"{sec}s"

# --------- Worker Logic with ETA parsing ----------
class WorkerThread(QtCore.QThread):
    log_signal = QtCore.Signal(str)
    status_signal = QtCore.Signal(str)
    progress_signal = QtCore.Signal(dict)  # {percent, current, total, eta}

    def __init__(self, worker_id, worker_name, parent=None):
        super().__init__(parent)
        self.worker_id = worker_id
        self.worker_name = worker_name
        self._running = True
        self._available = True
        # internal for ETA parsing
        self._frame_times = []  # list of durations between consecutive frames (seconds)
        self._last_frame_time = None
        self._last_frame_number = None
        # regex patterns to detect frame lines
        # common patterns: "Fra: 1 Mem:", "Fra:1", "Saved: /.../frame_0001.png"
        self.re_frame = re.compile(r"\bFra[:\s]+(\d+)\b", re.IGNORECASE)
        self.re_frame_alt = re.compile(r"\bFrame[:\s]+(\d+)\b", re.IGNORECASE)
        self.re_saved = re.compile(r"Saved:.*?(\d+)(?:\D|$)")  # sometimes includes frame number
        self.re_rendered = re.compile(r"Finished rendering.*?(\d+)", re.IGNORECASE)

    def set_available(self, avail: bool):
        self._available = avail
        api_post("/update_worker", {"id": self.worker_id, "on": avail, "name": self.worker_name, "info": {}})

    def stop(self):
        self._running = False

    def _extract_frame_from_line(self, line: str):
        # try multiple regexes
        m = self.re_frame.search(line)
        if m:
            try:
                return int(m.group(1))
            except:
                pass
        m = self.re_frame_alt.search(line)
        if m:
            try:
                return int(m.group(1))
            except:
                pass
        m = self.re_saved.search(line)
        if m:
            try:
                return int(m.group(1))
            except:
                pass
        m = self.re_rendered.search(line)
        if m:
            try:
                return int(m.group(1))
            except:
                pass
        # fallback: try to find standalone integers that look like frames when context includes "Time" or "Fra"
        return None

    def run(self):
        # register initially
        api_post("/register_worker", {"id": self.worker_id, "name": self.worker_name, "on": self._available, "info": {}})
        self.log_signal.emit(f"[{now_iso()}] Worker registered: {self.worker_name} ({self.worker_id})")
        while self._running:
            try:
                # heartbeat update
                api_post("/update_worker", {"id": self.worker_id, "on": self._available, "name": self.worker_name, "info": {}})
                if self._available:
                    res = api_get("/get_task", params={"worker_id": self.worker_id})
                    if isinstance(res, dict) and res.get("task"):
                        t = res["task"]
                        tid = t["id"]
                        total_frames = t.get("total_frames", t.get("end", t.get("end", t["end"])) - t.get("start", t["start"]) + 1)
                        cmd = [
                            "blender", "-b", t["path"],
                            "-s", str(t["start"]), "-e", str(t["end"]), "-a"
                        ]
                        api_post("/update_task", {"task_id": tid, "status": "running", "log": f"Worker {self.worker_name} started task."})
                        self.status_signal.emit("running")
                        self.log_signal.emit(f"Starting task {tid}: {' '.join(cmd)}")
                        # reset ETA state
                        self._frame_times = []
                        self._last_frame_time = None
                        self._last_frame_number = None
                        # run subprocess and stream logs
                        try:
                            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
                        except Exception as e:
                            api_post("/update_task", {"task_id": tid, "status": "error", "log": f"Failed to start blender: {e}"})
                            self.log_signal.emit(f"Failed to start blender: {e}")
                            continue
                        # read stdout line by line
                        start_time = time.time()
                        frames_seen = set()
                        while True:
                            line = proc.stdout.readline()
                            if not line:
                                if proc.poll() is not None:
                                    break
                                time.sleep(0.05)
                                continue
                            line_stripped = line.rstrip()
                            # send raw log line to server
                            api_post("/update_task", {"task_id": tid, "log": line_stripped})
                            self.log_signal.emit(line_stripped)
                            # attempt to parse a frame number
                            frame_num = self._extract_frame_from_line(line_stripped)
                            if frame_num is not None:
                                now_t = time.time()
                                # update frame times and compute average
                                if self._last_frame_number is not None and frame_num != self._last_frame_number:
                                    # accept only forward increments (or any change) but compute delta
                                    if self._last_frame_time is not None:
                                        delta = max(0.0001, now_t - self._last_frame_time)
                                        self._frame_times.append(delta)
                                        if len(self._frame_times) > FRAME_TIME_WINDOW:
                                            self._frame_times.pop(0)
                                self._last_frame_time = now_t
                                self._last_frame_number = frame_num
                                frames_seen.add(frame_num)
                                # compute average frame time
                                if len(self._frame_times) > 0:
                                    avg = sum(self._frame_times) / len(self._frame_times)
                                else:
                                    # fallback: use elapsed / frames_seen
                                    elapsed = now_t - start_time
                                    if len(frames_seen) > 0:
                                        avg = elapsed / max(1, len(frames_seen))
                                    else:
                                        avg = None
                                # calculate progress & ETA
                                start_frame = t.get("start", 1)
                                end_frame = t.get("end", t.get("end", start_frame))
                                total = end_frame - start_frame + 1
                                # derive completed frames as max seen - start +1 clipped
                                completed = max(0, frame_num - start_frame + 1)
                                percent = min(100.0, (completed / total) * 100.0) if total > 0 else 0.0
                                eta_s = None
                                if avg is not None:
                                    remaining = max(0, total - completed)
                                    eta_s = remaining * avg
                                # push progress update
                                api_post("/update_task", {"task_id": tid, "extra": {
                                    "current_frame": frame_num,
                                    "total_frames": total,
                                    "progress_percent": round(percent, 2),
                                    "eta_seconds": int(round(eta_s)) if eta_s is not None else None
                                }})
                                # also emit locally
                                self.progress_signal.emit({
                                    "current_frame": frame_num,
                                    "total_frames": total,
                                    "percent": round(percent,2),
                                    "eta_seconds": int(round(eta_s)) if eta_s is not None else None
                                })
                        ret = proc.poll()
                        if ret == 0:
                            api_post("/update_task", {"task_id": tid, "status": "done", "log": f"Worker finished: exit {ret}"})
                            self.log_signal.emit(f"Task {tid} finished (exit {ret})")
                        else:
                            api_post("/update_task", {"task_id": tid, "status": "error", "log": f"Worker finished with error: exit {ret}"})
                            self.log_signal.emit(f"Task {tid} finished with error (exit {ret})")
                        self.status_signal.emit("idle")
                    else:
                        time.sleep(0.8)
                else:
                    time.sleep(1.0)
            except Exception as e:
                self.log_signal.emit(f"Worker loop error: {e}")
                time.sleep(2.0)

# --------- GUI Components ----------
class ToggleSwitch(QtWidgets.QPushButton):
    def __init__(self, label_on="ON", label_off="OFF"):
        super().__init__()
        self.setCheckable(True)
        self.setChecked(True)
        self.setText(label_on)
        self.label_on = label_on
        self.label_off = label_off
        self.setObjectName("toggle")
        self.toggled.connect(self._on_toggle)
        self.setStyleSheet("QPushButton#toggle { min-width:80px; padding:6px; border-radius:16px; }")

    def _on_toggle(self, checked):
        self.setText(self.label_on if checked else self.label_off)

# Artist window with worker selection and ETA display
class ArtistWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RenderQ - Submit")
        self.setMinimumSize(980, 620)
        self.init_ui()
        self.poll_timer = QtCore.QTimer()
        self.poll_timer.timeout.connect(self.refresh_all)
        self.poll_timer.start(int(POLL_INTERVAL * 1000))
        self.refresh_all()

    def init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        header = QtWidgets.QLabel("Artist - Submit Render Task")
        header.setObjectName("title")
        layout.addWidget(header)

        main_h = QtWidgets.QHBoxLayout()
        left_v = QtWidgets.QVBoxLayout()
        right_v = QtWidgets.QVBoxLayout()
        main_h.addLayout(left_v, 2)
        main_h.addLayout(right_v, 3)

        # --- left: form ---
        form = QtWidgets.QGroupBox("Submit Task")
        f_layout = QtWidgets.QGridLayout()
        form.setLayout(f_layout)

        f_layout.addWidget(QtWidgets.QLabel("Your name:"), 0, 0)
        self.input_name = QtWidgets.QLineEdit()
        f_layout.addWidget(self.input_name, 0, 1)

        f_layout.addWidget(QtWidgets.QLabel("Blend file path:"), 1, 0)
        path_h = QtWidgets.QHBoxLayout()
        self.input_path = QtWidgets.QLineEdit()
        btn_browse = QtWidgets.QPushButton("Browse")
        btn_browse.clicked.connect(self.browse_file)
        path_h.addWidget(self.input_path)
        path_h.addWidget(btn_browse)
        f_layout.addLayout(path_h, 1, 1)

        f_layout.addWidget(QtWidgets.QLabel("Start frame:"), 2, 0)
        self.input_start = QtWidgets.QSpinBox()
        self.input_start.setRange(0, 100000)
        self.input_start.setValue(1)
        f_layout.addWidget(self.input_start, 2, 1)

        f_layout.addWidget(QtWidgets.QLabel("End frame:"), 3, 0)
        self.input_end = QtWidgets.QSpinBox()
        self.input_end.setRange(0, 100000)
        self.input_end.setValue(1)
        f_layout.addWidget(self.input_end, 3, 1)

        # worker selection
        f_layout.addWidget(QtWidgets.QLabel("Assign to worker:"), 4, 0)
        self.worker_combo = QtWidgets.QComboBox()
        self.worker_combo.addItem("Auto (first ON)", "auto")
        f_layout.addWidget(self.worker_combo, 4, 1)

        self.btn_submit = QtWidgets.QPushButton("Submit Task")
        self.btn_submit.clicked.connect(self.submit_task)
        f_layout.addWidget(self.btn_submit, 5, 0, 1, 2)

        left_v.addWidget(form)

        # workers list panel
        workers_box = QtWidgets.QGroupBox("Workers (live)")
        w_layout = QtWidgets.QVBoxLayout()
        workers_box.setLayout(w_layout)
        self.workers_table = QtWidgets.QTableWidget(0, 4)
        self.workers_table.setHorizontalHeaderLabels(["ID", "Name", "On", "Last seen"])
        self.workers_table.horizontalHeader().setStretchLastSection(True)
        w_layout.addWidget(self.workers_table)
        left_v.addWidget(workers_box)

        # footer
        footer = QtWidgets.QLabel("Created by Dwiky Gilang Imrodhani | https://github.com/dwikygilang")
        footer.setObjectName("small")
        left_v.addWidget(footer)

        # --- right: tasks + log ---
        tasks_box = QtWidgets.QGroupBox("Tasks")
        t_layout = QtWidgets.QVBoxLayout()
        tasks_box.setLayout(t_layout)

        self.table = QtWidgets.QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["ID", "Artist", "Frames", "Worker", "Status", "Progress", "ETA"])
        self.table.horizontalHeader().setStretchLastSection(True)
        t_layout.addWidget(self.table)

        log_box = QtWidgets.QGroupBox("Selected Task Log & Details")
        lg_layout = QtWidgets.QVBoxLayout()
        log_box.setLayout(lg_layout)
        self.log_view = QtWidgets.QPlainTextEdit()
        self.log_view.setReadOnly(True)
        lg_layout.addWidget(self.log_view)
        self.task_detail_label = QtWidgets.QLabel("")
        self.task_detail_label.setObjectName("small")
        lg_layout.addWidget(self.task_detail_label)

        right_v.addWidget(tasks_box)
        right_v.addWidget(log_box)

        layout.addLayout(main_h)

        # connect selection
        self.table.itemSelectionChanged.connect(self.on_select_task)

    def browse_file(self):
        fn, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select .blend file", "", "Blender files (*.blend);;All files (*)")
        if fn:
            self.input_path.setText(fn)

    def submit_task(self):
        path = self.input_path.text().strip()
        start = int(self.input_start.value())
        end = int(self.input_end.value())
        name = self.input_name.text().strip() or "artist"
        assigned = self.worker_combo.currentData()  # 'auto' or worker id
        if not path:
            QtWidgets.QMessageBox.warning(self, "Validation", "Please select a .blend path.")
            return
        # if user selected a specific worker that is offline -> warn
        if assigned and assigned != "auto":
            res_w = api_get("/list_workers")
            if isinstance(res_w, dict) and "workers" in res_w:
                chosen = None
                for w in res_w["workers"]:
                    if w["id"] == assigned:
                        chosen = w
                        break
                if chosen and not chosen.get("on"):
                    # warn but allow
                    resp = QtWidgets.QMessageBox.question(self, "Worker offline", f"Worker '{chosen['name']}' is currently OFF. Submit anyway (it will stay queued)?", QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
                    if resp != QtWidgets.QMessageBox.Yes:
                        return
        res = api_post("/submit_task", {"path": path, "start": start, "end": end, "artist": name, "assigned_worker": assigned})
        if not res.get("ok"):
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to submit: {res.get('error')}")
            return
        tid = res.get("task_id")
        assigned_worker = res.get("assigned_worker")
        QtWidgets.QMessageBox.information(self, "Submitted", f"Task submitted (id={tid}). Assigned worker: {assigned_worker}")
        # clear form optional
        # self.input_path.clear()
        self.refresh_all()

    def refresh_workers(self):
        res = api_get("/list_workers")
        if not isinstance(res, dict) or "workers" not in res:
            return
        workers = res["workers"]
        # update combo
        current = self.worker_combo.currentData()
        self.worker_combo.clear()
        self.worker_combo.addItem("Auto (first ON)", "auto")
        for w in workers:
            label = f"{w['name']} ({w['id'][:8]}) {'[ON]' if w.get('on') else '[OFF]'}"
            self.worker_combo.addItem(label, w["id"])
        # try to restore selection
        index = 0
        for i in range(self.worker_combo.count()):
            if self.worker_combo.itemData(i) == current:
                index = i
                break
        self.worker_combo.setCurrentIndex(index)
        # update table
        self.workers_table.setRowCount(len(workers))
        for i, w in enumerate(workers):
            self.workers_table.setItem(i, 0, QtWidgets.QTableWidgetItem(w["id"]))
            self.workers_table.setItem(i, 1, QtWidgets.QTableWidgetItem(w.get("name","")))
            self.workers_table.setItem(i, 2, QtWidgets.QTableWidgetItem("ON" if w.get("on") else "OFF"))
            self.workers_table.setItem(i, 3, QtWidgets.QTableWidgetItem(w.get("last_seen","")))

    def refresh_tasks(self):
        res = api_get("/tasks")
        if not isinstance(res, dict) or "tasks" not in res:
            return
        tasks = res["tasks"]
        self.table.setRowCount(len(tasks))
        for i, t in enumerate(tasks):
            id_item = QtWidgets.QTableWidgetItem(t["id"])
            artist_item = QtWidgets.QTableWidgetItem(t.get("artist", ""))
            frames_item = QtWidgets.QTableWidgetItem(f"{t.get('start')}-{t.get('end')}")
            worker_item = QtWidgets.QTableWidgetItem(str(t.get("assigned_worker")))
            status_item = QtWidgets.QTableWidgetItem(t.get("status"))
            prog = t.get("progress_percent", 0.0) or 0.0
            eta = format_eta(t.get("eta_seconds"))
            progress_item = QtWidgets.QTableWidgetItem(f"{prog}%")
            eta_item = QtWidgets.QTableWidgetItem(eta)
            self.table.setItem(i, 0, id_item)
            self.table.setItem(i, 1, artist_item)
            self.table.setItem(i, 2, frames_item)
            self.table.setItem(i, 3, worker_item)
            self.table.setItem(i, 4, status_item)
            self.table.setItem(i, 5, progress_item)
            self.table.setItem(i, 6, eta_item)

    def on_select_task(self):
        sel = self.table.selectedIndexes()
        if not sel:
            self.log_view.setPlainText("")
            self.task_detail_label.setText("")
            return
        row = sel[0].row()
        tid_item = self.table.item(row, 0)
        if not tid_item: return
        tid = tid_item.text()
        res = api_get("/tasks")
        if not res.get("tasks"): return
        for t in res["tasks"]:
            if t["id"] == tid:
                logs = t.get("logs", [])
                txt = "\n".join(f"[{l['t']}] {l['line']}" for l in logs[-200:])
                self.log_view.setPlainText(txt)
                detail = f"Status: {t.get('status')} | Assigned: {t.get('assigned_worker')} | Progress: {t.get('progress_percent')}% | ETA: {format_eta(t.get('eta_seconds'))}"
                self.task_detail_label.setText(detail)
                break

    def refresh_all(self):
        self.refresh_workers()
        self.refresh_tasks()
        # update selected log view if a task selected
        self.on_select_task()

# Worker window (UI)
class WorkerWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RenderQ - Workers")
        self.setMinimumSize(760, 520)
        self.worker_id = str(uuid.uuid4())[:8]
        self.worker_name = f"worker-{self.worker_id}"
        self.thread = None
        self.init_ui()
        self.start_worker_thread()

    def init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        header = QtWidgets.QLabel(f"Worker Node - {self.worker_name}")
        header.setObjectName("title")
        layout.addWidget(header)

        info_box = QtWidgets.QGroupBox("Worker Info")
        i_layout = QtWidgets.QGridLayout()
        info_box.setLayout(i_layout)
        i_layout.addWidget(QtWidgets.QLabel("Worker ID:"), 0, 0)
        self.lbl_id = QtWidgets.QLabel(self.worker_id)
        i_layout.addWidget(self.lbl_id, 0, 1)
        i_layout.addWidget(QtWidgets.QLabel("Name:"), 1, 0)
        self.input_name = QtWidgets.QLineEdit(self.worker_name)
        i_layout.addWidget(self.input_name, 1, 1)
        i_layout.addWidget(QtWidgets.QLabel("Available:"), 2, 0)
        self.toggle = ToggleSwitch("ON", "OFF")
        self.toggle.setChecked(True)
        self.toggle.clicked.connect(self.on_toggle)
        i_layout.addWidget(self.toggle, 2, 1)
        layout.addWidget(info_box)

        # status & logs
        status_box = QtWidgets.QGroupBox("Status & Logs")
        s_layout = QtWidgets.QVBoxLayout()
        status_box.setLayout(s_layout)
        self.lbl_status = QtWidgets.QLabel("idle")
        s_layout.addWidget(self.lbl_status)
        self.log_view = QtWidgets.QPlainTextEdit()
        self.log_view.setReadOnly(True)
        s_layout.addWidget(self.log_view)
        # progress mini
        self.progress_label = QtWidgets.QLabel("Progress: -")
        s_layout.addWidget(self.progress_label)

        layout.addWidget(status_box)

        footer = QtWidgets.QLabel("Created by Dwiky Gilang Imrodhani | https://github.com/dwikygilang")
        footer.setObjectName("small")
        layout.addWidget(footer)

    def start_worker_thread(self):
        self.worker_thread = WorkerThread(self.worker_id, self.worker_name)
        self.worker_thread.log_signal.connect(self.append_log)
        self.worker_thread.status_signal.connect(self.update_status)
        self.worker_thread.progress_signal.connect(self.update_progress)
        self.worker_thread.start()

    def append_log(self, text):
        # ensure UI thread
        self.log_view.appendPlainText(text)

    def update_status(self, s):
        self.lbl_status.setText(s)

    def update_progress(self, p: dict):
        # p: {current_frame, total_frames, percent, eta_seconds}
        eta_text = format_eta(p.get("eta_seconds"))
        self.progress_label.setText(f"Progress: {p.get('percent')}% ({p.get('current_frame')}/{p.get('total_frames')}) ETA: {eta_text}")

    def on_toggle(self):
        checked = self.toggle.isChecked()
        # update worker name if changed
        newname = self.input_name.text().strip()
        self.worker_thread.worker_name = newname or self.worker_thread.worker_name
        self.worker_thread.set_available(checked)
        api_post("/update_worker", {"id": self.worker_id, "on": checked, "name": newname})
        self.append_log(f"Availability set to {'ON' if checked else 'OFF'}")

    def closeEvent(self, event):
        try:
            self.worker_thread.stop()
        except:
            pass
        event.accept()

# Mode chooser
class ModeChooser(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Render Farm - Mode Selection")
        self.setFixedSize(460, 260)
        self.init_ui()

    def init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        header = QtWidgets.QLabel("Render Farm\nChoose Mode")
        header.setAlignment(QtCore.Qt.AlignCenter)
        header.setObjectName("title")
        layout.addWidget(header)
        layout.addSpacing(10)

        btn_artist = QtWidgets.QPushButton("Artist (submit tasks)")
        btn_worker = QtWidgets.QPushButton("Worker (render node)")

        btn_artist.clicked.connect(self.open_artist)
        btn_worker.clicked.connect(self.open_worker)

        layout.addWidget(btn_artist)
        layout.addWidget(btn_worker)
        layout.addStretch()

    def open_artist(self):
        self.aw = ArtistWindow()
        self.aw.show()
        self.close()

    def open_worker(self):
        self.ww = WorkerWindow()
        self.ww.show()
        self.close()

# ---- Main entrypoint ----
def main():
    # start server thread
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    # small wait for server up
    time.sleep(0.6)

    app_qt = QtWidgets.QApplication(sys.argv)
    app_qt.setStyleSheet(DARK_STYLE)
    chooser = ModeChooser()
    chooser.show()
    sys.exit(app_qt.exec())

if __name__ == "__main__":
    main()
