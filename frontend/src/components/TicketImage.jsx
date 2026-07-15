import React from "react";

// Renders the ticket's photo backdrop. Used by both the card front and the
// adjust-tool preview so they are guaranteed to look identical — `live`
// lets a caller override the persisted zoom/position with in-progress
// drag/slider state for real-time feedback. `frameProps.className` picks the
// frame's sizing (e.g. "ticket-photo-card" to fill the card, or
// "ticket-photo-preview" for a fixed-height block in the adjust tool).
export default function TicketImage({ event, live, frameProps = {} }) {
  if (!event?.image_url) return null;

  const zoom = live?.zoom ?? event.image_zoom ?? 1;
  const posX = live?.pos_x ?? event.image_pos_x ?? 50;
  const posY = live?.pos_y ?? event.image_pos_y ?? 50;

  return (
    <div {...frameProps} className={`ticket-photo ${frameProps.className || ""}`.trim()}>
      <img
        className="ticket-photo-img"
        src={event.image_url}
        alt=""
        draggable={false}
        style={{
          objectPosition: `${posX}% ${posY}%`,
          transform: `scale(${zoom})`,
          transformOrigin: `${posX}% ${posY}%`,
        }}
      />
    </div>
  );
}
