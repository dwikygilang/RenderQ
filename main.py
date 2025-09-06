import os
import subprocess
import json
import time
import datetime
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinterdnd2 import DND_FILES, TkinterDnD
import ttkbootstrap as tb
from ttkbootstrap.constants import *

# ==============================
# Inspect .blend
# ==============================
def inspect_blend(blend_file, blender_exec="blender"):
    code = """
import bpy, json
scene = bpy.context.scene
data = {
    "frame_start": scene.frame_start,
    "frame_end": scene.frame_end,
    "frame_step": scene.frame_step,
    "output_path": scene.render.filepath,
    "use_nodes": scene.use_nodes
}
print("BLEND_META_START")
print(json.dumps(data))
print("BLEND_META_END")
"""
    try:
        result = subprocess.run(
            [blender_exec, "-b", blend_file, "--python-expr", code],
            capture_output=True, text=True
        )
        inside = False
        json_str = ""
        for line in result.stdout.splitlines():
            if "BLEND_META_START" in line:
                inside = True
                continue
            if "BLEND_META_END" in line:
                break
            if inside:
                json_str += line.strip()
        if json_str:
            return json.loads(json_str)
    except Exception as e:
        print("Inspect error:", e)
    return None

# ==============================
# Render job
# ==============================
def render_job(blend_file, start, end, step, blender_exec="blender", update_frame_cb=None):
    cmd = [
        blender_exec, "-b", blend_file,
        "-s", str(start),
        "-e", str(end),
        "-j", str(step),
        "-a"
    ]
    print("Running:", " ".join(cmd))

    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    for line in process.stdout:
        if "Fra:" in line:
            try:
                frame_num = int(line.split("Fra:")[1].split()[0])
                if update_frame_cb:
                    update_frame_cb(frame_num)
            except:
                pass
    process.wait()
    return process.returncode

