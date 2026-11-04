import numpy as np
import rasterio
import onnxruntime as ort

from pathlib import Path


# Project paths
IMAGE_PATH = "dataset/raw_images/residential_blocks.tif"
MODEL_PATH = "ai_model/model_weights/model.onnx"

OUTPUT_DIR = Path("outputs/masks")

TILE_SIZE = 256
BUILDING_CLASS = 1


def preprocess(tile):

    tile = tile.astype(np.float32) / 255.0

    mean = np.array(
        [0.4297, 0.4002, 0.3433],
        dtype=np.float32
    )

    std = np.array(
        [0.2056, 0.1674, 0.1599],
        dtype=np.float32
    )

    tile = (tile - mean) / std

    tile = np.transpose(tile, (2, 0, 1))

    return np.expand_dims(tile, axis=0)


def save_geotiff(output_path, data, source_profile):

    profile = source_profile.copy()

    profile.pop("photometric", None)
    profile.pop("interleave", None)
    profile.pop("nbits", None)

    profile.update({
        "driver": "GTiff",
        "count": 1,
        "dtype": "uint8",
        "compress": "lzw",
        "photometric": "MINISBLACK"
    })

    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(data, 1)


def main():

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading ONNX model...")

    session = ort.InferenceSession(
        MODEL_PATH,
        providers=["CPUExecutionProvider"]
    )

    input_name = session.get_inputs()[0].name

    with rasterio.open(IMAGE_PATH) as src:

        width = src.width
        height = src.height

        print(f"Image dimensions: {width} x {height}")

        class_map = np.zeros(
            (height, width),
            dtype=np.uint8
        )

        total_tiles = (
            ((height + TILE_SIZE - 1) // TILE_SIZE)
            *
            ((width + TILE_SIZE - 1) // TILE_SIZE)
        )

        tile_number = 0

        print("Total tiles:", total_tiles)
        print("\nStarting building detection...\n")

        for y in range(0, height, TILE_SIZE):

            for x in range(0, width, TILE_SIZE):

                h = min(TILE_SIZE, height - y)
                w = min(TILE_SIZE, width - x)

                tile = src.read(
                    window=((y, y + h), (x, x + w))
                )

                tile = np.transpose(tile, (1, 2, 0))

                padded = np.zeros(
                    (TILE_SIZE, TILE_SIZE, 3),
                    dtype=np.uint8
                )

                padded[:h, :w] = tile

                input_tensor = preprocess(padded)

                logits = session.run(
                    None,
                    {input_name: input_tensor}
                )[0][0]

                predictions = np.argmax(
                    logits,
                    axis=0
                )

                class_map[y:y+h, x:x+w] = predictions[:h, :w]

                tile_number += 1

                if tile_number % 20 == 0:
                    print(
                        f"Processed {tile_number}/{total_tiles} tiles"
                    )

        # Create building mask
        building_mask = (
            class_map == BUILDING_CLASS
        ).astype(np.uint8) * 255

        # Output paths
        class_path = OUTPUT_DIR / "class_map.tif"
        mask_path = OUTPUT_DIR / "building_mask.tif"

        # Save georeferenced outputs
        save_geotiff(
            class_path,
            class_map,
            src.profile
        )

        save_geotiff(
            mask_path,
            building_mask,
            src.profile
        )

        # Class statistics
        classes, counts = np.unique(
            class_map,
            return_counts=True
        )

        print("\nCLASS DISTRIBUTION")

        for cls, count in zip(classes, counts):

            percentage = (count / class_map.size) * 100

            print(
                f"Class {cls}: {count} pixels "
                f"({percentage:.2f}%)"
            )

        print("\nBUILDING DETECTION COMPLETED!")

        print(
            "Building pixels:",
            np.count_nonzero(building_mask)
        )

        print("Class map:", class_path)
        print("Building mask:", mask_path)


if __name__ == "__main__":
    main()