import React, { useState } from "react";
import { motion } from "framer-motion";
import TicketImage from "./TicketImage";
import { extractDroppedImage } from "../lib/imageDrop";
import { setImageByUrl, setImageByFile } from "../api";

const TYPE_META = {
  concert: { label: "Concert", color: "#B33A2B" },
  sports: { label: "Sports", color: "#3E6B68" },
  festival: { label: "Festival", color: "#9A6A1E" },
  theatre: { label: "Theatre", color: "#6B2F6B" },
  other: { label: "Event", color: "#5a4f3d" },
};

function fmtDate(d) {
  if (!d) return "DATE TBD";
  const dt = new Date(d + "T00:00:00");
  if (isNaN(dt)) return d;
  return dt
    .toLocaleDateString("en-US", { month: "short", day: "2-digit", year: "numeric" })
    .toUpperCase()
    .replace(",", " ·");
}

function Stars({ rating }) {
  if (!rating) return <span className="text-faded text-xs">unrated</span>;
  return (
    <span className="text-gold tracking-widest text-sm">
      {"★".repeat(rating)}
      <span className="text-faded">{"☆".repeat(5 - rating)}</span>
    </span>
  );
}

export default function TicketCard({ event, index, onEdit, onDelete, onImage, onImageDropped }) {
  const [flipped, setFlipped] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const meta = TYPE_META[event.event_type] || TYPE_META.other;
  const serial = "№ " + String(event.id).padStart(6, "0");
  const setlistLines = (event.setlist || "")
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);

  const stop = (e, fn) => {
    e.stopPropagation();
    fn();
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(true);
  };

  const handleDragLeave = (e) => {
    if (!e.currentTarget.contains(e.relatedTarget)) setDragOver(false);
  };

  const handleDrop = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
    const dropped = extractDroppedImage(e.dataTransfer);
    if (!dropped) return;
    try {
      const updated =
        dropped.type === "file"
          ? await setImageByFile(event.id, dropped.file)
          : await setImageByUrl(event.id, dropped.url);
      onImageDropped(updated);
    } catch {
      // best-effort — the picker's own drop zone reports errors explicitly
    }
  };

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: Math.min(index * 0.04, 0.4) }}
      className={`flip-wrap${flipped ? " flipped" : ""}`}
      style={{ height: 260, filter: "drop-shadow(3px 5px 0 rgba(43,33,24,.25))" }}
      onClick={() => setFlipped((f) => !f)}
    >
      <div className="flip-inner">
        {/* FRONT */}
        <div className="face front">
          <div className="stub">
            <div
              className={`stub-main ticket-drop-target${event.image_url ? " has-photo" : ""}${dragOver ? " drag-over" : ""}`}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
            >
              {event.image_url ? (
                <>
                  <TicketImage event={event} frameProps={{ className: "ticket-photo-card" }} />
                  <div className="ticket-scrim" />
                  <span className="ticket-photo-badge inline-block font-mono text-[10px] tracking-[2px] uppercase px-2 py-[2px] text-gold border border-gold">
                    {meta.label}
                  </span>
                  <div className="ticket-photo-content">
                    <h3 className="font-stamp font-bold uppercase leading-[1.05] tracking-wide text-[22px] text-stock">
                      {event.name}
                    </h3>
                    <div className="font-mono text-[13px] mt-2 text-[#d8cbb3]">
                      {event.venue}
                      {event.city ? ` — ${event.city}` : ""}
                    </div>
                    <div className="mt-2 flex justify-between items-end">
                      <span className="font-stamp font-semibold text-[15px] tracking-wide text-stock">
                        {fmtDate(event.date)}
                      </span>
                      <span className="stamp">ATTENDED</span>
                    </div>
                  </div>
                </>
              ) : (
                <>
                  <span
                    className="inline-block font-mono text-[10px] tracking-[2px] uppercase px-2 py-[2px] mb-2"
                    style={{ border: `1px solid ${meta.color}`, color: meta.color }}
                  >
                    {meta.label}
                  </span>
                  <h3 className="font-stamp font-bold uppercase leading-[1.05] tracking-wide text-[22px]">
                    {event.name}
                  </h3>
                  <div className="font-mono text-[13px] mt-2 text-[#5a4f3d]">
                    {event.venue}
                    {event.city ? ` — ${event.city}` : ""}
                  </div>

                  <div className="absolute bottom-3 left-[18px] right-[18px] flex justify-between items-end">
                    <span className="font-stamp font-semibold text-[15px] tracking-wide">
                      {fmtDate(event.date)}
                    </span>
                    <span className="stamp">ATTENDED</span>
                  </div>
                </>
              )}
            </div>
            <div className="stub-side">
              <span className="admit">Admit One</span>
              <span className="serial">{serial}</span>
            </div>
          </div>
        </div>

        {/* BACK */}
        <div className="face back">
          <div className="stub-back flex flex-col">
            <div className="flex justify-between items-start mb-1">
              <h4 className="font-stamp text-[13px] tracking-[2px] uppercase text-stamp">
                {event.event_type === "concert" ? "Setlist" : "Notes"}
              </h4>
              <div className="flex gap-2 relative z-10">
                <button
                  title="Set image"
                  onClick={(e) => stop(e, () => onImage(event))}
                  className="font-mono text-[11px] underline text-ink"
                >
                  img
                </button>
                <button
                  title="Edit"
                  onClick={(e) => stop(e, () => onEdit(event))}
                  className="font-mono text-[11px] underline text-ink"
                >
                  edit
                </button>
                <button
                  title="Delete"
                  onClick={(e) => stop(e, () => onDelete(event))}
                  className="font-mono text-[11px] underline text-stamp"
                >
                  del
                </button>
              </div>
            </div>

            <div className="scroll-area flex-1 pr-1">
              {event.event_type === "concert" && setlistLines.length > 0 ? (
                <ol className="font-mono text-[12px] leading-[1.5] columns-2 gap-6">
                  {setlistLines.map((line, i) => (
                    <li key={i} className="break-inside-avoid">
                      {line}
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="font-mono text-[12px] leading-[1.5] whitespace-pre-wrap">
                  {event.notes || "No notes yet."}
                </p>
              )}
            </div>

            <div className="flex justify-between items-end mt-2 font-mono text-[11px] text-[#5a4f3d] relative z-10">
              <span>{event.attendees ? `w/ ${event.attendees}` : "solo"}</span>
              <Stars rating={event.rating} />
            </div>
          </div>
        </div>
      </div>
    </motion.div>
  );
}

export { TYPE_META };
