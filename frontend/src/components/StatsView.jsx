import React, { useState, useEffect } from "react";
import { motion } from "framer-motion";
import api from "../api";

const SECTION = "border-[1.5px] border-ink bg-stock p-5 relative";
const HEADING = "font-stamp text-[13px] tracking-[2px] uppercase text-stamp mb-3";

function Bar({ label, sub, count, max, delay = 0 }) {
  const pct = max > 0 ? (count / max) * 100 : 0;
  return (
    <div className="mb-2">
      <div className="flex justify-between font-mono text-[12px] mb-[3px]">
        <span className="truncate pr-2">
          {label}
          {sub ? <span className="text-faded"> · {sub}</span> : null}
        </span>
        <span className="text-faded shrink-0">{count}</span>
      </div>
      <div className="h-[10px] border border-ink bg-paper">
        <motion.div
          className="h-full bg-ink"
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.5, delay, ease: "easeOut" }}
        />
      </div>
    </div>
  );
}

function YearChart({ perYear }) {
  const max = Math.max(...perYear.map((y) => y.count), 1);
  return (
    <div className="flex items-end gap-2 h-[140px] pt-2">
      {perYear.map((y, i) => (
        <div key={y.year} className="flex-1 flex flex-col items-center justify-end h-full">
          <span className="font-mono text-[11px] mb-1">{y.count}</span>
          <motion.div
            className="w-full bg-ink border border-ink"
            style={{ maxWidth: 44 }}
            initial={{ height: 0 }}
            animate={{ height: `${(y.count / max) * 100}%` }}
            transition={{ duration: 0.5, delay: i * 0.05, ease: "easeOut" }}
          />
          <span className="font-mono text-[11px] mt-1 text-faded">{y.year}</span>
        </div>
      ))}
    </div>
  );
}

export default function StatsView() {
  const [stats, setStats] = useState(null);
  const [err, setErr] = useState(false);

  useEffect(() => {
    api.get("/api/stats")
      .then((r) => setStats(r.data))
      .catch(() => setErr(true));
  }, []);

  if (err) return <p className="text-center font-mono text-stamp mt-12">Could not load stats.</p>;
  if (!stats) return <p className="text-center font-mono text-faded mt-12">tallying the stubs…</p>;

  const { totals, per_year, by_type, top_venues, top_artists, ratings, top_attendees, top_songs } = stats;

  if (totals.events === 0) {
    return (
      <p className="text-center font-mono text-faded mt-12">
        No events yet — stats appear once the collection starts.
      </p>
    );
  }

  const maxType = Math.max(...by_type.map((t) => t.count), 1);
  const maxVenue = Math.max(...top_venues.map((v) => v.count), 1);
  const maxArtist = Math.max(...top_artists.map((a) => a.count), 1);
  const maxAtt = Math.max(...top_attendees.map((a) => a.count), 1);
  const maxSong = Math.max(...top_songs.map((s) => s.count), 1);
  const maxRating = Math.max(...Object.values(ratings), 1);

  return (
    <div className="max-w-[1100px] mx-auto px-6">
      {/* headline numbers, punched-ticket style */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-8">
        {[
          ["Events", totals.events],
          ["Venues", totals.venues],
          ["Cities", totals.cities],
          ["Avg Rating", totals.avg_rating ? `${totals.avg_rating} ★` : "—"],
        ].map(([label, value], i) => (
          <motion.div
            key={label}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.06 }}
            className="border-[1.5px] border-ink bg-stock text-center py-4"
            style={{ filter: "drop-shadow(2px 3px 0 rgba(43,33,24,.2))" }}
          >
            <div className="font-stamp font-bold text-[30px] leading-none">{value}</div>
            <div className="font-mono text-[10px] tracking-[2px] uppercase text-faded mt-2">
              {label}
            </div>
          </motion.div>
        ))}
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        {per_year.length > 0 && (
          <div className={SECTION + " md:col-span-2"}>
            <h3 className={HEADING}>Events per year</h3>
            <YearChart perYear={per_year} />
          </div>
        )}

        <div className={SECTION}>
          <h3 className={HEADING}>By type</h3>
          {by_type.map((t, i) => (
            <Bar key={t.type} label={t.type} count={t.count} max={maxType} delay={i * 0.05} />
          ))}
        </div>

        <div className={SECTION}>
          <h3 className={HEADING}>Ratings</h3>
          {[5, 4, 3, 2, 1].map((n, i) => (
            <Bar
              key={n}
              label={"★".repeat(n)}
              count={ratings[String(n)] || 0}
              max={maxRating}
              delay={i * 0.05}
            />
          ))}
        </div>

        {top_artists.length > 0 && (
          <div className={SECTION}>
            <h3 className={HEADING}>Most seen live</h3>
            {top_artists.map((a, i) => (
              <Bar key={a.name} label={a.name} count={a.count} max={maxArtist} delay={i * 0.05} />
            ))}
          </div>
        )}

        {top_venues.length > 0 && (
          <div className={SECTION}>
            <h3 className={HEADING}>Top venues</h3>
            {top_venues.map((v, i) => (
              <Bar
                key={v.venue + (v.city || "")}
                label={v.venue}
                sub={v.city}
                count={v.count}
                max={maxVenue}
                delay={i * 0.05}
              />
            ))}
          </div>
        )}

        {top_attendees.length > 0 && (
          <div className={SECTION}>
            <h3 className={HEADING}>Concert buddies</h3>
            {top_attendees.map((a, i) => (
              <Bar key={a.name} label={a.name} count={a.count} max={maxAtt} delay={i * 0.05} />
            ))}
          </div>
        )}

        {top_songs.length > 0 && (
          <div className={SECTION}>
            <h3 className={HEADING}>Songs heard most (2+)</h3>
            {top_songs.map((s, i) => (
              <Bar key={s.song} label={s.song} count={s.count} max={maxSong} delay={i * 0.04} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
