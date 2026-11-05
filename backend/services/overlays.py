from pathlib import Path

import cv2
import numpy as np


def write_rgba_overlay(mask_path, output_path, color_rgb, max_size=1600, alpha=170):
    mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        raise FileNotFoundError(f"Mask not found: {mask_path}")

    height, width = mask.shape
    scale = min(1.0, max_size / max(height, width))
    if scale < 1.0:
        resized = (
            max(1, int(round(width * scale))),
            max(1, int(round(height * scale))),
        )
        mask = cv2.resize(mask, resized, interpolation=cv2.INTER_NEAREST)

    overlay = np.zeros((mask.shape[0], mask.shape[1], 4), dtype=np.uint8)
    selected = mask > 0
    overlay[selected, 0] = color_rgb[2]
    overlay[selected, 1] = color_rgb[1]
    overlay[selected, 2] = color_rgb[0]
    overlay[selected, 3] = alpha

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output_path), overlay):
        raise RuntimeError(f"Could not write overlay: {output_path}")
    return str(output_path)
