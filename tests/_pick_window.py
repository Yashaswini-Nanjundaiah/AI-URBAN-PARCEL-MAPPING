import cv2
import numpy as np

mask = cv2.imread("outputs/run_1/detection/building_mask.png", cv2.IMREAD_GRAYSCALE)
print("mask", None if mask is None else mask.shape)
if mask is None:
    raise SystemExit(1)

size = 768
best = None
for row in range(0, mask.shape[0] - size, 384):
    for col in range(0, mask.shape[1] - size, 384):
        window = mask[row:row + size, col:col + size]
        building = int(np.count_nonzero(window))
        open_pixels = int(window.size - building)
        score = min(building, open_pixels)
        if best is None or score > best[0]:
            best = (score, building, open_pixels, col, row)

print("best", best)
