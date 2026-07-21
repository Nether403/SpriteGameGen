import { useEffect, useState } from "react";

import {
  listImageProviders,
  type ImageProviderName,
  type ImageProviderOption,
} from "../api/client";
import { useProjectStore } from "../state/project";

export function ProviderSelector({ id }: { id: string }) {
  const { provider, setProvider } = useProjectStore();
  const [options, setOptions] = useState<ImageProviderOption[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listImageProviders()
      .then(setOptions)
      .catch(() => setError("Could not load image providers."));
  }, []);

  const selected = options.find((option) => option.id === provider);

  return (
    <div className="provider-selector">
      <label htmlFor={id}>Image provider</label>
      <select
        id={id}
        value={provider}
        onChange={(event) => setProvider(event.target.value as ImageProviderName)}
        disabled={options.length === 0}
      >
        {options.map((option) => (
          <option key={option.id} value={option.id} disabled={!option.available}>
            {option.label}{option.experimental ? " (Experimental)" : ""}
            {!option.available ? " — unavailable" : ""}
          </option>
        ))}
      </select>
      {selected && (
        <p className={selected.available ? "hint" : "error"}>
          {selected.available
            ? selected.description
            : selected.unavailable_reason ?? selected.description}
        </p>
      )}
      {error && <p className="error">{error}</p>}
    </div>
  );
}
