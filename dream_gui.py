import os
import sys
import threading
import queue

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk

import trimesh
from trimesh.viewer import windowed
import numpy as np

# DreamGaussian + Voxel support imports
import subprocess
import shutil
import platform

# ---- CONFIG ----
DREAMGAUSSIAN_SCRIPT = os.path.join(os.getcwd(), "run_dreamgaussian.py")
MAGICAVOXEL_PATH = r"C:\Program Files\MagicaVoxel\MagicaVoxel.exe"  # Change if needed

# ---- UTILS ----

def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)
    return path

def run_dreamgaussian(text_prompt, image_path, out_dir, mesh_name="dreamasset", hd=True, config_preset="auto"):
    config_dir = os.path.join(os.getcwd(), "configs")
    # Live config selection
    if config_preset and config_preset != "auto":
        config = os.path.join(config_dir, config_preset)
    else:
        if text_prompt and image_path:
            config = os.path.join(config_dir, "imagedream.yaml")
        elif text_prompt:
            config = os.path.join(config_dir, "text.yaml")
        else:
            config = os.path.join(config_dir, "image.yaml")
    # Assemble command to run DreamGaussian
    args = [
        sys.executable, DREAMGAUSSIAN_SCRIPT,
        "--config", config,
        "--output_dir", out_dir,
        "--name", mesh_name,
        "--hd" if hd else "--low"
    ]
    if text_prompt:
        args += ["--text", text_prompt]
    if image_path:
        args += ["--image", image_path]
    # Run and wait
    print("Running DreamGaussian with:", args)
    result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8")
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
        raise Exception("DreamGaussian failed!")
    # Output files: out_dir/mesh_name.obj, out_dir/mesh_name.png
    return os.path.join(out_dir, f"{mesh_name}.obj"), os.path.join(out_dir, f"{mesh_name}.png")

def obj_to_vox(obj_path, vox_path, resolution):
    try:
        from obj2vox import obj2vox
    except ImportError:
        raise Exception("You must install 'obj2vox' package (pip install obj2vox)!")
    print(f"Converting {obj_path} to {vox_path} at resolution {resolution}...")
    obj2vox(obj_path, vox_path, grid=resolution)
    return vox_path

def show_mesh_in_window(mesh_path):
    mesh = trimesh.load(mesh_path)
    windowed.SceneViewer(mesh)

# ---- MAIN GUI ----

class AssetGeneratorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("DreamGaussian 3D Asset Generator")
        self.geometry("1080x1080")
        self.resizable(True, True)
        self.jobs = queue.Queue()
        self.preview_mesh_path = None

        # --- Variables ---
        self.text_prompt = tk.StringVar()
        self.image_path = tk.StringVar()
        self.voxel_mode = tk.BooleanVar(value=True)
        self.voxel_res = tk.IntVar(value=256)
        self.mesh_only = tk.BooleanVar(value=True)
        self.texture_only = tk.BooleanVar(value=False)
        self.mesh_and_texture = tk.BooleanVar(value=True)
        self.output_dir = tk.StringVar(value=os.getcwd())
        self.processing = False

        # --- UI ---
        self.setup_ui()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def setup_ui(self):
        # Configure grid for root window
        self.grid_columnconfigure(0, weight=1, minsize=400)
        self.grid_columnconfigure(1, weight=2, minsize=600)
        self.grid_rowconfigure(0, weight=3)
        self.grid_rowconfigure(1, weight=1)

        # LEFT CONTROL PANEL
        controls_frame = ttk.Frame(self)
        controls_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        controls_frame.grid_columnconfigure(0, weight=1)
        controls_frame.grid_rowconfigure(0, weight=0)
        controls_frame.grid_rowconfigure(1, weight=0)
        controls_frame.grid_rowconfigure(2, weight=0)

        # --- Input Frame ---
        input_frame = ttk.LabelFrame(controls_frame, text="Prompt Inputs", padding=10)
        input_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        input_frame.grid_columnconfigure(1, weight=1)
        # Text Prompt
        ttk.Label(input_frame, text="Text Prompt:").grid(row=0, column=0, sticky="w", pady=2)
        self.text_entry = ttk.Entry(input_frame, textvariable=self.text_prompt)
        self.text_entry.grid(row=0, column=1, sticky="ew", padx=4, pady=2, columnspan=2)
        # Image Prompt
        ttk.Label(input_frame, text="Image Prompt:").grid(row=1, column=0, sticky="w", pady=2)
        self.image_entry = ttk.Entry(input_frame, textvariable=self.image_path)
        self.image_entry.grid(row=1, column=1, sticky="ew", padx=4, pady=2)
        browse_img_btn = ttk.Button(input_frame, text="Browse...", command=self.browse_image)
        browse_img_btn.grid(row=1, column=2, sticky="ew", padx=2, pady=2)

        # --- Options Frame ---
        options_frame = ttk.LabelFrame(controls_frame, text="Options", padding=10)
        options_frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        options_frame.grid_columnconfigure(1, weight=1)
        ttk.Label(options_frame, text="Voxel Resolution:").grid(row=0, column=0, sticky="w")
        voxel_res_menu = ttk.Combobox(options_frame, textvariable=self.voxel_res, values=(128, 256, 512), state="readonly")
        voxel_res_menu.grid(row=0, column=1, sticky="ew")
        self.voxel_checkbox = ttk.Checkbutton(options_frame, text="Export MicroVoxel (.vox)", variable=self.voxel_mode)
        self.voxel_checkbox.grid(row=1, column=0, columnspan=2, sticky="w")
        ttk.Label(options_frame, text="Output:").grid(row=2, column=0, sticky="w")
        ttk.Checkbutton(options_frame, text="Mesh (.obj)", variable=self.mesh_only).grid(row=2, column=1, sticky="w")
        ttk.Checkbutton(options_frame, text="Texture (.png)", variable=self.texture_only).grid(row=3, column=1, sticky="w")
        ttk.Checkbutton(options_frame, text="Both", variable=self.mesh_and_texture).grid(row=4, column=1, sticky="w")
        ttk.Label(options_frame, text="Output Folder:").grid(row=5, column=0, sticky="w")
        self.out_dir_entry = ttk.Entry(options_frame, textvariable=self.output_dir)
        self.out_dir_entry.grid(row=5, column=1, sticky="ew")
        ttk.Button(options_frame, text="Browse", command=self.browse_output).grid(row=5, column=2, padx=3)
        # --- Config Selection ---
        ttk.Label(options_frame, text="Config Preset:").grid(row=6, column=0, sticky="w")
        self.config_preset = tk.StringVar(value="auto")
        config_options = ["auto", "image.yaml", "image_sai.yaml", "imagedream.yaml", "text.yaml", "text_mv.yaml"]
        self.config_menu = ttk.Combobox(options_frame, textvariable=self.config_preset, values=config_options, state="readonly")
        self.config_menu.grid(row=6, column=1, sticky="ew")

        # --- Control Frame ---
        control_frame = ttk.LabelFrame(controls_frame, text="Control", padding=10)
        control_frame.grid(row=2, column=0, sticky="ew")
        control_frame.grid_columnconfigure(0, weight=1)
        control_frame.grid_columnconfigure(1, weight=1)
        ttk.Button(control_frame, text="Generate", command=self.enqueue_job).grid(row=0, column=0, padx=10, pady=5, sticky="ew")
        ttk.Button(control_frame, text="Quit", command=self.on_close).grid(row=0, column=1, padx=10, pady=5, sticky="ew")

        # RIGHT PREVIEW PANEL
        preview_frame = ttk.LabelFrame(self, text="Live 3D Preview", padding=10)
        preview_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        preview_frame.grid_rowconfigure(0, weight=1)
        preview_frame.grid_columnconfigure(0, weight=1)
        self.preview_label = ttk.Label(preview_frame, text="No preview yet.")
        self.preview_label.grid(row=0, column=0, sticky="nsew")
        ttk.Button(preview_frame, text="Open 3D Viewer", command=self.open_preview_window).grid(row=1, column=0, pady=5, sticky="ew")

        # BOTTOM JOB QUEUE (full width)
        job_frame = ttk.LabelFrame(self, text="Job Queue", padding=10)
        job_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(0,10))
        job_frame.grid_columnconfigure(0, weight=1)
        self.job_list = tk.Listbox(job_frame, height=1)
        self.job_list.grid(row=0, column=0, sticky="ew")

        self.after(200, self.poll_queue)

    def browse_image(self):
        img_path = filedialog.askopenfilename(title="Select image file", filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp")])
        if img_path:
            self.image_path.set(img_path)

    def browse_output(self):
        folder = filedialog.askdirectory(title="Select output folder")
        if folder:
            self.output_dir.set(folder)

    def enqueue_job(self):
        text = self.text_prompt.get().strip()
        img = self.image_path.get().strip()
        if not text and not img:
            messagebox.showwarning("No prompt", "Provide text and/or image prompt.")
            return
        out_dir = self.output_dir.get()
        mesh_name = f"dreamasset_{len(os.listdir(out_dir))}"
        job = (text, img, out_dir, mesh_name, self.mesh_only.get(), self.texture_only.get(), self.mesh_and_texture.get(), self.voxel_mode.get(), self.voxel_res.get())
        self.jobs.put(job)
        self.job_list.insert(tk.END, f"Job {self.job_list.size()+1}: {mesh_name}")
        if not self.processing:
            self.process_next_job()

    def poll_queue(self):
        if not self.processing and not self.jobs.empty():
            self.process_next_job()
        self.after(200, self.poll_queue)

    def process_next_job(self):
        if self.jobs.empty():
            return
        self.processing = True
        job = self.jobs.get()
        self.job_list.delete(0)
        t = threading.Thread(target=self.run_job, args=job)
        t.daemon = True
        t.start()

    def run_job(self, text, img, out_dir, mesh_name, mesh_only, texture_only, mesh_and_texture, voxel_mode, voxel_res):
        try:
            # Run DreamGaussian pipeline
            config_preset = self.config_preset.get() if hasattr(self, 'config_preset') else "auto"
            obj_path, tex_path = run_dreamgaussian(text, img, out_dir, mesh_name, hd=True, config_preset=config_preset)
            out_paths = [obj_path]
            if texture_only or mesh_and_texture:
                out_paths.append(tex_path)
            # If voxel mode: convert to .vox
            vox_path = None
            if voxel_mode:
                vox_path = os.path.join(out_dir, f"{mesh_name}_{voxel_res}.vox")
                obj_to_vox(obj_path, vox_path, voxel_res)
                out_paths.append(vox_path)
            # Preview OBJ (show progress!)
            self.preview_mesh_path = obj_path
            self.show_preview(obj_path)
            messagebox.showinfo("Success", f"Generation complete!\nFiles:\n" + "\n".join(out_paths))
        except Exception as ex:
            messagebox.showerror("Error", f"Job failed: {ex}")
        finally:
            self.processing = False

    def show_preview(self, mesh_path):
        try:
            mesh = trimesh.load(mesh_path)
            scene = mesh.scene()
            img = scene.save_image(resolution=[320, 320])
            if img:
                photo = ImageTk.PhotoImage(Image.open(trimesh.util.wrap_as_stream(img)))
                self.preview_label.config(image=photo)
                self.preview_label.image = photo
            else:
                self.preview_label.config(text="3D preview not available.")
        except Exception as e:
            self.preview_label.config(text=f"Preview error: {e}")

    def open_preview_window(self):
        if not self.preview_mesh_path:
            messagebox.showwarning("No mesh", "No mesh generated yet.")
            return
        show_mesh_in_window(self.preview_mesh_path)

    def on_close(self):
        self.destroy()

# ---- RUN ----

if __name__ == "__main__":
    try:
        app = AssetGeneratorApp()
        app.mainloop()
    except Exception as e:
        print("Error launching app:", e)
        input("Press any key to exit...")
