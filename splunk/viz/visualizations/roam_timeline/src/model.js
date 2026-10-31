// Stays, gaps and axis for the roaming timeline. Pure JS, no DOM: check-roam.mjs tests it.
// Input rows (from the ds_roam_timeline search): kind=assoc rows (t, ap, band, roam, run_latency, category, bssid)
// and kind=seen rows (t: one per minute the client reported). Every row carries info_min_time / info_max_time.

// Silence longer than this (seconds) ends a stay and is drawn as offline.
export const GAP_SECONDS = 300;
// A presence row covers the minute that starts at its t.
export const SAMPLE_SECONDS = 60;

const num = (v) => (v === null || v === undefined || v === '' ? NaN : Number(v));

// When the stay ends: the next association, or earlier when presence shows a silence longer than GAP_SECONDS.
// The current stay (no next association) ends at its last seen minute, never after nowSec.
export function stayEnd(start, limit, seen, nowSec) {
  let last = null;
  for (const p of seen) {
    if (p < start - SAMPLE_SECONDS) continue;
    if (last !== null && p - last > GAP_SECONDS) return { end: Math.min(last + SAMPLE_SECONDS, limit), reason: 'last' };
    if (p >= limit) break;
    last = p;
  }
  if (Number.isFinite(limit)) return { end: limit, reason: 'next' };
  return last === null ? { end: start, reason: 'last' } : { end: Math.min(last + SAMPLE_SECONDS, nowSec), reason: 'last' };
}

// Builds lanes (one per AP, first appearance first), stays (bars and ticks) and gaps, clipped to the time range.
export function buildTimeline(rows, nowSec) {
  const assoc = [];
  const seen = [];
  let infoMin = NaN;
  let infoMax = NaN;
  for (const r of rows) {
    if (!(infoMin > 0)) infoMin = num(r.info_min_time);
    if (!Number.isFinite(infoMax)) infoMax = num(r.info_max_time);
    const t = num(r.t);
    if (!Number.isFinite(t)) continue;
    if (r.kind === 'assoc') assoc.push({ ...r, t });
    else if (r.kind === 'seen') seen.push(t);
  }
  assoc.sort((a, b) => a.t - b.t);
  seen.sort((a, b) => a - b);
  if (assoc.length === 0) return { empty: true, from: NaN, to: NaN, lanes: [], stays: [], gaps: [] };

  // All time has info_min_time 0: start at the first data point instead.
  const dataMin = Math.min(assoc[0].t, seen.length ? seen[0] : Infinity);
  const from = infoMin > 0 ? infoMin : dataMin;
  const to = Number.isFinite(infoMax) ? infoMax : nowSec;

  const stays = [];
  assoc.forEach((a, i) => {
    const limit = i + 1 < assoc.length ? assoc[i + 1].t : Infinity;
    if (a.t > to) return;
    const { end, reason } = stayEnd(a.t, limit, seen, nowSec);
    const inRange = a.t >= from;
    if (!inRange && end <= from) return; // ended before the range started
    stays.push({
      ap: a.ap, band: a.band, roam: a.roam, runLatency: num(a.run_latency), category: a.category, bssid: a.bssid,
      start: a.t, end, endReason: reason, inRange,
      barStart: Math.max(a.t, from), barEnd: Math.min(end, to),
    });
  });

  // Lanes by first appearance (stable for equal starts).
  const laneOf = new Map();
  const lanes = [];
  [...stays].sort((x, y) => x.barStart - y.barStart).forEach((s) => {
    if (!laneOf.has(s.ap)) {
      laneOf.set(s.ap, lanes.length);
      lanes.push(s.ap);
    }
  });
  stays.forEach((s) => { s.lane = laneOf.get(s.ap); });

  // AP changes: a stay that runs into the next association on another AP. Drawn as a vertical line between the
  // lanes, so the bars read as one path. None across an offline gap (the stay ended at last seen).
  const moves = [];
  for (let k = 1; k < stays.length; k++) {
    const a = stays[k - 1], b = stays[k];
    if (a.endReason === 'next' && a.lane !== b.lane && b.inRange) moves.push({ t: b.start, fromLane: a.lane, toLane: b.lane });
  }

  // Offline: silence between two presence rows longer than GAP_SECONDS.
  const gaps = [];
  for (let k = 1; k < seen.length; k++) {
    if (seen[k] - seen[k - 1] <= GAP_SECONDS) continue;
    const start = Math.max(seen[k - 1] + SAMPLE_SECONDS, from);
    const end = Math.min(seen[k], to);
    if (end > start) gaps.push({ start, end });
  }
  return { empty: false, from, to, lanes, stays, gaps, moves };
}

// Colour class of a roam tick: category from the search (Join, Good < 100 ms, Slow 100-500 ms, Bad > 500 ms).
const TICK_CLASS = { Join: 'join', Good: 'good', Slow: 'slow', Bad: 'bad' };
export function tickClass(category) {
  return TICK_CLASS[category] ?? 'bad';
}

// Time axis ticks: the smallest round step that gives at most maxTicks labels.
const STEPS = [60, 300, 600, 900, 1800, 3600, 7200, 10800, 21600, 43200, 86400];
export function axisTicks(from, to, maxTicks = 8, tzOff = 0) {
  const span = to - from;
  if (!(span > 0)) return [];
  const step = STEPS.find((s) => span / s <= maxTicks) ?? 86400 * Math.ceil(span / (86400 * maxTicks));
  const out = [];
  // Round in the display time zone (tzOff seconds east of UTC), so ticks fall on its full hours and midnights.
  for (let t = Math.ceil((from + tzOff) / step) * step - tzOff; t <= to; t += step) out.push(t);
  return out;
}
