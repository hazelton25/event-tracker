import React, { useState, useEffect } from "react";
import { searchImages, setImageByUrl, setImageByFile } from "../api";

export default function ImagePicker({ event, onClose, onSaved }) {
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [pasteUrl, setPasteUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const fileRef = React.useRef(null);

  const runSearch = async (q) => {
    setLoading(true);
    setErr("");
    try {
      const r = await searchImages(q);
      setResults(r);
      if (r.length === 0) setErr("No suggestions found. Try a paste or upload.");
    } catch {
      setErr("Image search failed (server offline or no internet).");
    }
    setLoading(false);
  };

  useEffect(() => {
    runSearch(event.name);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const apply = async (fn) => {
    setBusy(true);
    setErr("");
    try {
      const updated = await fn();
      onSaved(updated);
    } catch (e) {
      setErr(e?.response?.data?.error || "Could not set image.");
      setBusy(false);
    }
  };

  return (
    <div className="overlay" onClick={onClose}>
      <div className="sheet p-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-1">
          <h2 className="font-stamp font-bold uppercase text-2xl tracking-wide">Set Image</h2>
          <button onClick={onClose} className="font-mono text-sm underline">close</button>
        </div>
        <p className="font-mono text-xs text-faded mb-4">for "{event.name}"</p>

        {/* search box */}
        <div className="flex gap-2 mb-4">
          <input
            defaultValue={event.name}
            onKeyDown={(e) => e.key === "Enter" && runSearch(e.target.value)}
            className="flex-1 bg-stock border-[1.5px] border-ink px-3 py-2 font-mono text-[13px] outline-none focus:border-stamp"
          />
          <button
            onClick={(e) => runSearch(e.target.previousSibling.value)}
            className="font-stamp uppercase text-xs tracking-wide px-4 bg-ink text-stock"
          >
            Search
          </button>
        </div>

        {loading && <p className="font-mono text-xs text-faded">searching Wikipedia…</p>}

        {results.length > 0 && (
          <div className="grid grid-cols-3 gap-3 mb-4">
            {results.map((r, i) => (
              <button
                key={i}
                disabled={busy}
                onClick={() => apply(() => setImageByUrl(event.id, r.url))}
                className="border-[1.5px] border-ink overflow-hidden group disabled:opacity-50"
                title={r.title + (r.description ? ` — ${r.description}` : "")}
              >
                <img
                  src={r.url}
                  alt={r.title}
                  className="w-full h-24 object-cover group-hover:opacity-80"
                  style={{ filter: "sepia(0.2)" }}
                />
                <span className="block font-mono text-[10px] truncate px-1 py-[2px] bg-stock">
                  {r.title}
                </span>
              </button>
            ))}
          </div>
        )}

        {/* paste URL */}
        <label className="font-stamp text-[11px] tracking-[2px] uppercase text-faded mb-1 block">
          Paste image URL
        </label>
        <div className="flex gap-2 mb-4">
          <input
            value={pasteUrl}
            onChange={(e) => setPasteUrl(e.target.value)}
            placeholder="https://…"
            className="flex-1 bg-stock border-[1.5px] border-ink px-3 py-2 font-mono text-[13px] outline-none focus:border-stamp"
          />
          <button
            disabled={busy || !pasteUrl.trim()}
            onClick={() => apply(() => setImageByUrl(event.id, pasteUrl.trim()))}
            className="font-stamp uppercase text-xs tracking-wide px-4 bg-ink text-stock disabled:opacity-50"
          >
            Use
          </button>
        </div>

        {/* upload */}
        <label className="font-stamp text-[11px] tracking-[2px] uppercase text-faded mb-1 block">
          Upload from device
        </label>
        <button
          disabled={busy}
          onClick={() => fileRef.current.click()}
          className="font-mono text-[13px] border-[1.5px] border-ink px-3 py-2 w-full text-left disabled:opacity-50"
        >
          choose a file…
        </button>
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          hidden
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) apply(() => setImageByFile(event.id, f));
          }}
        />

        {err && <p className="text-stamp font-mono text-xs mt-3">{err}</p>}
        {busy && <p className="font-mono text-xs text-faded mt-3">saving image…</p>}
      </div>
    </div>
  );
}
