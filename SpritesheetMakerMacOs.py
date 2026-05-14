import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import json
import math
import sys
import re
from pathlib import Path
from PIL import Image

# --- ORIGINAL LOGIC ENGINE ---
SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tga"}

def natural_sort_key(s):
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r"(\d+)", str(s))]

def trim_alpha(img):
    bbox = img.getbbox()
    return (img.crop(bbox), (bbox[0], bbox[1])) if bbox else (img, (0, 0))

def pack_tight(items, padding):
    items.sort(key=lambda s: s["img"].height, reverse=True)
    total_area = sum((s["img"].width + padding) * (s["img"].height + padding) for s in items)
    target_width = max(max(s["img"].width for s in items), int(math.sqrt(total_area)))
    
    shelves = [] 
    placements = []
    
    for item in items:
        sw, sh = item['img'].width + padding, item['img'].height + padding
        placed = False
        for shelf in shelves:
            if shelf[0] + sw <= target_width:
                placements.append((item, shelf[0], shelf[1]))
                shelf[0] += sw
                placed = True
                break
        if not placed:
            y_start = shelves[-1][1] + shelves[-1][2] if shelves else 0
            shelves.append([sw, y_start, sh])
            placements.append((item, 0, y_start))
            
    canvas_h = shelves[-1][1] + shelves[-1][2]
    canvas_w = max(shelf[0] for shelf in shelves)
    return placements, canvas_w, canvas_h

def process_sprites(folder_path, padding, quality, trim, output_name):
    folder = Path(folder_path)
    files = [p for p in folder.glob("**/*") if p.suffix.lower() in SUPPORTED_EXTS]
    files.sort(key=lambda p: natural_sort_key(p.name))
    
    if not files:
        raise Exception("No images found in the selected folder.")

    loaded_items = []
    for p in files:
        img = Image.open(p).convert("RGBA")
        if trim:
            trimmed_img, (ox, oy) = trim_alpha(img)
            loaded_items.append({"p": p, "img": trimmed_img, "ow": img.width, "oh": img.height, "ox": ox, "oy": oy})
        else:
            loaded_items.append({"p": p, "img": img, "ow": img.width, "oh": img.height, "ox": 0, "oy": 0})

    placements, cw, ch = pack_tight(loaded_items, padding)
    atlas_img = Image.new("RGBA", (cw, ch), (0,0,0,0))
    frame_dict = {}
    
    for item, x, y in placements:
        atlas_img.paste(item['img'], (x, y))
        frame_dict[item['p'].name] = {
            "frame": {"x": x, "y": y, "w": item['img'].width, "h": item['img'].height},
            "rotated": False,
            "trimmed": item['ox'] > 0 or item['oy'] > 0,
            "spriteSourceSize": {"x": item['ox'], "y": item['oy'], "w": item['img'].width, "h": item['img'].height},
            "sourceSize": {"w": item['ow'], "h": item['oh']}
        }

    out_base = str(folder / (output_name or "atlas"))
    img_path = out_base + ".webp"
    atlas_img.save(img_path, "WEBP", quality=quality, method=6)
    
    with open(out_base + ".json", "w") as f:
        json.dump({"frames": frame_dict, "meta": {"app": "Mac-Pixi-Packer", "image": Path(img_path).name, "size": {"w": cw, "h": ch}}}, f, indent=4)
    
    return f"Success! Created {cw}x{ch} atlas."

# --- GUI INTERFACE ---
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Mac Spritesheet Tool")
        self.root.geometry("400x350")
        
        # Folder Selection
        tk.Label(root, text="Source Folder:").pack(pady=(10, 0))
        self.folder_var = tk.StringVar()
        tk.Entry(root, textvariable=self.folder_var, width=40).pack()
        tk.Button(root, text="Browse", command=self.browse_folder).pack(pady=5)
        
        # Output Name
        tk.Label(root, text="Output Name:").pack()
        self.output_var = tk.StringVar(value="atlas")
        tk.Entry(root, textvariable=self.output_var).pack()

        # Settings
        self.trim_var = tk.BooleanVar(value=True)
        tk.Checkbutton(root, text="Trim Alpha", variable=self.trim_var).pack(pady=5)

        tk.Label(root, text="Padding (pixels):").pack()
        self.padding_scale = tk.Scale(root, from_=0, to=20, orient="horizontal")
        self.padding_scale.set(1)
        self.padding_scale.pack()

        tk.Label(root, text="WebP Quality:").pack()
        self.quality_scale = tk.Scale(root, from_=1, to=100, orient="horizontal")
        self.quality_scale.set(60)
        self.quality_scale.pack()

        # Run Button
        self.run_btn = tk.Button(root, text="Generate Spritesheet", command=self.run, bg="#007AFF", fg="black")
        self.run_btn.pack(pady=20)

    def browse_folder(self):
        path = filedialog.askdirectory()
        if path: self.folder_var.set(path)

    def run(self):
        try:
            msg = process_sprites(
                self.folder_var.get(), 
                self.padding_scale.get(), 
                self.quality_scale.get(), 
                self.trim_var.get(), 
                self.output_var.get()
            )
            messagebox.showinfo("Done", msg)
        except Exception as e:
            messagebox.showerror("Error", str(e))

if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()