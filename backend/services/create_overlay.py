from pathlib import Path

import numpy as np
import rasterio
import cv2
from PIL import Image


BASE_DIR = Path(__file__).resolve().parents[2]

IMAGE_PATH = BASE_DIR / "dataset/raw_images/residential_blocks.tif"

BUILDING_MASK = (
    BASE_DIR / "outputs/run_1/detection/building_mask.png"
)

CANDIDATE_MASK = (
    BASE_DIR / "outputs/run_1/parcels/candidate_regions_mask.png"
)

OUTPUT_PATH = (
    BASE_DIR / "outputs/run_1/combined_overlay.png"
)


def create_overlay():

    # Read original image
    with rasterio.open(IMAGE_PATH) as src:
        image = src.read([1, 2, 3])
        image = np.transpose(image, (1, 2, 0))

    # Convert image to displayable RGB
    image = image.astype(np.float32)

    for channel in range(3):
        band = image[:, :, channel]
        low, high = np.percentile(band, [2, 98])

        if high > low:
            image[:, :, channel] = (
                (band - low) / (high - low) * 255
            )

    image = np.clip(image, 0, 255).astype(np.uint8)

    # Read masks
    building = cv2.imread(
        str(BUILDING_MASK),
        cv2.IMREAD_GRAYSCALE
    )

    candidate = cv2.imread(
        str(CANDIDATE_MASK),
        cv2.IMREAD_GRAYSCALE
    )

    if building is None or candidate is None:
        raise FileNotFoundError("One or both masks are missing.")

    if building.shape != image.shape[:2]:
        raise ValueError("Building mask dimensions mismatch.")

    if candidate.shape != image.shape[:2]:
        raise ValueError("Candidate mask dimensions mismatch.")

    # Create overlay
    overlay = image.copy()

    building_pixels = building > 0
    candidate_pixels = candidate > 0

    # Buildings = Red
    overlay[building_pixels] = (
        0.45 * image[building_pixels]
        + 0.55 * np.array([255, 0, 0])
    )

    # Candidate open regions = Green
    overlay[candidate_pixels] = (
        0.45 * image[candidate_pixels]
        + 0.55 * np.array([0, 255, 0])
    )

    overlay = np.clip(overlay, 0, 255).astype(np.uint8)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    Image.fromarray(overlay).save(OUTPUT_PATH)

    print("Overlay generated successfully!")
    print("Output:", OUTPUT_PATH)


if __name__ == "__main__":
    create_overlay()
    