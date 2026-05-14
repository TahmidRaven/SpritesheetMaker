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
    """Sorts strings containing numbers naturally (e.g., frame2 before frame10)."""
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r"(\d+)", str(s))]

def trim_alpha(img):
    """Crops transparent borders and returns the new image and the offset."""
    bbox = img.getbbox()
    return (img.crop(bbox), (bbox[0], bbox[1])) if bbox else (img, (0, 0))

def pack_shelves(items, max_w, padding):
    """Shelf packing algorithm to organize sprites into rows."""
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
            shelves.append([sw, y_start, sh])
            placements.append((item, 0, y_start))
            
    total_h = shelves[-1][1] + shelves[-1][2] if shelves else 0
    return placements, total_h

def run_sprites(args):
    folder = Path(args.folder)
    # Recursively find images
    files = [p for p in folder.glob("**/*") if p.suffix.lower() in SUPPORTED_EXTS]
    files.sort(key=lambda p: natural_sort_key(p.name))
    
    if not files:
        print(f"Error: No images found in '{folder.absolute()}'.")
        print("Try using '.' as the path if you are already inside the image folder.")
        return

    # Prepare images
    loaded_items = []
    for p in files:
        img = Image.open(p).convert("RGBA")
        ow, oh = img.size
        ox, oy = (0, 0)
        if args.trim:
            img, (ox, oy) = trim_alpha(img)
        loaded_items.append({"p": p, "img": img, "ow": ow, "oh": oh, "ox": ox, "oy": oy})

    loaded_items.sort(key=lambda s: s["img"].height, reverse=True)

    remaining = loaded_items
    page_index = 0
    
    while remaining:
        # Determine how many sprites fit on this current page
        placements, total_h = pack_shelves(remaining, args.max_size, args.padding)
        
        # If total height exceeds max_size, reduce the item count until it fits
        if total_h > args.max_size:
            while total_h > args.max_size and len(placements) > 1:
                remaining_count = len(placements) - 1
                placements, total_h = pack_shelves(remaining[:remaining_count], args.max_size, args.padding)
        
        current_page_items = remaining[:len(placements)]
        remaining = remaining[len(placements):]
        
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

        animations = {}
        if args.group_by_folder:
            for fname in frame_dict.keys():
                prefix = "".join(re.split(r'(\d+)', fname)[0])
                animations.setdefault(prefix, []).append(fname)

        suffix = f"-{page_index}" if page_index > 0 or len(remaining) > 0 else ""
        out_name = (args.output or folder.name) + suffix
        json_path = out_name + ".json"
        img_ext = ".webp" if args.webp else ".png"
        img_path = out_name + img_ext
        
        if args.webp:
            atlas_img.save(img_path, "WEBP", quality=args.quality)
        else:
            atlas_img.save(img_path, "PNG")

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
        
        print(f"Created {img_path} and {json_path} ({len(placements)} sprites)")
        page_index += 1

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PixiJS Multi-Packer & Squoosher")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Sprites Command Setup
    f_parser = subparsers.add_parser("sprites", help="Pack folder into JSON atlas")
    f_parser.add_argument("folder", help="Folder containing sprites")
    f_parser.add_argument("--padding", type=int, default=2, help="Pixels between sprites")
    f_parser.add_argument("--max-size", type=int, default=2048, help="Max texture dimension")
    f_parser.add_argument("--trim", action="store_true", help="Remove transparent borders")
    f_parser.add_argument("--webp", action="store_true", help="Export as WebP")
    f_parser.add_argument("--quality", type=int, default=80, help="WebP quality 1-100")
    f_parser.add_argument("--power-of-two", action="store_true", help="Force POT dimensions")
    f_parser.add_argument("--group-by-folder", action="store_true", help="Auto-create animation tags")
    f_parser.add_argument("--output", "-o", help="Root name for output files")
    f_parser.add_argument("--pretty", action="store_true", help="Format JSON with indents")
    
    f_parser.set_defaults(func=run_sprites)

    # Keep compatibility for 'sheet' command if needed
    s_parser = subparsers.add_parser("sheet", help="Extract from existing sheet")
    # (Sheet implementation omitted for brevity, but you can keep your old one here)

    args = parser.parse_args()
    args.func(args)