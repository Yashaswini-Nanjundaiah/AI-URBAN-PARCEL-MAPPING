import numpy as np
import rasterio
from PIL import Image
from pathlib import Path

IMAGE_PATH = "dataset/raw_images/residential_blocks.tif"
CLASS_MAP_PATH = "outputs/masks/class_map.tif"
OUTPUT_DIR = Path("outputs/masks")


def main():

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with rasterio.open(IMAGE_PATH) as src:
        image = src.read([1, 2, 3])
        image = np.transpose(image, (1, 2, 0))

    with rasterio.open(CLASS_MAP_PATH) as src:
        class_map = src.read(1)

    # Create class visualization
    class_visual = np.zeros(
        (*class_map.shape, 3),
        dtype=np.uint8
    )

    class_visual[class_map == 0] = [0, 0, 255]
    class_visual[class_map == 1] = [255, 0, 0]
    class_visual[class_map == 2] = [0, 255, 0]

    # Highlight predicted buildings in red
    overlay = image.copy()

    building_pixels = class_map == 1

    overlay[building_pixels] = (
        0.5 * overlay[building_pixels]
        + 0.5 * np.array([255, 0, 0])
    ).astype(np.uint8)

    # Resize previews for easy viewing
    def save_preview(array, filename):
        img = Image.fromarray(array)
        img.thumbnail((1600, 1600))
        img.save(OUTPUT_DIR / filename)

    save_preview(
        class_visual,
        "class_map_preview.png"
    )

    save_preview(
        overlay,
        "building_overlay_preview.png"
    )

    print("Visual previews generated!")
    print("outputs/masks/class_map_preview.png")
    print("outputs/masks/building_overlay_preview.png")


if __name__ == "__main__":
    main()