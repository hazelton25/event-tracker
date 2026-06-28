import React, { useState, useEffect, useCallback } from "react";
import { AnimatePresence } from "framer-motion";
import TicketCard from "./components/TicketCard";
import EventModal from "./components/EventModal";
import ImagePicker from "./components/ImagePicker";
import BackupControls from "./components/BackupControls";
import {
  listEvents,
  createEvent,
  updateEvent,
  deleteEvent,
} from "./api";

const FILTERS = [
  { key: "all", label: "All" },
  { key: "concert", label: "Concerts" },
  { key: "sports", label: "Sports" },
  { key: "festival", label: "Festivals" },
  { key: "theatre", label: "Theatre" },
  { key: "other", label: "Other" },
];

const SORTS = [
  { key: "date|desc", label: "Date ↓" },
  { key: "date|asc", label: "Date ↑" },
  { key: "name|asc", label: "Name A–Z" },
  { key: "rating|desc", label: "Top rated" },
];

export default function App() {
  const [events, setEvents] = useState([]);
  const [filter, setFilter] = useState("all");
  const [sort, setSort] = useState("date|desc");
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null); // event obj or {} for new
  const [imaging, setImaging] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    const [sortKey, order] = sort.split("|");
    try {
      const data = await listEvents({ type: filter, sort: sortKey, order });
      setEvents(data);
    } catch {
      setEvents([]);
    }
    setLoading(false);
  }, [filter, sort]);

  useEffect(() => {
    load();
  }, [load]);

  const handleSave = async (payload) => {
    if (editing && editing.id) {
      await updateEvent(editing.id, payload);
    } else {
      await createEvent(payload);
    }
    setEditing(null);
    load();
  };

  const handleDelete = async (event) => {
    if (window.confirm(`Delete "${event.name}"? This can't be undone.`)) {
      await deleteEvent(event.id);
      load();
    }
  };

  const handleImageSaved = (updated) => {
    setEvents((prev) => prev.map((e) => (e.id === updated.id ? updated : e)));
    setImaging(null);
  };

  return (
    <div className="min-h-screen pb-20">
      {/* header */}
      <header className="px-6 pt-10 pb-4 text-center relative">
        <div className="absolute top-6 right-6 hidden sm:block">
          <BackupControls onImported={load} />
        </div>
        <div className="font-mono text-[12px] tracking-[4px] text-stamp">★ ADMIT ONE ★</div>
        <h1 className="font-stamp font-bold uppercase tracking-[3px] text-[clamp(36px,6vw,60px)]">
          Ticket <span className="text-stamp">Stubs</span>
        </h1>
        <div className="w-[120px] h-[3px] bg-ink mx-auto mt-3" />
        <p className="font-mono text-[12px] text-faded mt-3">
          {events.length} event{events.length === 1 ? "" : "s"} logged
        </p>
      </header>

      {/* mobile backup controls */}
      <div className="sm:hidden flex justify-center mb-2">
        <BackupControls onImported={load} />
      </div>

      {/* controls */}
      <div className="flex flex-wrap gap-2 justify-center px-4 py-6">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            className={`font-mono text-[12px] tracking-[1px] uppercase border-[1.5px] border-ink px-4 py-[7px] ${
              filter === f.key ? "bg-ink text-stock" : "text-ink"
            }`}
          >
            {f.label}
          </button>
        ))}
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value)}
          className="font-mono text-[12px] tracking-[1px] uppercase border-[1.5px] border-ink px-3 bg-paper text-ink"
        >
          {SORTS.map((s) => (
            <option key={s.key} value={s.key}>
              Sort: {s.label}
            </option>
          ))}
        </select>
        <button
          onClick={() => setEditing({})}
          className="font-stamp uppercase tracking-wide text-[13px] border-[1.5px] border-stamp bg-stamp text-stock px-4 py-[6px]"
        >
          + New Ticket
        </button>
      </div>

      {/* grid */}
      {loading ? (
        <p className="text-center font-mono text-faded mt-12">loading tickets…</p>
      ) : events.length === 0 ? (
        <div className="text-center mt-16">
          <p className="font-stamp uppercase tracking-wide text-xl mb-2">No tickets yet</p>
          <p className="font-mono text-sm text-faded mb-5">
            Add your first event to start the stub collection.
          </p>
          <button
            onClick={() => setEditing({})}
            className="font-stamp uppercase tracking-wide text-sm border-[1.5px] border-ink bg-ink text-stock px-5 py-2"
          >
            + New Ticket
          </button>
        </div>
      ) : (
        <div
          className="grid gap-9 justify-center px-6"
          style={{ gridTemplateColumns: "repeat(auto-fill, minmax(340px, 440px))" }}
        >
          {events.map((ev, i) => (
            <TicketCard
              key={ev.id}
              event={ev}
              index={i}
              onEdit={setEditing}
              onDelete={handleDelete}
              onImage={setImaging}
            />
          ))}
        </div>
      )}

      <AnimatePresence>
        {editing && (
          <EventModal
            event={editing.id ? editing : null}
            onClose={() => setEditing(null)}
            onSave={handleSave}
          />
        )}
      </AnimatePresence>

      {imaging && (
        <ImagePicker
          event={imaging}
          onClose={() => setImaging(null)}
          onSaved={handleImageSaved}
        />
      )}
    </div>
  );
}
