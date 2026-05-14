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

def pack_serial(items, padding):
    """Packs sprites in the order they were provided (Natural Order)."""
    # We DO NOT sort by height here to keep the sequence serial
    total_area = sum((s["img"].width + padding) * (s["img"].height + padding) for s in items)
    # Estimate a square-ish width, but ensure it fits the widest sprite
    target_width = max(max(s["img"].width for s in items), int(math.sqrt(total_area)))
    
    placements = []
    curr_x, curr_y = 0, 0
    row_h = 0
    max_canvas_w = 0
    
    for item in items:
        w, h = item['img'].width + padding, item['img'].height + padding
        
        # If adding this sprite exceeds the width, start a new row
        if curr_x + w > target_width and curr_x > 0:
            curr_y += row_h
            curr_x = 0
            row_h = 0
            
        placements.append((item, curr_x, curr_y))
        curr_x += w
        row_h = max(row_h, h)
        max_canvas_w = max(max_canvas_w, curr_x)
        
    return placements, max_canvas_w, (curr_y + row_h)

def run_sprites(args):
    folder = Path(args.folder)
    files = [p for p in folder.glob("**/*") if p.suffix.lower() in SUPPORTED_EXTS]
    # 1. Establish the serial order (frame1, frame2...)
    files.sort(key=lambda p: natural_sort_key(p.name))
    
    if not files:
        print("Error: No images found!"); return

    loaded_items = []
    for p in files:
        img = Image.open(p).convert("RGBA")
        if args.trim:
            trimmed_img, (ox, oy) = trim_alpha(img)
            loaded_items.append({"p": p, "img": trimmed_img, "ow": img.width, "oh": img.height, "ox": ox, "oy": oy})
        else:
            loaded_items.append({"p": p, "img": img, "ow": img.width, "oh": img.height, "ox": 0, "oy": 0})

    # 2. Use the serial packer instead of tight packing
    placements, cw, ch = pack_serial(loaded_items, args.padding)
    
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

    out_name = (args.output or "atlas").replace(".json", "")
    img_path = out_name + ".webp"
    
    print(f"Saving Serial Atlas: {img_path}...")
    atlas_img.save(img_path, "WEBP", quality=args.quality, method=6)
    
    # Save JSON with frames in the EXACT input order
    with open(out_name + ".json", "w") as f:
        json_dump_data = {
            "frames": frame_dict, 
            "meta": {"app": "Raven-Serial-Packer", "image": img_path, "size": {"w": cw, "h": ch}}
        }
        json.dump(json_dump_data, f, indent=4)
    
    print(f"Done! Layout is now serial (row-by-row in filename order).")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", help="Path to images")
    parser.add_argument("--padding", type=int, default=2)
    parser.add_argument("--quality", type=int, default=80)
    parser.add_argument("--trim", action="store_true", default=True)
    parser.add_argument("--output", "-o", help="Output name")
    args = parser.parse_args()
    run_sprites(args)