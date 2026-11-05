import time
import numpy as np
import rasterio
import onnxruntime as ort
from rasterio.windows import Window

image_path = "dataset/raw_images/residential_blocks.tif"
model_path = "ai_model/model_weights/model.onnx"
mean = np.array([0.485, 0.456, 0.406], dtype=np.float32).reshape(3, 1, 1)
std = np.array([0.229, 0.224, 0.225], dtype=np.float32).reshape(3, 1, 1)

t0 = time.perf_counter()
session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
print("load_s", round(time.perf_counter() - t0, 2))
print("input", session.get_inputs()[0].name, session.get_inputs()[0].shape)
print("output", session.get_outputs()[0].name, session.get_outputs()[0].shape)

with rasterio.open(image_path) as src:
    tile = src.read([1, 2, 3], window=Window(2000, 4000, 256, 256)).astype(np.float32) / 255.0

tile = (tile - mean) / std
tensor = np.expand_dims(tile, axis=0).astype(np.float32)
t1 = time.perf_counter()
output = session.run(None, {session.get_inputs()[0].name: tensor})[0]
print("infer_s", round(time.perf_counter() - t1, 2), "shape", output.shape)
