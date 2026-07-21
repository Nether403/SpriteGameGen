import { useEffect, useState } from "react";

import {
  deleteProject,
  getProject,
  listProjects,
  type ProjectSummary,
} from "../api/client";
import { useProjectStore } from "../state/project";

function formatUpdated(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "Unknown date" : date.toLocaleString();
}

function statusText(project: ProjectSummary): string {
  if (project.health === "corrupt") return "Cannot read manifest";
  if (project.health === "incomplete") return "Needs attention before resume";
  if (project.failed_count > 0) {
    return `${project.ok_count}/${project.frame_count} frames ready · ${project.failed_count} failed`;
  }
  return `${project.frame_count} frame${project.frame_count === 1 ? "" : "s"} ready`;
}

export function ProjectBrowser() {
  const { projectId, catalogRevision, loadProject, reset } = useProjectStore();
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshNonce, setRefreshNonce] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    listProjects()
      .then((items) => {
        if (active) setProjects(items);
      })
      .catch((reason) => {
        if (active) setError(reason instanceof Error ? reason.message : "Could not load projects.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [catalogRevision, refreshNonce]);

  async function onOpen(project: ProjectSummary) {
    if (!project.resume_available || busyId !== null) return;
    setBusyId(project.id);
    setError(null);
    try {
      loadProject(await getProject(project.id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not open project.");
    } finally {
      setBusyId(null);
    }
  }

  async function onDelete(project: ProjectSummary) {
    if (busyId !== null || !window.confirm(`Delete project “${project.prompt_preview || project.id}”?`)) return;
    setBusyId(project.id);
    setError(null);
    try {
      await deleteProject(project.id);
      setProjects((items) => items.filter((item) => item.id !== project.id));
      if (project.id === projectId) reset();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not delete project.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section className="project-browser panel" aria-labelledby="projects-heading">
      <div className="project-browser-header">
        <div>
          <h2 id="projects-heading">Saved projects</h2>
          <p className="hint">Resume a sprite or animation from your local project library.</p>
        </div>
        <button
          type="button"
          className="secondary-button"
          onClick={() => setRefreshNonce((value) => value + 1)}
          disabled={loading}
        >
          Refresh
        </button>
      </div>

      {loading && (
        <div className="project-browser-state" role="status" aria-busy="true">
          Loading saved projects…
        </div>
      )}
      {!loading && error && <p className="error" role="alert">{error}</p>}
      {!loading && !error && projects.length === 0 && (
        <div className="project-browser-state" role="status">
          <strong>No saved projects yet.</strong>
          <span>Generate a sprite below to start your local library.</span>
        </div>
      )}
      {!loading && !error && projects.length > 0 && (
        <ul className="project-list" aria-label="Saved projects">
          {projects.map((project) => {
            const active = project.id === projectId;
            return (
              <li key={project.id} className={`project-card${active ? " project-card-active" : ""}`}>
                <div className="project-thumbnail">
                  {project.thumbnail_url ? (
                    <img src={project.thumbnail_url} alt="" />
                  ) : (
                    <span aria-hidden="true">?</span>
                  )}
                </div>
                <div className="project-card-content">
                  <div className="project-card-title-row">
                    <h3>{project.prompt_preview || "Unreadable project"}</h3>
                    {active && <span className="project-active-label">Open</span>}
                  </div>
                  <p className="project-card-meta">
                    {project.style || "Unknown style"}
                    {project.action ? ` · ${project.action}` : " · Not animated"}
                  </p>
                  <p className={`project-card-status project-status-${project.health}`}>
                    {statusText(project)}
                  </p>
                  <p className="project-card-updated">Updated {formatUpdated(project.updated_at)}</p>
                  <div className="project-card-actions">
                    <button
                      type="button"
                      onClick={() => onOpen(project)}
                      disabled={!project.resume_available || busyId !== null}
                    >
                      {busyId === project.id ? "Opening…" : project.resume_available ? "Open project" : "Cannot resume"}
                    </button>
                    <button
                      type="button"
                      className="secondary-button"
                      aria-label={`Delete project ${project.id}`}
                      onClick={() => onDelete(project)}
                      disabled={busyId !== null}
                    >
                      {busyId === project.id ? "Working…" : "Delete"}
                    </button>
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
