import sqlite3
import rasterio

src = rasterio.open("dataset/raw_images/residential_blocks.tif")
print("IMAGE", src.width, src.height, src.count, src.crs, list(src.dtypes))
print("BOUNDS", src.bounds)
print("RES", src.res)

conn = sqlite3.connect("database/urban_mapping.db")
print("SCHEMA")
for row in conn.execute("SELECT sql FROM sqlite_master WHERE type='table'"):
    print(row[0])
print("projects", conn.execute("select count(*) from projects").fetchone()[0])
print("runs")
for row in conn.execute(
    "select id, project_id, status, building_pixels, candidate_count from processing_runs"
):
    print(row)
print("regions", conn.execute("select count(*) from candidate_regions").fetchone()[0])
