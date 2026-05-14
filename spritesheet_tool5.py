#!/usr/bin/env python3
import argparse
import json
import math
import sys
import re
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("Error: Pillow is required. Install it with:  pip install Pillow")
    sys.exit(1)

SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tga"}

def natural_sort_key(s):
    """Sorts strings with numbers naturally (e.g., fly1, fly2, fly10)."""
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r"(\d+)", str(s))]

def trim_alpha(img):
    """Crops transparent borders and returns the offset for Pixi's spriteSourceSize."""
    bbox = img.getbbox()
    return (img.crop(bbox), (bbox[0], bbox[1])) if bbox else (img, (0, 0))

def pack_all_sprites(items, padding, pot=False):
    """Shelf packing algorithm that expands to fit everything in one sheet."""
    # Sort by height descending for tighter shelf packing
    items.sort(key=lambda s: s["img"].height, reverse=True)
    
    # Calculate an ideal width based on total area to keep the sheet somewhat square
    total_area = sum((s["img"].width + padding) * (s["img"].height + padding) for s in items)
    ideal_width = max(max(s["img"].width for s in items), int(math.sqrt(total_area)))
    
    shelves = [] # [x_ptr, y_ptr, shelf_h]
    placements = []
    
    for item in items:
        sw, sh = item['img'].width + padding, item['img'].height + padding
        placed = False
        for shelf in shelves:
            if shelf[0] + sw <= ideal_width:
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
    
    if pot:
        canvas_h = 2**math.ceil(math.log2(canvas_h))
        canvas_w = 2**math.ceil(math.log2(canvas_w))

    return placements, canvas_w, canvas_h

def run_sprites(args):
    folder = Path(args.folder)
    files = [p for p in folder.glob("**/*") if p.suffix.lower() in SUPPORTED_EXTS]
    files.sort(key=lambda p: natural_sort_key(p.name))
    
    if not files:
        print(f"Error: No images found in '{folder.absolute()}'. Use '.' for current folder."); return

    loaded_items = []
    for p in files:
        img = Image.open(p).convert("RGBA")
        ow, oh = img.size
        ox, oy = (0, 0)
        if args.trim:
            img, (ox, oy) = trim_alpha(img)
        loaded_items.append({"p": p, "img": img, "ow": ow, "oh": oh, "ox": ox, "oy": oy})

    print(f"Packing {len(loaded_items)} sprites into a single sheet...")
    placements, canvas_w, canvas_h = pack_all_sprites(loaded_items, args.padding, args.power_of_two)

    atlas_img = Image.new("RGBA", (canvas_w, canvas_h), (0,0,0,0))
    frame_dict = {}
    
    for item, x, y in placements:
        atlas_img.paste(item['img'], (x, y))
        # PixiJS TexturePacker Hash Format
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
            # Automatically group by name prefix (e.g. fly001 -> fly)
            prefix = "".join(re.split(r'(\d+)', fname)[0])
            animations.setdefault(prefix, []).append(fname)

    out_base = (args.output or folder.name).replace(".json", "")
    json_path = out_base + ".json"
    img_ext = ".webp" if args.webp else ".png"
    img_path = out_base + img_ext
    
    if args.webp:
        atlas_img.save(img_path, "WEBP", quality=args.quality)
    else:
        atlas_img.save(img_path, "PNG")

    data = {
        "frames": frame_dict,
        "animations": animations,
        "meta": {
            "app": "Gemini-Pixi-Packer-Unlimited",
            "image": Path(img_path).name,
            "format": "RGBA8888",
            "size": {"w": canvas_w, "h": canvas_h},
            "scale": "1"
        }
    }

    with open(json_path, "w") as f:
        json.dump(data, f, indent=4 if args.pretty else None)
    
    print(f"Success! Created {img_path} and {json_path} ({canvas_w}x{canvas_h})")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PixiJS Single-Sheet Packer")
    subparsers = parser.add_subparsers(dest="command", required=True)

    f_parser = subparsers.add_parser("sprites")
    f_parser.add_argument("folder")
    f_parser.add_argument("--padding", type=int, default=2)
    f_parser.add_argument("--trim", action="store_true", help="Remove transparency")
    f_parser.add_argument("--webp", action="store_true", help="Export as WebP")
    f_parser.add_argument("--quality", type=int, default=80)
    f_parser.add_argument("--power-of-two", action="store_true")
    f_parser.add_argument("--group-by-folder", action="store_true")
    f_parser.add_argument("--output", "-o")
    f_parser.add_argument("--pretty", action="store_true")
    f_parser.set_defaults(func=run_sprites)

    args = parser.parse_args()
    args.func(args)