// Stage 1 layout: Generate -> Export. Stage 2 inserts an Animate step between.
import { ExportPanel } from "./components/ExportPanel";
import { GeneratePanel } from "./components/GeneratePanel";

export default function App() {
  return (
    <main className="app">
      <header>
        <h1>AI Sprite &amp; Game Asset Tool</h1>
        <p>Describe a sprite, get a clean engine-ready asset.</p>
      </header>
      <div className="steps">
        <GeneratePanel />
        <ExportPanel />
      </div>
    </main>
  );
}
