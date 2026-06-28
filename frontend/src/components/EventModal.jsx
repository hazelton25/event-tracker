import React, { useState } from "react";

const FIELD = "w-full bg-stock border-[1.5px] border-ink px-3 py-2 font-mono text-[13px] outline-none focus:border-stamp";
const LABEL = "font-stamp text-[11px] tracking-[2px] uppercase text-faded mb-1 block";

const EVENT_TYPES = ["concert", "sports", "festival", "theatre", "other"];

export default function EventModal({ event, onClose, onSave }) {
  const isEdit = Boolean(event && event.id);
  const [form, setForm] = useState({
    name: event?.name || "",
    event_type: event?.event_type || "concert",
    date: event?.date || "",
    venue: event?.venue || "",
    city: event?.city || "",
    setlist: event?.setlist || "",
    notes: event?.notes || "",
    attendees: event?.attendees || "",
    rating: event?.rating || 0,
  });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");

  const set = (k) => (e) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async () => {
    if (!form.name.trim()) {
      setErr("Name is required.");
      return;
    }
    setSaving(true);
    setErr("");
    try {
      await onSave({ ...form, rating: Number(form.rating) || null });
    } catch (e) {
      setErr("Could not save. Check the server is running.");
      setSaving(false);
    }
  };

  const isConcert = form.event_type === "concert";

  return (
    <div className="overlay" onClick={onClose}>
      <div className="sheet p-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-4">
          <h2 className="font-stamp font-bold uppercase text-2xl tracking-wide">
            {isEdit ? "Edit Ticket" : "New Ticket"}
          </h2>
          <button onClick={onClose} className="font-mono text-sm underline">
            close
          </button>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="col-span-2">
            <label className={LABEL}>Event Name</label>
            <input className={FIELD} value={form.name} onChange={set("name")} placeholder="The National" />
          </div>
          <div>
            <label className={LABEL}>Type</label>
            <select className={FIELD} value={form.event_type} onChange={set("event_type")}>
              {EVENT_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t[0].toUpperCase() + t.slice(1)}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className={LABEL}>Date</label>
            <input type="date" className={FIELD} value={form.date} onChange={set("date")} />
          </div>
          <div>
            <label className={LABEL}>Venue</label>
            <input className={FIELD} value={form.venue} onChange={set("venue")} placeholder="Massey Hall" />
          </div>
          <div>
            <label className={LABEL}>City</label>
            <input className={FIELD} value={form.city} onChange={set("city")} placeholder="Toronto, ON" />
          </div>

          {isConcert ? (
            <div className="col-span-2">
              <label className={LABEL}>Setlist (one per line)</label>
              <textarea
                className={FIELD}
                rows={4}
                value={form.setlist}
                onChange={set("setlist")}
                placeholder={"Sea of Love\nBloodbuzz Ohio\nI Need My Girl"}
              />
            </div>
          ) : null}

          <div className="col-span-2">
            <label className={LABEL}>Notes</label>
            <textarea className={FIELD} rows={3} value={form.notes} onChange={set("notes")} />
          </div>
          <div>
            <label className={LABEL}>Attendees</label>
            <input className={FIELD} value={form.attendees} onChange={set("attendees")} placeholder="Sarah & Mike" />
          </div>
          <div>
            <label className={LABEL}>Rating</label>
            <div className="flex gap-1 pt-1">
              {[1, 2, 3, 4, 5].map((n) => (
                <button
                  key={n}
                  onClick={() => setForm((f) => ({ ...f, rating: n }))}
                  className="text-2xl leading-none"
                  style={{ color: n <= form.rating ? "#C9A227" : "#cbbfa6" }}
                >
                  ★
                </button>
              ))}
              {form.rating > 0 && (
                <button
                  onClick={() => setForm((f) => ({ ...f, rating: 0 }))}
                  className="font-mono text-[11px] underline ml-2 text-faded"
                >
                  clear
                </button>
              )}
            </div>
          </div>
        </div>

        {err && <p className="text-stamp font-mono text-xs mt-3">{err}</p>}

        <div className="flex justify-end gap-3 mt-5">
          <button onClick={onClose} className="font-mono text-sm px-4 py-2 underline">
            cancel
          </button>
          <button
            onClick={submit}
            disabled={saving}
            className="font-stamp uppercase tracking-wide text-sm px-5 py-2 bg-ink text-stock disabled:opacity-50"
          >
            {saving ? "saving…" : isEdit ? "Save changes" : "Add ticket"}
          </button>
        </div>
      </div>
    </div>
  );
}
