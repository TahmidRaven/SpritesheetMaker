#!/usr/bin/env python3
"""
spritesheet_to_json.py — CLI tool for spritesheet ↔ JSON atlas conversion.

SUB-COMMANDS
  sheet    Extract frame data from a single spritesheet image → JSON
  sprites  Pack a folder of individual sprite images → JSON atlas (+ optional sheet)
"""

import argparse
import json
import math
import os
import re
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("Error: Pillow is required. Install it with:  pip install Pillow")
    sys.exit(1)

SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tga"}

# ══════════════════════════════════════════════════════════════════════════════
# Shared Helpers
# ══════════════════════════════════════════════════════════════════════════════

def natural_sort_key(s):
    """Sort strings with numbers naturally: frame2 < frame10."""
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r"(\d+)", str(s))]

def parse_animations(animation_args):
    """Parse 'idle:0-3' strings into {name: [frame_indices]}."""
    animations = {}
    for anim in animation_args:
        parts = anim.split(":")
        if len(parts) < 2: continue
        name, range_str = parts[0], parts[1]
        if "-" in range_str:
            a, b = range_str.split("-", 1)
            animations[name] = list(range(int(a), int(b) + 1))
        else:
            animations[name] = [int(range_str)]
    return animations

# ══════════════════════════════════════════════════════════════════════════════
# SHEET Mode (Extracting from existing sheet)
# ══════════════════════════════════════════════════════════════════════════════

def extract_grid_frames(img, cols, rows, padding=0, margin=0):
    w, h = img.size
    cell_w, cell_h = (w - margin * 2) // cols, (h - margin * 2) // rows
    fw, fh = cell_w - padding * 2, cell_h - padding * 2
    frames = []
    for r in range(rows):
        for c in range(cols):
            frames.append({
                "frame": len(frames), 
                "x": margin + c * cell_w + padding, 
                "y": margin + r * cell_h + padding, 
                "w": fw, "h": fh
            })
    return frames, fw, fh

def run_sheet(args):
    img = Image.open(args.image)
    if args.cols:
        frames, fw, fh = extract_grid_frames(img, args.cols, args.rows, args.padding, args.margin)
    else:
        sys.exit("Error: Please specify --cols or use --auto (auto not implemented in this snippet for brevity)")

    for f in frames: f["name"] = f"{args.prefix}{f['frame']:04d}"
    
    data = {
        "meta": {"image": Path(args.image).name, "size": {"w": img.width, "h": img.height}, "frameCount": len(frames)},
        "frames": frames
    }
    
    out = args.output or (Path(args.image).stem + ".json")
    _write_json(data, out, args.pretty)
    print(f"Saved JSON: {out}")

# ══════════════════════════════════════════════════════════════════════════════
# SPRITES Mode (Packing folder into sheet)
# ══════════════════════════════════════════════════════════════════════════════

def trim_alpha(img):
    bbox = img.getbbox()
    return (img.crop(bbox), (bbox[0], bbox[1])) if bbox else (img, (0, 0))

def pack_sprites(sprite_paths, padding=2, pot=False, trim=False):
    loaded = []
    for p in sprite_paths:
        img = Image.open(p).convert("RGBA")
        ow, oh = img.size
        ox, oy = (0, 0)
        if trim: img, (ox, oy) = trim_alpha(img)
        loaded.append({"p": p, "img": img, "ow": ow, "oh": oh, "ox": ox, "oy": oy})

    # Sort by height for shelf packing
    loaded.sort(key=lambda s: s["img"].height, reverse=True)
    
    # Calculate rough width
    total_area = sum(s["img"].width * s["img"].height for s in loaded)
    canvas_w = max(max(s["img"].width for s in loaded), int(math.sqrt(total_area) * 1.2))
    
    shelves = [] # [x_ptr, y_ptr, shelf_h]
    placements = []
    
    for s in loaded:
        sw, sh = s["img"].width + padding, s["img"].height + padding
        placed = False
        for shelf in shelves:
            if shelf[0] + sw <= canvas_w:
                placements.append((s, shelf[0], shelf[1]))
                shelf[0] += sw
                placed = True
                break
        if not placed:
            y_start = shelves[-1][1] + shelves[-1][2] if shelves else 0
            shelves.append([sw, y_start, sh])
            placements.append((s, 0, y_start))

    canvas_h = shelves[-1][1] + shelves[-1][2]
    if pot:
        canvas_w = 2**math.ceil(math.log2(canvas_w))
        canvas_h = 2**math.ceil(math.log2(canvas_h))

    atlas_img = Image.new("RGBA", (canvas_w, canvas_h), (0,0,0,0))
    frame_data = []
    for s, x, y in placements:
        atlas_img.paste(s["img"], (x, y))
        frame_data.append({
            "filename": s["p"].name,
            "frame": {"x": x, "y": y, "w": s["img"].width, "h": s["img"].height},
            "sourceSize": {"w": s["ow"], "h": s["oh"]},
            "spriteSourceSize": {"x": s["ox"], "y": s["oy"], "w": s["img"].width, "h": s["img"].height}
        })
    
    return atlas_img, frame_data

def run_sprites(args):
    folder = Path(args.folder)
    files = [p for p in folder.glob("**/*") if p.suffix.lower() in SUPPORTED_EXTS]
    files.sort(key=natural_sort_key)
    
    print(f"Packing {len(files)} sprites...")
    atlas_img, frames = pack_sprites(files, padding=args.padding, pot=args.power_of_two, trim=args.trim)
    
    # Handle animations by folder name
    animations = {}
    if args.group_by_folder:
        for i, f in enumerate(frames):
            folder_name = Path(files[i]).parent.name
            if folder_name != folder.name:
                animations.setdefault(folder_name, []).append(i)

    output_base = args.output or folder.name
    json_path = output_base if output_base.endswith(".json") else output_base + ".json"
    img_path = str(Path(json_path).with_suffix(".png"))
    
    atlas_img.save(img_path)
    data = {
        "meta": {"image": Path(img_path).name, "size": {"w": atlas_img.width, "h": atlas_img.height}},
        "frames": frames,
    }
    if animations: data["animations"] = animations

    _write_json(data, json_path, args.pretty)
    print(f"Success! Created {img_path} and {json_path}")

def _write_json(data, path, pretty):
    with open(path, "w") as f:
        json.dump(data, f, indent=4 if pretty else None)

# ══════════════════════════════════════════════════════════════════════════════
# Entry Point
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Spritesheet Utility")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: sheet
    s_parser = subparsers.add_parser("sheet")
    s_parser.add_argument("image")
    s_parser.add_argument("--cols", type=int)
    s_parser.add_argument("--rows", type=int, default=1)
    s_parser.add_argument("--padding", type=int, default=0)
    s_parser.add_argument("--margin", type=int, default=0)
    s_parser.add_argument("--prefix", default="frame_")
    s_parser.add_argument("--output", "-o")
    s_parser.add_argument("--pretty", action="store_true")
    s_parser.set_defaults(func=run_sheet)

    # Subcommand: sprites
    f_parser = subparsers.add_parser("sprites")
    f_parser.add_argument("folder")
    f_parser.add_argument("--padding", type=int, default=2)
    f_parser.add_argument("--trim", action="store_true", help="Remove transparent whitespace")
    f_parser.add_argument("--power-of-two", action="store_true")
    f_parser.add_argument("--group-by-folder", action="store_true")
    f_parser.add_argument("--output", "-o")
    f_parser.add_argument("--pretty", action="store_true")
    f_parser.set_defaults(func=run_sprites)

    args = parser.parse_args()
    args.func(args)