import React, { useCallback, useEffect, useRef, useState } from "react";
import TicketImage from "./TicketImage";
import { adjustImage } from "../api";

function clamp(v, min, max) {
  return Math.min(max, Math.max(min, v));
}

// Pan/zoom control for the ticket's image band. Shows the exact same crop
// (`TicketImage`) the card renders, live-updated while dragging/sliding, and
// persists non-destructively — the source image file is never touched.
export default function ImageAdjust({ event, onChange }) {
  const [zoom, setZoom] = useState(event.image_zoom ?? 1);
  const [posX, setPosX] = useState(event.image_pos_x ?? 50);
  const [posY, setPosY] = useState(event.image_pos_y ?? 50);
  const frameRef = useRef(null);
  const dragRef = useRef(null);
  const saveTimer = useRef(null);
  const pendingRef = useRef(null);

  // A newly-set image resets on the server; mirror that locally too.
  useEffect(() => {
    setZoom(event.image_zoom ?? 1);
    setPosX(event.image_pos_x ?? 50);
    setPosY(event.image_pos_y ?? 50);
  }, [event.image_url]);

  useEffect(
    () => () => {
      clearTimeout(saveTimer.current);
      if (pendingRef.current) {
        adjustImage(event.id, pendingRef.current).then(onChange).catch(() => {});
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );

  const persistNow = useCallback(
    (z, x, y) => {
      clearTimeout(saveTimer.current);
      pendingRef.current = null;
      adjustImage(event.id, { zoom: z, pos_x: x, pos_y: y })
        .then(onChange)
        .catch(() => {});
    },
    [event.id, onChange]
  );

  const persistDebounced = useCallback(
    (z, x, y) => {
      pendingRef.current = { zoom: z, pos_x: x, pos_y: y };
      clearTimeout(saveTimer.current);
      saveTimer.current = setTimeout(() => persistNow(z, x, y), 250);
    },
    [persistNow]
  );

  const onPointerDown = (e) => {
    e.preventDefault();
    frameRef.current?.setPointerCapture(e.pointerId);
    dragRef.current = { startX: e.clientX, startY: e.clientY, startPosX: posX, startPosY: posY };
  };

  const onPointerMove = (e) => {
    if (!dragRef.current) return;
    const rect = frameRef.current.getBoundingClientRect();
    const { startX, startY, startPosX, startPosY } = dragRef.current;
    const dxPct = ((e.clientX - startX) / rect.width) * (100 / zoom);
    const dyPct = ((e.clientY - startY) / rect.height) * (100 / zoom);
    setPosX(clamp(startPosX - dxPct, 0, 100));
    setPosY(clamp(startPosY - dyPct, 0, 100));
  };

  const endDrag = () => {
    if (!dragRef.current) return;
    dragRef.current = null;
    persistNow(zoom, posX, posY);
  };

  const onZoomChange = (e) => {
    const z = parseFloat(e.target.value);
    setZoom(z);
    persistDebounced(z, posX, posY);
  };

  const commitZoom = () => persistNow(zoom, posX, posY);

  const reset = () => {
    setZoom(1);
    setPosX(50);
    setPosY(50);
    persistNow(1, 50, 50);
  };

  return (
    <div className="mb-4">
      <div className="flex justify-between items-baseline mb-1">
        <label className="font-stamp text-[11px] tracking-[2px] uppercase text-faded block">
          Adjust crop
        </label>
        <button type="button" onClick={reset} className="font-mono text-[11px] underline text-ink">
          reset
        </button>
      </div>
      <TicketImage
        event={event}
        live={{ zoom, pos_x: posX, pos_y: posY }}
        frameProps={{
          ref: frameRef,
          onPointerDown,
          onPointerMove,
          onPointerUp: endDrag,
          onPointerCancel: endDrag,
          className: "cursor-grab active:cursor-grabbing select-none touch-none",
        }}
      />
      <div className="flex items-center gap-2 mt-2">
        <span className="font-mono text-[10px] text-faded">zoom</span>
        <input
          type="range"
          min="1"
          max="3"
          step="0.01"
          value={zoom}
          onChange={onZoomChange}
          onMouseUp={commitZoom}
          onTouchEnd={commitZoom}
          className="flex-1"
        />
      </div>
      <p className="font-mono text-[10px] text-faded mt-1">drag the preview to pan</p>
    </div>
  );
}
