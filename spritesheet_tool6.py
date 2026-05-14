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
    """Sorts strings with numbers naturally: frame1, frame2, frame10."""
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r"(\d+)", str(s))]

def trim_alpha(img):
    """Crops transparent borders to save space."""
    bbox = img.getbbox()
    return (img.crop(bbox), (bbox[0], bbox[1])) if bbox else (img, (0, 0))

def pack_tight(items, padding):
    """Packs all sprites into a single tight, square-ish rectangle."""
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

def run_sprites(args):
    folder = Path(args.folder)
    files = [p for p in folder.glob("**/*") if p.suffix.lower() in SUPPORTED_EXTS]
    files.sort(key=lambda p: natural_sort_key(p.name))
    
    if not files:
        print("Error: No images found! Use '.' if you are in the folder."); return

    loaded_items = []
    for p in files:
        img = Image.open(p).convert("RGBA")
        # Record source data for Pixi
        if args.trim:
            trimmed_img, (ox, oy) = trim_alpha(img)
            loaded_items.append({
                "p": p, "img": trimmed_img, 
                "ow": img.width, "oh": img.height, 
                "ox": ox, "oy": oy
            })
        else:
            loaded_items.append({
                "p": p, "img": img, 
                "ow": img.width, "oh": img.height, 
                "ox": 0, "oy": 0
            })

    placements, cw, ch = pack_tight(loaded_items, args.padding)
    
    atlas_img = Image.new("RGBA", (cw, ch), (0,0,0,0))
    frame_dict = {}
    
    for item, x, y in placements:
        atlas_img.paste(item['img'], (x, y))
        # PixiJS Hash Format
        frame_dict[item['p'].name] = {
            "frame": {"x": x, "y": y, "w": item['img'].width, "h": item['img'].height},
            "rotated": False,
            "trimmed": item['ox'] > 0 or item['oy'] > 0,
            "spriteSourceSize": {"x": item['ox'], "y": item['oy'], "w": item['img'].width, "h": item['img'].height},
            "sourceSize": {"w": item['ow'], "h": item['oh']}
        }

    out_name = (args.output or "atlas").replace(".json", "")
    img_path = out_name + ".webp"
    
    # METHOD 6 is the highest compression effort for WebP
    print(f"Squooshing image to {img_path} (Quality: {args.quality})...")
    atlas_img.save(img_path, "WEBP", quality=args.quality, method=6)
    
    # Pretty-print the JSON with 4-space indentation
    with open(out_name + ".json", "w") as f:
        json_dump_data = {
            "frames": frame_dict,
            "meta": {
                "app": "Gemini-Pixi-Packer-Small",
                "image": img_path,
                "format": "RGBA8888",
                "size": {"w": cw, "h": ch},
                "scale": "1"
            }
        }
        json.dump(json_dump_data, f, indent=4)
    
    print(f"WakeUP! Final Atlas Size: {cw}x{ch}. JSON is at your disposal.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", help="Path to images (use '.' for current folder)")
    parser.add_argument("--padding", type=int, default=1, help="Pixels between sprites")
    parser.add_argument("--quality", type=int, default=60, help="WebP quality (1-100)")
    parser.add_argument("--trim", action="store_true", default=True, help="Remove empty space")
    parser.add_argument("--output", "-o", help="Name of output files")
    args = parser.parse_args()
    run_sprites(args)