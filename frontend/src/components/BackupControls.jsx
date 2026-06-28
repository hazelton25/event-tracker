import React, { useRef, useState } from "react";
import { importBackup } from "../api";

export default function BackupControls({ onImported }) {
  const fileRef = useRef(null);
  const [busy, setBusy] = useState(false);

  const onImport = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const ok = window.confirm(
      "Importing replaces ALL current events and images with the contents of this backup. " +
        "A safety copy of the current database is kept on the server. Continue?"
    );
    if (!ok) {
      e.target.value = "";
      return;
    }
    setBusy(true);
    try {
      await importBackup(file);
      onImported();
    } catch {
      window.alert("Import failed — make sure it's an Event Tracker backup zip.");
    }
    setBusy(false);
    e.target.value = "";
  };

  const btn =
    "font-mono text-[11px] tracking-[1px] uppercase border-[1.5px] border-ink text-ink px-3 py-[6px] hover:bg-ink hover:text-stock transition-colors";

  return (
    <div className="flex gap-2 items-center">
      <a href="/api/backup" className={btn} style={{ textDecoration: "none" }}>
        ↓ Backup
      </a>
      <button className={btn} disabled={busy} onClick={() => fileRef.current.click()}>
        {busy ? "importing…" : "↑ Import"}
      </button>
      <input ref={fileRef} type="file" accept=".zip" hidden onChange={onImport} />
    </div>
  );
}
