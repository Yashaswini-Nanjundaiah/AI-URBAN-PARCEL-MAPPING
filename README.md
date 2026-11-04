# AI-Based Automated Urban Parcel Mapping

AI-based building detection and candidate open-region extraction from georeferenced aerial imagery.

## Technology Stack
- Python
- ONNX Runtime
- OpenCV
- Rasterio
- FastAPI
- Streamlit
- SQLite
- GeoJSON

## Features
- GeoTIFF image input
- Building detection using ONNX segmentation
- Candidate region extraction
- Geospatial processing
- Processing history
- GeoJSON export
- Results visualisation

## Setup

1. Clone the repository.
2. Create a virtual environment:
   `python -m venv .venv`
3. Activate it:
   `.venv\Scripts\activate`
4. Install dependencies:
   `pip install -r requirements.txt`
5. Place the required ONNX model in:
   `ai_model/model_weights/model.onnx`
6. Add a suitable GeoTIFF image to the dataset.
7. Start the backend:
   `uvicorn backend.main:app --reload`
8. Start the dashboard:
   `streamlit run frontend/app.py`

## Note
Model weights and large input datasets are not included in this repository.
Candidate regions are algorithmically extracted regions, not verified cadastral parcels.