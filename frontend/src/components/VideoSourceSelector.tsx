import { useEffect, useState } from "react";
import { fetchSources, switchSource } from "../lib/api";
import type { VideoSourceOption } from "../lib/types";

interface Props {
  onSwitched?: () => void;
}

/** Lets the operator pick which camera feed / demo clip is being processed.
 * Switching resets all lane counts and the signal timer on the backend, since
 * counts from a different clip aren't meaningful to carry over. */
export function VideoSourceSelector({ onSwitched }: Props) {
  const [sources, setSources] = useState<VideoSourceOption[]>([]);
  const [active, setActive] = useState<string>("");
  const [switching, setSwitching] = useState(false);

  useEffect(() => {
    fetchSources()
      .then((res) => {
        setSources(res.sources);
        setActive(res.active);
      })
      .catch(() => {
        // no sources loaded — selector just stays empty, not fatal
      });
  }, []);

  const handleChange = async (source: string) => {
    if (source === active || switching) return;
    setSwitching(true);
    try {
      await switchSource(source);
      setActive(source);
      onSwitched?.();
    } catch (err) {
      console.error("source switch failed", err);
    } finally {
      setSwitching(false);
    }
  };

  if (sources.length <= 1) return null;

  return (
    <label className="source-selector">
      <span>Feed</span>
      <select value={active} disabled={switching} onChange={(e) => handleChange(e.target.value)}>
        {sources.map((s) => (
          <option key={s.id} value={s.id}>
            {s.label}
          </option>
        ))}
      </select>
      {switching && <span className="source-switching">switching…</span>}
    </label>
  );
}
