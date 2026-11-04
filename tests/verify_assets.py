from pathlib import Path
import rasterio
import onnxruntime as ort

image_path = Path("dataset/raw_images/residential_blocks.tif")
model_path = Path("ai_model/model_weights/model.onnx")

# Check files
assert image_path.exists(), f"Image missing: {image_path}"
assert model_path.exists(), f"Model missing: {model_path}"

print("Both files found!")

# Inspect drone image
with rasterio.open(image_path) as src:
    print("\nIMAGE DETAILS")
    print("Dimensions:", src.width, "x", src.height)
    print("Bands:", src.count)
    print("CRS:", src.crs)
    print("Bounds:", src.bounds)

# Inspect ONNX model
session = ort.InferenceSession(
    str(model_path),
    providers=["CPUExecutionProvider"]
)

print("\nMODEL DETAILS")
print("Inputs:")
for item in session.get_inputs():
    print(item.name, item.shape, item.type)

print("Outputs:")
for item in session.get_outputs():
    print(item.name, item.shape, item.type)

print("\nASSET VERIFICATION PASSED!")