import { useEffect, useMemo, useState } from "react";
import {
  getGeoJson,
  getHealth,
  getRun,
  listRuns,
  listProjects,
  startProcessing,
  uploadGeotiff,
} from "./api";
import MapView from "./MapView";

const EMPTY_LAYERS = {
  image: true,
  buildings: true,
  candidates: true,
  polygons: true,
};

function formatWhen(value) {
  if (!value) {
    return "—";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

export default function App() {
  const [health, setHealth] = useState(null);
  const [runs, setRuns] = useState([]);
  const [projects, setProjects] = useState([]);
  const [activeRun, setActiveRun] = useState(null);
  const [uploaded, setUploaded] = useState(null);
  const [geojson, setGeojson] = useState(null);
  const [layers, setLayers] = useState(EMPTY_LAYERS);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function refreshRuns(preferredRunId) {
    const nextRuns = await listRuns();
    setRuns(nextRuns);
    if (preferredRunId) {
      const match = nextRuns.find((run) => run.run_id === preferredRunId);
      if (match) {
        setActiveRun(match);
      }
    }
    return nextRuns;
  }

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const [healthResult, runResult, projectResult] = await Promise.all([
          getHealth(),
          listRuns(),
          listProjects(),
        ]);
        if (cancelled) {
          return;
        }
        setHealth(healthResult);
        setRuns(runResult);
        setProjects(projectResult);
        if (runResult.length > 0) {
          setActiveRun(runResult[0]);
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError.message);
        }
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!activeRun || !["pending", "processing"].includes(activeRun.status)) {
      return undefined;
    }

    const timer = setInterval(async () => {
      try {
        const run = await getRun(activeRun.run_id);
        setActiveRun(run);
        setRuns((current) =>
          current.map((item) => (item.run_id === run.run_id ? run : item))
        );
        if (run.status === "failed") {
          setError(run.error_message || "Processing failed.");
        }
      } catch (pollError) {
        setError(pollError.message);
      }
    }, 2000);

    return () => clearInterval(timer);
  }, [activeRun?.run_id, activeRun?.status]);

  useEffect(() => {
    if (!activeRun || activeRun.status !== "completed") {
      setGeojson(null);
      return undefined;
    }

    let cancelled = false;
    getGeoJson(activeRun.run_id)
      .then((data) => {
        if (!cancelled) {
          setGeojson(data);
        }
      })
      .catch((geoError) => {
        if (!cancelled) {
          setError(geoError.message);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [activeRun?.run_id, activeRun?.status]);

  const mapSubject = activeRun || uploaded;

  const previewUrl = mapSubject?.preview_url || null;
  const buildingUrl = activeRun?.status === "completed"
    ? `${activeRun.building_overlay_url}?v=${encodeURIComponent(activeRun.completed_at || "")}`
    : null;
  const candidateUrl = activeRun?.status === "completed"
    ? `${activeRun.candidate_overlay_url}?v=${encodeURIComponent(activeRun.completed_at || "")}`
    : null;

  const totalArea = useMemo(() => {
    if (!geojson) {
      return 0;
    }
    return geojson.features.reduce(
      (sum, feature) => sum + Number(feature.properties?.area_sqm || 0),
      0
    );
  }, [geojson]);

  async function onUpload(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) {
      return;
    }

    setBusy(true);
    setError("");
    setMessage("");
    try {
      const project = await uploadGeotiff(file);
      setProjects((current) => [
        project,
        ...current.filter((item) => item.project_id !== project.project_id),
      ]);
      setUploaded(project);
      setActiveRun(null);
      setGeojson(null);
      setMessage(`${project.image_name} passed validation. ${project.width}×${project.height}, ${project.bands} bands, ${project.crs}.`);
    } catch (uploadError) {
      setError(uploadError.message);
    } finally {
      setBusy(false);
    }
  }

  async function onProcess() {
    if (!uploaded) {
      return;
    }
    setBusy(true);
    setError("");
    try {
      const started = await startProcessing(uploaded.project_id);
      const run = await getRun(started.run_id);
      setActiveRun(run);
      await refreshRuns(run.run_id);
      setMessage(`Processing ${run.image_name}. Building detection is running.`);
    } catch (processError) {
      setError(processError.message);
    } finally {
      setBusy(false);
    }
  }

  function toggleLayer(name) {
    setLayers((current) => ({ ...current, [name]: !current[name] }));
  }

  return (
    <div className="app-shell">
      <aside className="side-panel">
        <header className="brand">
          <p className="eyebrow">SIH 2026</p>
          <h1>Urban Parcel Mapping</h1>
          <p className="lede">
            Upload a georeferenced aerial image, detect buildings, and review candidate open regions.
          </p>
        </header>

        <section className="panel-block">
          <div className="status-row">
            <span className={health?.database ? "dot ok" : "dot bad"} />
            <span>
              {health
                ? health.database
                  ? "PostGIS connected"
                  : "Database unavailable"
                : "Checking services"}
            </span>
          </div>
          <div className="status-row">
            <span className={health?.model ? "dot ok" : "dot bad"} />
            <span>{health?.model ? "ONNX model found" : "ONNX model missing"}</span>
          </div>
        </section>

        <section className="panel-block">
          <h2>Upload GeoTIFF</h2>
          <label className="upload-control">
            <input
              type="file"
              accept=".tif,.tiff,image/tiff"
              onChange={onUpload}
              disabled={busy}
            />
            <span>{busy ? "Working…" : "Choose a GeoTIFF"}</span>
          </label>
          {uploaded ? (
            <div className="meta-card">
              <img src={uploaded.preview_url} alt="Uploaded GeoTIFF preview" />
              <dl>
                <div><dt>File</dt><dd>{uploaded.image_name}</dd></div>
                <div><dt>Size</dt><dd>{uploaded.width} × {uploaded.height}</dd></div>
                <div><dt>Bands</dt><dd>{uploaded.bands}</dd></div>
                <div><dt>CRS</dt><dd>{uploaded.crs}</dd></div>
              </dl>
              <button type="button" onClick={onProcess} disabled={busy}>
                Process image
              </button>
            </div>
          ) : (
            <p className="hint">The file is checked for dimensions, at least three bands, and a CRS before it is stored.</p>
          )}
        </section>

        {activeRun ? (
          <section className="panel-block">
            <h2>Current run</h2>
            <p className={`run-state ${activeRun.status}`}>{activeRun.status}</p>
            {activeRun.status === "processing" ? (
              <p className="hint">
                {activeRun.stage?.replaceAll("_", " ") || "Starting"}
                {activeRun.progress_total > 0
                  ? ` · ${activeRun.progress_current || 0}/${activeRun.progress_total} ${activeRun.stage === "building_detection" ? "tiles" : "regions"}`
                  : "…"}
              </p>
            ) : null}
            <dl className="compact">
              <div><dt>Image</dt><dd>{activeRun.image_name}</dd></div>
              <div><dt>Buildings</dt><dd>{Number(activeRun.building_pixels || 0).toLocaleString()} px</dd></div>
              <div><dt>Regions</dt><dd>{activeRun.candidate_regions || 0}</dd></div>
              <div><dt>Area</dt><dd>{totalArea.toLocaleString(undefined, { maximumFractionDigits: 0 })} m²</dd></div>
            </dl>
            {activeRun.status === "completed" ? (
              <div className="downloads">
                <a href={activeRun.download_geojson_url}>GeoJSON</a>
                <a href={activeRun.download_building_mask_url}>Building mask</a>
                <a href={activeRun.download_candidate_mask_url}>Region mask</a>
              </div>
            ) : null}
          </section>
        ) : null}

        <section className="panel-block runs">
          <h2>Projects</h2>
          {projects.length === 0 ? <p className="hint">No uploaded projects yet.</p> : null}
          <ul>
            {projects.map((project) => (
              <li key={project.project_id}>
                <button
                  type="button"
                  className={uploaded?.project_id === project.project_id ? "selected" : ""}
                  onClick={() => {
                    setUploaded(project);
                    setActiveRun(null);
                    setGeojson(null);
                    setError("");
                  }}
                >
                  <strong>{project.project_name}</strong>
                  <span>{project.width} × {project.height} · {project.crs}</span>
                  <span>{formatWhen(project.created_at)}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>

        <section className="panel-block layers">
          <h2>Map layers</h2>
          {[
            ["image", "Image"],
            ["buildings", "Buildings"],
            ["candidates", "Open regions"],
            ["polygons", "Polygons"],
          ].map(([key, label]) => (
            <label key={key}>
              <input
                type="checkbox"
                checked={layers[key]}
                onChange={() => toggleLayer(key)}
              />
              {label}
            </label>
          ))}
        </section>

        <section className="panel-block runs">
          <h2>Previous runs</h2>
          {runs.length === 0 ? <p className="hint">No processing runs yet.</p> : null}
          <ul>
            {runs.map((run) => (
              <li key={run.run_id}>
                <button
                  type="button"
                  className={activeRun?.run_id === run.run_id ? "selected" : ""}
                  onClick={() => {
                    setActiveRun(run);
                    setUploaded(null);
                    setError("");
                  }}
                >
                  <strong>{run.image_name}</strong>
                  <span>{run.status} · {run.candidate_regions || 0} regions</span>
                  <span>{formatWhen(run.started_at)}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>

        {message ? <p className="banner info">{message}</p> : null}
        {error ? <p className="banner error">{error}</p> : null}
      </aside>
      <main className="map-stage">
        <MapView
          bounds={mapSubject?.bounds || null}
          previewUrl={previewUrl}
          buildingUrl={buildingUrl}
          candidateUrl={candidateUrl}
          geojson={geojson}
          layers={layers}
        />
      </main>
    </div>
  );
}
