import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import rasterio
import numpy as np

from ai_model.building_detection import BuildingDetector

image_path = "dataset/raw_images/residential_blocks.tif"
model_path = "ai_model/model_weights/model.onnx"

# Read an actual image tile
with rasterio.open(image_path) as src:
    tile = src.read(
        window=((0, 256), (0, 256))
    )
    tile = np.transpose(tile, (1, 2, 0))

print("Real tile shape:", tile.shape)

# Run inference
detector = BuildingDetector(model_path)
logits = detector.predict_tile(tile)

print("\nCHANNEL STATISTICS")

for i in range(logits.shape[0]):
    channel = logits[i]

    print(f"\nChannel {i}")
    print("Min:", channel.min())
    print("Max:", channel.max())
    print("Mean:", channel.mean())

# Determine winning class per pixel
predictions = np.argmax(logits, axis=0)

print("\nPREDICTED CLASS DISTRIBUTION")

classes, counts = np.unique(
    predictions,
    return_counts=True
)

for cls, count in zip(classes, counts):
    print(f"Class {cls}: {count} pixels ({count / predictions.size * 100:.2f}%)")