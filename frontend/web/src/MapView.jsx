import { useEffect } from "react";
import {
  GeoJSON,
  ImageOverlay,
  MapContainer,
  TileLayer,
  useMap,
} from "react-leaflet";

function FitBounds({ bounds }) {
  const map = useMap();

  useEffect(() => {
    if (!bounds) {
      return;
    }
    map.fitBounds(bounds, { padding: [24, 24], maxZoom: 19 });
  }, [map, bounds]);

  return null;
}

function onEachRegion(feature, layer) {
  const properties = feature.properties || {};
  const area = Number(properties.area_sqm || 0).toLocaleString(undefined, {
    maximumFractionDigits: 1,
  });
  layer.bindPopup(
    `<strong>Region ${properties.region_number ?? ""}</strong><br/>${area} m²`
  );
}

export default function MapView({
  bounds,
  previewUrl,
  buildingUrl,
  candidateUrl,
  geojson,
  layers,
}) {
  const center = bounds
    ? [
        (bounds[0][0] + bounds[1][0]) / 2,
        (bounds[0][1] + bounds[1][1]) / 2,
      ]
    : [5.085, -76.652];

  return (
    <MapContainer
      center={center}
      zoom={16}
      minZoom={2}
      maxZoom={22}
      className="map-canvas"
      scrollWheelZoom
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <FitBounds bounds={bounds} />
      {layers.image && previewUrl && bounds ? (
        <ImageOverlay url={previewUrl} bounds={bounds} opacity={0.92} zIndex={200} />
      ) : null}
      {layers.buildings && buildingUrl && bounds ? (
        <ImageOverlay url={buildingUrl} bounds={bounds} opacity={0.85} zIndex={300} />
      ) : null}
      {layers.candidates && candidateUrl && bounds ? (
        <ImageOverlay url={candidateUrl} bounds={bounds} opacity={0.8} zIndex={400} />
      ) : null}
      {layers.polygons && geojson ? (
        <GeoJSON
          key={JSON.stringify(geojson.features?.length || 0) + (bounds ? bounds.join(",") : "")}
          data={geojson}
          style={{
            color: "#7c2d12",
            weight: 1.4,
            fillColor: "#f59e0b",
            fillOpacity: 0.28,
          }}
          onEachFeature={onEachRegion}
        />
      ) : null}
    </MapContainer>
  );
}
