#!/usr/bin/env python3
"""Cut achievement pin PNG out of background → transparent 512×512.

Usage: cut_achievement.py SRC.png DST.png
- If SRC already has real transparency → just contain-fit to 512, keep alpha.
- Else BFS flood-fill from border over a bright/low-saturation bg mask.
"""
import sys
import numpy as np
from PIL import Image
from collections import deque

SRC, DST = sys.argv[1], sys.argv[2]
img = Image.open(SRC).convert("RGBA")
arr = np.array(img)
h, w = arr.shape[:2]
alpha = arr[..., 3]

def fit512(im):
    im = im.copy()
    im.thumbnail((512, 512), Image.LANCZOS)
    canvas = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    canvas.paste(im, ((512 - im.width) // 2, (512 - im.height) // 2), im)
    return canvas

# already transparent? (>2% fully-transparent pixels)
if (alpha < 16).mean() > 0.02:
    # trim transparent border then fit
    ys, xs = np.where(alpha > 16)
    if len(xs):
        arr = arr[ys.min():ys.max()+1, xs.min():xs.max()+1]
    fit512(Image.fromarray(arr, "RGBA")).save(DST)
    print(f"{DST}: already-alpha, trimmed+resized")
    sys.exit(0)

# BFS cutout
rgb = arr[..., :3].astype(np.int16)
mx = rgb.max(axis=2); mn = rgb.min(axis=2)
sat = mx - mn
bg = (sat < 30) & (mn > 165)            # neutral & bright
visited = np.zeros((h, w), bool)
q = deque()
for x in range(w):
    for y in (0, h-1):
        if bg[y, x]: q.append((y, x)); visited[y, x] = True
for y in range(h):
    for x in (0, w-1):
        if bg[y, x] and not visited[y, x]: q.append((y, x)); visited[y, x] = True
while q:
    y, x = q.popleft()
    for dy, dx in ((1,0),(-1,0),(0,1),(0,-1)):
        ny, nx = y+dy, x+dx
        if 0 <= ny < h and 0 <= nx < w and not visited[ny, nx] and bg[ny, nx]:
            visited[ny, nx] = True; q.append((ny, nx))
# halo grow 2px so anti-aliased fringe goes too
out = visited.copy()
for _ in range(2):
    g = out.copy()
    g[1:,:] |= out[:-1,:]; g[:-1,:] |= out[1:,:]
    g[:,1:] |= out[:,:-1]; g[:,:-1] |= out[:,1:]
    out = g & bg | visited
arr[..., 3] = np.where(out, 0, 255).astype(np.uint8)
cut_pct = 100 * out.mean()
ys, xs = np.where(arr[..., 3] > 16)
if len(xs):
    arr = arr[ys.min():ys.max()+1, xs.min():xs.max()+1]
fit512(Image.fromarray(arr, "RGBA")).save(DST)
print(f"{DST}: BFS cut {cut_pct:.1f}%")
