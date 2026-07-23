// Stage 2 layout: Generate -> Animate -> Export.
import { AnimatePanel } from "./components/AnimatePanel";
import { ExportPanel } from "./components/ExportPanel";
import { GeneratePanel } from "./components/GeneratePanel";
import { ProjectBrowser } from "./components/ProjectBrowser";
import { WorkspacePanel } from "./components/WorkspacePanel";

export default function App() {
  return (
    <main className="app" aria-labelledby="app-title">
      <header className="app-header">
        <div className="brand-lockup">
          <div className="brand-mark" aria-hidden="true">
            <span />
            <span />
            <span />
            <span />
          </div>
          <div>
            <p className="brand-name">SpriteGameGen</p>
            <p className="brand-context">Character workbench / local-first pipeline</p>
          </div>
        </div>
        <div className="header-status"><span className="status-dot" /> Local workspace</div>
        <h1 id="app-title">Build characters that move.</h1>
        <p className="app-lede">Turn a single idea into a production-ready sprite, animation clips, and engine-ready exports.</p>
      </header>
      <ProjectBrowser />
      <WorkspacePanel />
      <div className="workflow-heading">
        <div>
          <p className="eyebrow">The production line</p>
          <h2>From prompt to playable</h2>
        </div>
        <p className="hint">Generate a base, shape the motion, then take the files with you.</p>
      </div>
      <div className="steps" aria-label="Character production steps">
        <GeneratePanel />
        <AnimatePanel />
        <ExportPanel />
      </div>
    </main>
  );
}
