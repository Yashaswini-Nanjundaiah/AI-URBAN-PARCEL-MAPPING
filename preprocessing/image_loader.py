import rasterio
from pathlib import Path


def load_image(image_path):
    image_path = Path(image_path)

    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    with rasterio.open(image_path) as src:
        image = src.read()

        metadata = {
            "width": src.width,
            "height": src.height,
            "bands": src.count,
            "crs": str(src.crs),
            "transform": src.transform,
            "bounds": src.bounds,
            "dtype": str(src.dtypes[0])
        }

    print("Image loaded successfully!")
    print(f"Dimensions: {metadata['width']} x {metadata['height']}")
    print(f"Bands: {metadata['bands']}")
    print(f"CRS: {metadata['crs']}")

    return image, metadata