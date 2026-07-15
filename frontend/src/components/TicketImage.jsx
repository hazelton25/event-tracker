import React from "react";

// Renders the ticket's image band. Used by both the card front and the
// adjust-tool preview so they are guaranteed to look identical — `live`
// lets a caller override the persisted zoom/position with in-progress
// drag/slider state for real-time feedback.
export default function TicketImage({ event, live, frameProps = {} }) {
  if (!event?.image_url) return null;

  const zoom = live?.zoom ?? event.image_zoom ?? 1;
  const posX = live?.pos_x ?? event.image_pos_x ?? 50;
  const posY = live?.pos_y ?? event.image_pos_y ?? 50;

  return (
    <div {...frameProps} className={`ticket-thumb-frame ${frameProps.className || ""}`.trim()}>
      <img
        className="ticket-thumb"
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
