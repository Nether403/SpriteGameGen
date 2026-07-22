// Stage 2 layout: Generate -> Animate -> Export.
import { AnimatePanel } from "./components/AnimatePanel";
import { ExportPanel } from "./components/ExportPanel";
import { GeneratePanel } from "./components/GeneratePanel";
import { ProjectBrowser } from "./components/ProjectBrowser";
import { WorkspacePanel } from "./components/WorkspacePanel";

export default function App() {
  return (
    <main className="app">
      <header>
        <h1>SpriteGameGen Character Workbench</h1>
        <p>Build, repair, and package a complete local-first character animation set.</p>
      </header>
      <ProjectBrowser />
      <WorkspacePanel />
      <div className="steps">
        <GeneratePanel />
        <AnimatePanel />
        <ExportPanel />
      </div>
    </main>
  );
}
