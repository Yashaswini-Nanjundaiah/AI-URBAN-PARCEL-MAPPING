async function parseResponse(response) {
  const text = await response.text();
  let data = null;

  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { detail: text };
    }
  }

  if (!response.ok) {
    const detail = data && data.detail ? data.detail : response.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }

  return data;
}

export async function getHealth() {
  const response = await fetch("/api/health");
  return parseResponse(response);
}

export async function uploadGeotiff(file) {
  const body = new FormData();
  body.append("file", file);
  const response = await fetch("/api/uploads", {
    method: "POST",
    body,
  });
  return parseResponse(response);
}

export async function startProcessing(projectId) {
  const response = await fetch(`/api/projects/${projectId}/process`, {
    method: "POST",
  });
  return parseResponse(response);
}

export async function listRuns() {
  const response = await fetch("/api/runs");
  return parseResponse(response);
}

export async function listProjects() {
  const response = await fetch("/api/projects");
  return parseResponse(response);
}

export async function getRun(runId) {
  const response = await fetch(`/api/runs/${runId}`);
  return parseResponse(response);
}

export async function getGeoJson(runId) {
  const response = await fetch(`/api/runs/${runId}/geojson`);
  return parseResponse(response);
}
