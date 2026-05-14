#!/usr/bin/env python3
import argparse
import json
import math
import hashlib
import sys
import re
import os
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("Error: Pillow is required. Install it with:  pip install Pillow")
    sys.exit(1)

SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tga"}

def natural_sort_key(s):
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r"(\d+)", str(s))]

def trim_alpha(img):
    bbox = img.getbbox()
    return (img.crop(bbox), (bbox[0], bbox[1])) if bbox else (img, (0, 0))

def pack_shelves(items, max_w, padding):
    """Shelf packing algorithm that returns placements and height used."""
    shelves = [] # [x_ptr, y_ptr, shelf_h]
    placements = []
    
    for item in items:
        sw, sh = item['img'].width + padding, item['img'].height + padding
        placed = False
        for shelf in shelves:
            if shelf[0] + sw <= max_w:
                placements.append((item, shelf[0], shelf[1]))
                shelf[0] += sw
                placed = True
                break
        if not placed:
            y_start = shelves[-1][1] + shelves[-1][2] if shelves else 0
            # Check if this new shelf exceeds max height? Handled by the caller.
            shelves.append([sw, y_start, sh])
            placements.append((item, 0, y_start))
            
    total_h = shelves[-1][1] + shelves[-1][2] if shelves else 0
    return placements, total_h

def run_sprites(args):
    folder = Path(args.folder)
    files = [p for p in folder.glob("**/*") if p.suffix.lower() in SUPPORTED_EXTS]
    files.sort(key=lambda p: natural_sort_key(p.name))
    
    if not files:
        print(f"No images found in {folder}!"); return

    # Load and prep all images
    loaded_items = []
    for p in files:
        img = Image.open(p).convert("RGBA")
        ow, oh = img.size
        ox, oy = (0, 0)
        if args.trim:
            img, (ox, oy) = trim_alpha(img)
        loaded_items.append({"p": p, "img": img, "ow": ow, "oh": oh, "ox": ox, "oy": oy})

    # Sort for better packing
    loaded_items.sort(key=lambda s: s["img"].height, reverse=True)

    # Multi-packing logic
    remaining = loaded_items
    page_index = 0
    
    while remaining:
        page_items = []
        current_w = args.max_size
        
        # Greedy check: how many items fit in one page?
        # For simplicity in this CLI, we fill one page at a time
        placements, total_h = pack_shelves(remaining, args.max_size, args.padding)
        
        # If total_h > max_size, we need to subset the items
        if total_h > args.max_size:
            # Binary search or iterative reduction would go here. 
            # For this script, we'll slice items until they fit.
            while total_h > args.max_size and len(placements) > 1:
                remaining_count = len(placements) - 1
                placements, total_h = pack_shelves(remaining[:remaining_count], args.max_size, args.padding)
        
        # Finalize this page
        current_page_items = remaining[:len(placements)]
        remaining = remaining[len(placements):]
        
        # Render the page
        canvas_h = total_h
        canvas_w = args.max_size if args.power_of_two else max(p[1] + p[0]['img'].width for p in placements)
        
        if args.power_of_two:
            canvas_h = 2**math.ceil(math.log2(canvas_h))
            canvas_w = 2**math.ceil(math.log2(canvas_w))

        atlas_img = Image.new("RGBA", (canvas_w, canvas_h), (0,0,0,0))
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

        # Handle Animations
        animations = {}
        if args.group_by_folder:
            for fname in frame_dict.keys():
                prefix = "".join(re.split(r'(\d+)', fname)[0])
                animations.setdefault(prefix, []).append(fname)

        # Output filenames
        suffix = f"-{page_index}" if page_index > 0 or len(remaining) > 0 else ""
        out_name = (args.output or folder.name) + suffix
        json_path = out_name + ".json"
        
        # Format compression (WebP Squoosh)
        img_ext = ".webp" if args.webp else ".png"
        img_path = out_name + img_ext
        
        if args.webp:
            atlas_img.save(img_path, "WEBP", quality=args.quality)
        else:
            atlas_img.save(img_path, "PNG")

        # Metadata
        data = {
            "frames": frame_dict,
            "animations": animations,
            "meta": {
                "app": "Gemini-Pixi-Packer",
                "image": Path(img_path).name,
                "format": "RGBA8888",
                "size": {"w": atlas_img.width, "h": atlas_img.height},
                "scale": "1"
            }
        }

        with open(json_path, "w") as f:
            json.dump(data, f, indent=4 if args.pretty else None)
        
        print(f"Created Page {page_index}: {img_path} ({len(placements)} sprites)")
        page_index += 1

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PixiJS Multi-Packer & Squoosher")
    subparsers = parser.add_subparsers(dest="command", required=True)

    f_parser = subparsers.add_parser("sprites")
    f_parser.add_argument("folder")
    f_parser.add_argument("--padding", type=int, default=2)
    f_parser.add_argument("--max-size", type=int, default=2048, help="Max texture size (4096, 2048, etc)")
    f_parser.add_argument("--trim", action="store_true")
    f_parser.add_argument("--webp", action="store_true", help="Export as compressed WebP")
    f_parser.add_argument("--quality", type=int, default=80, help="WebP quality (1-100)")
    f_parser.add_argument("--power-of-two", action="store_true")
    f_parser.add_argument("--group-by-folder", action="store_true")
    f_parser.add_argument("--output", "-o")
    f_parser.add_argument("--pretty", action="store_true")
    
    f_parser.set_defaults(func=run_sprites)
    args = parser.parse_args()
    args.func(args)