# ==============================
# Main App
# ==============================
class BlenderQueueApp:
    def __init__(self, root):
        self.root = root
        self.root.title("🎬 RenderQ by Dwiky")
        self.root.geometry("1000x720")

        self.queue = []  # list of dict: {file, meta, status}
        self.is_rendering = False
        self.blender_exec = "blender"

        self.setup_ui()

    def setup_ui(self):
        style = tb.Style("darkly")

        # Queue list
        frame_top = tb.LabelFrame(self.root, text="Render Queue")
        frame_top.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.file_list = tk.Listbox(frame_top, bg="#222", fg="white", selectbackground="#555", height=10)
        self.file_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        self.file_list.drop_target_register(DND_FILES)
        self.file_list.dnd_bind("<<Drop>>", self.drop_file)

        scrollbar = tk.Scrollbar(frame_top)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.file_list.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.file_list.yview)

        # Buttons
        frame_btn = tb.Frame(self.root)
        frame_btn.pack(pady=5)
        tb.Button(frame_btn, text="➕ Add Blend", bootstyle=PRIMARY, command=self.add_blend).pack(side=tk.LEFT, padx=5)
        tb.Button(frame_btn, text="🗑 Remove by ID", bootstyle=DANGER, command=self.remove_by_id).pack(side=tk.LEFT, padx=5)
        tb.Button(frame_btn, text="🔄 Retry by ID", bootstyle=WARNING, command=self.retry_by_id).pack(side=tk.LEFT, padx=5)
        tb.Button(frame_btn, text="🔍 Inspect", bootstyle=INFO, command=self.inspect_selected).pack(side=tk.LEFT, padx=5)

        # Render Settings
        frame_settings = tb.LabelFrame(self.root, text="Render Settings")
        frame_settings.pack(fill=tk.X, padx=10, pady=10)

        tb.Label(frame_settings, text="Start Frame:").grid(row=0, column=0, sticky="e")
        self.start_entry = tb.Entry(frame_settings, width=10)
        self.start_entry.grid(row=0, column=1, sticky="w", padx=5)

        tb.Label(frame_settings, text="End Frame:").grid(row=0, column=2, sticky="e")
        self.end_entry = tb.Entry(frame_settings, width=10)
        self.end_entry.grid(row=0, column=3, sticky="w", padx=5)

        tb.Label(frame_settings, text="Step:").grid(row=0, column=4, sticky="e")
        self.step_entry = tb.Entry(frame_settings, width=10)
        self.step_entry.grid(row=0, column=5, sticky="w", padx=5)

        self.use_nodes_var = tk.BooleanVar()
        self.use_nodes_check = tb.Checkbutton(
            frame_settings, text="Use Nodes",
            variable=self.use_nodes_var, bootstyle="round-toggle"
        )
        self.use_nodes_check.grid(row=0, column=6, padx=10)

        # Inspect Output
        frame_meta = tb.LabelFrame(self.root, text="Inspect Output & Metadata")
        frame_meta.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.meta_text = tk.Text(frame_meta, bg="#111", fg="lightgreen", height=8)
        self.meta_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Render Controls
        frame_ctrl = tb.Frame(self.root)
        frame_ctrl.pack(pady=10)
        tb.Button(frame_ctrl, text="▶ Start Queue", bootstyle=SUCCESS, command=self.start_queue).pack(side=tk.LEFT, padx=5)
        tb.Button(frame_ctrl, text="⏹ Stop Queue", bootstyle=SECONDARY, command=self.stop_queue).pack(side=tk.LEFT, padx=5)

        # Progress & ETA
        self.progress = tb.Progressbar(self.root, bootstyle=SUCCESS, length=500)
        self.progress.pack(pady=5)
        self.eta_label = tb.Label(self.root, text="ETA job: --s | Total ETA: --s")
        self.eta_label.pack()

        # Status
        self.status_label = tb.Label(self.root, text="Status: Idle")
        self.status_label.pack(fill=tk.X, padx=10, pady=5)

        # Footer
        footer = tb.Label(self.root,
                          text="Made by Dwiky Gilang Imrodhani  |  https://github.com/dwikygilang",
                          bootstyle="secondary")
        footer.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=5)

    # ==============================
    # Drag & Drop
    # ==============================
    def drop_file(self, event):
        files = self.root.splitlist(event.data)
        for f in files:
            if f.endswith(".blend"):
                self.queue.append({"file": f, "meta": None, "status": "Pending"})
        self.refresh_list()

    # ==============================
    # Queue Functions
    # ==============================
    def add_blend(self):
        file = filedialog.askopenfilename(filetypes=[("Blender Files", "*.blend")])
        if file:
            self.queue.append({"file": file, "meta": None, "status": "Pending"})
            self.refresh_list()

    def remove_by_id(self):
        idx = self.simple_input("Enter ID to remove:")
        if idx and idx.isdigit():
            idx = int(idx) - 1
            if 0 <= idx < len(self.queue):
                self.queue.pop(idx)
                self.refresh_list()

    def retry_by_id(self):
        idx = self.simple_input("Enter ID to retry:")
        if idx and idx.isdigit():
            idx = int(idx) - 1
            if 0 <= idx < len(self.queue):
                job = self.queue[idx].copy()
                job["status"] = "Pending"
                self.queue.append(job)
                self.refresh_list()

    def refresh_list(self):
        self.file_list.delete(0, tk.END)
        for i, job in enumerate(self.queue, start=1):
            base = os.path.basename(job["file"])
            status = job.get("status", "Pending")
            if job["meta"]:
                m = job["meta"]
                desc = f"{i}. {base} | {m['frame_start']}-{m['frame_end']} step {m['frame_step']} | Nodes {'✅' if m['use_nodes'] else '❌'} | {status}"
            else:
                desc = f"{i}. {base} | {status}"
            self.file_list.insert(tk.END, desc)

    # ==============================
    # Inspect
    # ==============================
    def inspect_selected(self):
        sel = self.file_list.curselection()
        if not sel:
            messagebox.showwarning("Warning", "Please select a .blend file!")
            return
        idx = sel[0]
        job = self.queue[idx]
        data = inspect_blend(job["file"], self.blender_exec)
        if data:
            job["meta"] = data
            self.start_entry.delete(0, tk.END)
            self.start_entry.insert(0, data["frame_start"])
            self.end_entry.delete(0, tk.END)
            self.end_entry.insert(0, data["frame_end"])
            self.step_entry.delete(0, tk.END)
            self.step_entry.insert(0, data["frame_step"])
            self.use_nodes_var.set(data["use_nodes"])
            self.meta_text.delete("1.0", tk.END)
            self.meta_text.insert(tk.END, json.dumps(data, indent=2))
            self.status_label.config(text=f"Status: Inspected {os.path.basename(job['file'])} ✅")
            self.refresh_list()
        else:
            messagebox.showerror("Error", "Failed to inspect blend file!")

    # ==============================
    # Render Queue
    # ==============================
    def start_queue(self):
        if self.is_rendering:
            return
        if not self.queue:
            messagebox.showwarning("Warning", "Queue is empty!")
            return
        self.is_rendering = True
        self.status_label.config(text="Status: Rendering...")
        self.root.after(100, self.render_next)

    def stop_queue(self):
        self.is_rendering = False
        self.status_label.config(text="Status: Stopped ❌")

    def render_next(self):
        if not self.is_rendering:
            return

        job = None
        for j in self.queue:
            if j.get("status") == "Pending":
                job = j
                break

        if not job:
            self.is_rendering = False
            self.status_label.config(text="Status: Done ✅")
            self.eta_label.config(text="ETA: Finished")
            return

        job["status"] = "Rendering"
        self.refresh_list()

        meta = job["meta"] or {
            "frame_start": int(self.start_entry.get()),
            "frame_end": int(self.end_entry.get()),
            "frame_step": int(self.step_entry.get() or 1),
            "use_nodes": self.use_nodes_var.get()
        }

        start = int(meta["frame_start"])
        end = int(meta["frame_end"])
        step = int(meta["frame_step"])
        total_frames = ((end - start) // step) + 1

        self.progress["maximum"] = total_frames
        self.progress["value"] = 0

        job["start_time"] = time.time()
        job["frames_done"] = 0
        job["total_frames"] = total_frames

        def update_frame_cb(frame_num):
            job["frames_done"] += 1
            self.progress["value"] = job["frames_done"]
            self.status_label.config(
                text=f"Rendering {os.path.basename(job['file'])} | Frame {frame_num}/{end}"
            )

            # ETA per-job
            elapsed = time.time() - job["start_time"]
            avg_frame = elapsed / job["frames_done"]
            eta_job = avg_frame * (total_frames - job["frames_done"])

            # Total ETA
            total_remaining_frames = (total_frames - job["frames_done"])
            for j in self.queue:
                if j.get("status") == "Pending" and j.get("meta"):
                    s = j["meta"]["frame_start"]
                    e = j["meta"]["frame_end"]
                    st = j["meta"]["frame_step"]
                    total_remaining_frames += ((e - s) // st + 1)
            total_eta = avg_frame * total_remaining_frames

            self.eta_label.config(
                text=f"ETA job: {eta_job:.1f}s | Total ETA: {total_eta:.1f}s"
            )

        def worker():
            code = render_job(job["file"], start, end, step, self.blender_exec, update_frame_cb)
            job["status"] = "Done" if code == 0 else "Failed"
            self.save_log({
                "file": job["file"],
                "status": job["status"],
                "start": start,
                "end": end,
                "step": step,
                "use_nodes": meta["use_nodes"],
                "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            self.refresh_list()
            self.root.after(100, self.render_next)

        threading.Thread(target=worker, daemon=True).start()

    # ==============================
    # Helper
    # ==============================
    def simple_input(self, prompt):
        win = tb.Toplevel()
        win.title("Input")
        tb.Label(win, text=prompt).pack(padx=10, pady=10)
        entry = tb.Entry(win)
        entry.pack(padx=10, pady=5)
        result = []
        def submit():
            result.append(entry.get())
            win.destroy()
        tb.Button(win, text="OK", bootstyle=PRIMARY, command=submit).pack(pady=5)
        win.grab_set()
        win.wait_window()
        return result[0] if result else None

    def save_log(self, entry):
        log_file = "blender_queue.json"
        logs = []
        if os.path.exists(log_file):
            with open(log_file, "r") as f:
                try:
                    logs = json.load(f)
                except:
                    logs = []
        logs.append(entry)
        with open(log_file, "w") as f:
            json.dump(logs, f, indent=2)

# ==============================
# Run
# ==============================
if __name__ == "__main__":
    app = TkinterDnD.Tk()
    BlenderQueueApp(app)
    app.mainloop()
