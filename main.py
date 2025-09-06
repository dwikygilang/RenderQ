import os
import subprocess
import json
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# ==============================
# Blender Inspector
# ==============================
def inspect_blend(blend_file):
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
print(json.dumps(data))
"""
    try:
        result = subprocess.run(
            ["blender", "-b", blend_file, "--python-expr", code],
            capture_output=True, text=True
        )
        for line in result.stdout.splitlines():
            if line.startswith("{") and line.endswith("}"):
                return json.loads(line)
    except Exception as e:
        print("Inspect error:", e)
    return None

# ==============================
# Main App
# ==============================
class BlenderQueueApp:
    def __init__(self, root):
        self.root = root
        self.root.title("🎬 Blender Render Queue Manager")
        self.root.geometry("850x600")
        self.root.configure(bg="#2b2b2b")

        self.queue = []
        self.selected_blend = None
        self.is_rendering = False

        self.setup_ui()

    def setup_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TButton", background="#444", foreground="white", padding=6)
        style.map("TButton", background=[("active", "#666")])
        style.configure("TLabel", background="#2b2b2b", foreground="white")

        # Frame atas (file list + tombol)
        frame_top = tk.Frame(self.root, bg="#2b2b2b")
        frame_top.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.file_list = tk.Listbox(frame_top, bg="#1e1e1e", fg="white", selectbackground="#444", height=12)
        self.file_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        scrollbar = tk.Scrollbar(frame_top)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.file_list.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.file_list.yview)

        frame_btn = tk.Frame(self.root, bg="#2b2b2b")
        frame_btn.pack(pady=5)
        ttk.Button(frame_btn, text="➕ Add Blend", command=self.add_blend).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_btn, text="🗑 Remove by ID", command=self.remove_by_id).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_btn, text="🔄 Retry by ID", command=self.retry_by_id).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_btn, text="🔍 Inspect", command=self.inspect_selected).pack(side=tk.LEFT, padx=5)

        # Render Settings
        frame_settings = tk.LabelFrame(self.root, text="Render Settings", bg="#2b2b2b", fg="white")
        frame_settings.pack(fill=tk.X, padx=10, pady=10)

        tk.Label(frame_settings, text="Output Folder:", bg="#2b2b2b", fg="white").grid(row=0, column=0, sticky="e")
        self.output_entry = tk.Entry(frame_settings, width=50)
        self.output_entry.grid(row=0, column=1, padx=5, pady=5)

        tk.Label(frame_settings, text="Start Frame:", bg="#2b2b2b", fg="white").grid(row=1, column=0, sticky="e")
        self.start_entry = tk.Entry(frame_settings, width=10)
        self.start_entry.grid(row=1, column=1, sticky="w", padx=5)

        tk.Label(frame_settings, text="End Frame:", bg="#2b2b2b", fg="white").grid(row=1, column=1, sticky="e", padx=(100, 0))
        self.end_entry = tk.Entry(frame_settings, width=10)
        self.end_entry.grid(row=1, column=1, sticky="e", padx=(0, 5))

        tk.Label(frame_settings, text="Step:", bg="#2b2b2b", fg="white").grid(row=1, column=2, sticky="e")
        self.step_entry = tk.Entry(frame_settings, width=10)
        self.step_entry.grid(row=1, column=3, sticky="w", padx=5)

        self.use_nodes_var = tk.BooleanVar()
        self.use_nodes_check = tk.Checkbutton(frame_settings, text="Use Nodes", variable=self.use_nodes_var, bg="#2b2b2b", fg="white", selectcolor="#444")
        self.use_nodes_check.grid(row=2, column=1, sticky="w")

        # Render Controls
        frame_ctrl = tk.Frame(self.root, bg="#2b2b2b")
        frame_ctrl.pack(pady=10)
        ttk.Button(frame_ctrl, text="▶ Start Queue", command=self.start_queue).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_ctrl, text="⏹ Stop Queue", command=self.stop_queue).pack(side=tk.LEFT, padx=5)

        # Status
        self.status_label = tk.Label(self.root, text="Status: Idle", anchor="w", bg="#2b2b2b", fg="lightgray")
        self.status_label.pack(fill=tk.X, padx=10, pady=5)

        # Footer
        footer = tk.Label(self.root, text="Made by Dwiky & ChatGPT  |  https://github.com/dwikygilang",
                          bg="#2b2b2b", fg="gray", anchor="w")
        footer.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=5)

    # ==============================
    # Queue Functions
    # ==============================
    def add_blend(self):
        file = filedialog.askopenfilename(filetypes=[("Blender Files", "*.blend")])
        if file:
            self.queue.append(file)
            self.file_list.insert(tk.END, f"{len(self.queue)}. {os.path.basename(file)}")

    def remove_by_id(self):
        idx = simple_input("Enter ID to remove:")
        if idx and idx.isdigit():
            idx = int(idx) - 1
            if 0 <= idx < len(self.queue):
                self.queue.pop(idx)
                self.refresh_list()

    def retry_by_id(self):
        idx = simple_input("Enter ID to retry:")
        if idx and idx.isdigit():
            idx = int(idx) - 1
            if 0 <= idx < len(self.queue):
                blend = self.queue[idx]
                self.queue.append(blend)
                self.refresh_list()

    def refresh_list(self):
        self.file_list.delete(0, tk.END)
        for i, f in enumerate(self.queue, start=1):
            self.file_list.insert(tk.END, f"{i}. {os.path.basename(f)}")

    # ==============================
    # Inspect
    # ==============================
    def inspect_selected(self):
        sel = self.file_list.curselection()
        if not sel:
            messagebox.showwarning("Warning", "Please select a .blend file!")
            return
        idx = sel[0]
        blend_file = self.queue[idx]
        data = inspect_blend(blend_file)
        if data:
            self.output_entry.delete(0, tk.END)
            self.output_entry.insert(0, data["output_path"])
            self.start_entry.delete(0, tk.END)
            self.start_entry.insert(0, data["frame_start"])
            self.end_entry.delete(0, tk.END)
            self.end_entry.insert(0, data["frame_end"])
            self.step_entry.delete(0, tk.END)
            self.step_entry.insert(0, data["frame_step"])
            self.use_nodes_var.set(data["use_nodes"])
            self.status_label.config(text=f"Status: Inspected {os.path.basename(blend_file)} ✅")
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
        self.root.after(1000, self.render_next)

    def stop_queue(self):
        self.is_rendering = False
        self.status_label.config(text="Status: Stopped ❌")

    def render_next(self):
        if not self.is_rendering or not self.queue:
            self.is_rendering = False
            self.status_label.config(text="Status: Done ✅")
            return

        blend_file = self.queue.pop(0)
        self.refresh_list()

        # Ambil setting dari GUI
        output_path = self.output_entry.get()
        start = self.start_entry.get()
        end = self.end_entry.get()
        step = self.step_entry.get()

        cmd = [
            "blender", "-b", blend_file,
            "-o", output_path,
            "-s", start, "-e", end, "-j", step,
            "-a"
        ]
        subprocess.run(cmd)

        self.root.after(1000, self.render_next)

# ==============================
# Helper Input Dialog
# ==============================
def simple_input(prompt):
    win = tk.Toplevel()
    win.title("Input")
    tk.Label(win, text=prompt).pack(padx=10, pady=10)
    entry = tk.Entry(win)
    entry.pack(padx=10, pady=5)
    result = []
    def submit():
        result.append(entry.get())
        win.destroy()
    tk.Button(win, text="OK", command=submit).pack(pady=5)
    win.grab_set()
    win.wait_window()
    return result[0] if result else None

# ==============================
# Run
# ==============================
if __name__ == "__main__":
    root = tk.Tk()
    app = BlenderQueueApp(root)
    root.mainloop()
