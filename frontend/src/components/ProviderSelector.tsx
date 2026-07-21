import { useEffect, useState } from "react";

import {
  listImageProviders,
  isAbortError,
  type ImageProviderName,
  type ImageProviderOption,
} from "../api/client";
import { useProjectStore } from "../state/project";

interface ProviderSelectorProps {
  id: string;
  value?: ImageProviderName;
  onChange?: (provider: ImageProviderName) => void;
  disabled?: boolean;
}

export function ProviderSelector({ id, value, onChange, disabled }: ProviderSelectorProps) {
  const { provider: draftProvider, setProvider } = useProjectStore();
  const provider = value ?? draftProvider;
  const changeProvider = onChange ?? setProvider;
  const [options, setOptions] = useState<ImageProviderOption[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    listImageProviders({ signal: controller.signal })
      .then(setOptions)
      .catch((reason) => {
        if (!isAbortError(reason)) setError("Could not load image providers.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [attempt]);

  const selected = options.find((option) => option.id === provider);

  return (
    <div className="provider-selector">
      <label htmlFor={id}>Image provider</label>
      <select
        id={id}
        value={provider}
        onChange={(event) => changeProvider(event.target.value as ImageProviderName)}
        disabled={disabled || loading || options.length === 0}
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
      {loading && <p className="hint" role="status">Loading image providers…</p>}
      {error && (
        <div className="metadata-error">
          <p className="error" role="alert">{error}</p>
          <button type="button" className="secondary-button" onClick={() => setAttempt((value) => value + 1)}>
            Retry providers
          </button>
        </div>
      )}
    </div>
  );
}
