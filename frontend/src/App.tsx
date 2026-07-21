// Stage 2 layout: Generate -> Animate -> Export.
import { AnimatePanel } from "./components/AnimatePanel";
import { ExportPanel } from "./components/ExportPanel";
import { GeneratePanel } from "./components/GeneratePanel";
import { ProjectBrowser } from "./components/ProjectBrowser";

export default function App() {
  return (
    <main className="app">
      <header>
        <h1>AI Sprite &amp; Game Asset Tool</h1>
        <p>Describe a sprite, animate it, get a clean engine-ready sheet.</p>
      </header>
      <ProjectBrowser />
      <div className="steps">
        <GeneratePanel />
        <AnimatePanel />
        <ExportPanel />
      </div>
    </main>
  );
}
