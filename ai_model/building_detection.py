import os
import cv2
import numpy as np
import rasterio
import onnxruntime as ort

from rasterio.windows import Window


MODEL_SIZE = 256

# DINOv3 HOT model normalization
MEAN = np.array(
    [0.485, 0.456, 0.406],
    dtype=np.float32
)

STD = np.array(
    [0.229, 0.224, 0.225],
    dtype=np.float32
)


def detect_buildings(image_path, output_dir, model_path):

    os.makedirs(output_dir, exist_ok=True)

    if not os.path.exists(model_path):
        raise FileNotFoundError(
            f"ONNX model not found: {model_path}"
        )

    session = ort.InferenceSession(
        model_path,
        providers=["CPUExecutionProvider"]
    )

    input_name = session.get_inputs()[0].name

    with rasterio.open(image_path) as src:

        width = src.width
        height = src.height

        if src.count < 3:
            raise ValueError(
                "Building detection requires RGB imagery."
            )

        building_mask = np.zeros(
            (height, width),
            dtype=np.uint8
        )

        for row in range(0, height, MODEL_SIZE):

            for col in range(0, width, MODEL_SIZE):

                tile_width = min(
                    MODEL_SIZE,
                    width - col
                )

                tile_height = min(
                    MODEL_SIZE,
                    height - row
                )

                window = Window(
                    col,
                    row,
                    tile_width,
                    tile_height
                )

                tile = src.read(
                    [1, 2, 3],
                    window=window,
                    out_shape=(
                        3,
                        MODEL_SIZE,
                        MODEL_SIZE
                    )
                )

                tile = tile.astype(np.float32)

                # Convert to RGB range [0, 1]
                tile /= 255.0

                mean = MEAN.reshape(3, 1, 1)
                std = STD.reshape(3, 1, 1)

                tile = (tile - mean) / std

                tensor = np.expand_dims(
                    tile,
                    axis=0
                ).astype(np.float32)

                output = session.run(
                    None,
                    {input_name: tensor}
                )[0]

                logits = np.asarray(output)

                if logits.ndim != 4:
                    raise ValueError(
                        f"Unexpected model output shape: {logits.shape}"
                    )

                # Model documentation specifies mask logits
                # in output channel zero.
                mask_logits = logits[0, 0]

                probabilities = 1.0 / (
                    1.0 + np.exp(-mask_logits)
                )

                tile_mask = (
                    probabilities >= 0.4371
                ).astype(np.uint8) * 255

                tile_mask = cv2.resize(
                    tile_mask,
                    (tile_width, tile_height),
                    interpolation=cv2.INTER_NEAREST
                )

                building_mask[
                    row:row + tile_height,
                    col:col + tile_width
                ] = tile_mask

    mask_path = os.path.join(
        output_dir,
        "building_mask.png"
    )

    cv2.imwrite(
        mask_path,
        building_mask
    )

    print("Building detection completed.")

    return mask_path