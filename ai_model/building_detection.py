import os

import cv2
import numpy as np
import onnxruntime as ort
import rasterio
from rasterio.windows import Window


MODEL_SIZE = 256

# ImageNet normalization used by the existing ONNX building model.
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
BUILDING_THRESHOLD = 0.4371


def _origins(length, tile=MODEL_SIZE):
    """Tile starts that cover the axis without stretching a partial edge tile."""
    if length <= tile:
        return [0]
    values = list(range(0, length, tile))
    if values[-1] + tile > length:
        values[-1] = length - tile
    origins = []
    for value in values:
        if not origins or origins[-1] != value:
            origins.append(value)
    return origins


def _scale_to_unit(tile):
    values = tile.astype(np.float32)
    if np.issubdtype(tile.dtype, np.floating):
        peak = float(np.nanmax(values)) if values.size else 0.0
        if peak > 1.5:
            values = values / 255.0
        return values
    maximum = float(np.iinfo(tile.dtype).max)
    return values / maximum


def _prepare_tensor(tile):
    """Pad a tile that is smaller than the model input. Never stretch it."""
    unit = _scale_to_unit(tile)
    channels, height, width = unit.shape
    if channels < 3:
        raise ValueError("Building detection requires RGB imagery.")
    canvas = np.zeros((3, MODEL_SIZE, MODEL_SIZE), dtype=np.float32)
    canvas[:, :height, :width] = unit[:3]
    if height < MODEL_SIZE or width < MODEL_SIZE:
        # Reflect real pixels into the padding so the edge is not presented as black.
        padded = np.pad(
            unit[:3],
            ((0, 0), (0, MODEL_SIZE - height), (0, MODEL_SIZE - width)),
            mode="reflect" if height > 1 and width > 1 else "edge",
        )
        canvas = padded[:, :MODEL_SIZE, :MODEL_SIZE]
    mean = MEAN.reshape(3, 1, 1)
    std = STD.reshape(3, 1, 1)
    normalized = (canvas - mean) / std
    return np.expand_dims(normalized, axis=0).astype(np.float32)


def detect_buildings(image_path, output_dir, model_path, progress_callback=None):
    os.makedirs(output_dir, exist_ok=True)

    if not os.path.exists(model_path):
        raise FileNotFoundError(f"ONNX model not found: {model_path}")

    options = ort.SessionOptions()
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    session = ort.InferenceSession(
        model_path,
        sess_options=options,
        providers=["CPUExecutionProvider"],
    )
    input_name = session.get_inputs()[0].name
    output_name = session.get_outputs()[0].name

    with rasterio.open(image_path) as src:
        width = src.width
        height = src.height

        if src.count < 3:
            raise ValueError("Building detection requires RGB imagery.")

        row_origins = _origins(height)
        col_origins = _origins(width)
        total = len(row_origins) * len(col_origins)
        completed = 0

        building_mask = np.zeros((height, width), dtype=np.uint8)
        covered = np.zeros((height, width), dtype=bool)

        for row in row_origins:
            for col in col_origins:
                tile_width = min(MODEL_SIZE, width - col)
                tile_height = min(MODEL_SIZE, height - row)
                window = Window(col, row, tile_width, tile_height)
                tile = src.read([1, 2, 3], window=window)
                tensor = _prepare_tensor(tile)
                logits = np.asarray(session.run([output_name], {input_name: tensor})[0])

                if logits.ndim != 4 or logits.shape[1] < 1:
                    raise ValueError(f"Unexpected model output shape: {logits.shape}")

                # Channel 0 holds the building-mask logits used by this model.
                probabilities = 1.0 / (1.0 + np.exp(-logits[0, 0]))
                prediction = (probabilities >= BUILDING_THRESHOLD).astype(np.uint8) * 255
                prediction = prediction[:tile_height, :tile_width]

                view = covered[row:row + tile_height, col:col + tile_width]
                destination = building_mask[row:row + tile_height, col:col + tile_width]
                destination[~view] = prediction[~view]
                view[:] = True

                completed += 1
                if progress_callback and (
                    completed == total or completed % 10 == 0
                ):
                    progress_callback(completed, total)

    uncovered = int(np.count_nonzero(~covered))
    if uncovered:
        raise RuntimeError(f"Building detection left {uncovered} pixels without a result.")

    mask_path = os.path.join(output_dir, "building_mask.png")
    encoded = cv2.imencode(".png", building_mask)[1]
    encoded.tofile(mask_path)
    return mask_path
