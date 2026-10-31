// Runnable check for the roaming timeline model: node check-roam.mjs (exits non-zero on failure).
import assert from 'node:assert/strict';
import { axisTicks, buildTimeline, stayEnd, tickClass } from './visualizations/roam_timeline/src/model.js';

const T0 = 1_000_000; // range start (epoch seconds)
const TO = T0 + 4 * 3600; // range end
const range = { info_min_time: String(T0), info_max_time: String(TO) };
const assoc = (t, ap, extra = {}) => ({ kind: 'assoc', t, ap, band: '5 GHz', roam: 'OKC', run_latency: 80, category: 'Good', bssid: 'aa:bb', ...range, ...extra });
const seen = (t) => ({ kind: 'seen', t, ...range });
// Presence every minute from a to b (inclusive), as the search emits.
const minutes = (a, b) => Array.from({ length: (b - a) / 60 + 1 }, (_, i) => seen(a + i * 60));
const NOW = TO;

// Stays end at the next association.
{
  const m = buildTimeline([assoc(T0 + 600, 'AP1'), assoc(T0 + 1200, 'AP2'), ...minutes(T0 + 600, T0 + 1200)], NOW);
  assert.equal(m.stays[0].end, T0 + 1200);
  assert.equal(m.stays[0].endReason, 'next');
  assert.equal(m.stays[1].start, T0 + 1200);
}

// A presence gap over 5 minutes cuts the stay at the last seen minute; the gap is drawn after it.
{
  const rows = [assoc(T0 + 600, 'AP1'), ...minutes(T0 + 600, T0 + 900), ...minutes(T0 + 1300, T0 + 1500)];
  const m = buildTimeline(rows, NOW);
  assert.equal(m.stays[0].end, T0 + 960, 'cut at last seen minute (900 + 60)');
  assert.equal(m.stays[0].endReason, 'last');
  assert.deepEqual(m.gaps, [{ start: T0 + 960, end: T0 + 1300 }]);
}

// A gap of exactly 5 minutes does not cut (more than 5 minutes does).
{
  const m = buildTimeline([assoc(T0 + 600, 'AP1'), seen(T0 + 600), seen(T0 + 900), assoc(T0 + 1500, 'AP2')], NOW);
  assert.equal(m.stays[0].end, T0 + 1500);
  assert.deepEqual(m.gaps, []);
}

// Association before the range start: bar starts at the range start, no tick.
{
  const m = buildTimeline([assoc(T0 - 1800, 'AP1'), assoc(T0 + 900, 'AP2'), ...minutes(T0 - 1800, T0 + 900)], NOW);
  const s = m.stays[0];
  assert.equal(s.inRange, false);
  assert.equal(s.barStart, T0);
  assert.equal(s.barEnd, T0 + 900);
  assert.equal(m.stays[1].inRange, true);
  assert.equal(m.from, T0);
}

// An association that ended before the range start is dropped.
{
  // AP0 ends at AP1's association, before the range; AP1 runs until AP2 and reaches into the range.
  const m = buildTimeline([assoc(T0 - 3000, 'AP0'), assoc(T0 - 1000, 'AP1'), assoc(T0 + 60, 'AP2')], NOW);
  assert.deepEqual(m.lanes, ['AP1', 'AP2']);
  assert.equal(m.stays.length, 2);
}

// Lanes ordered by first appearance; the current stay ends at last seen (never after now).
{
  const rows = [assoc(T0 + 1200, 'AP2'), assoc(T0 + 600, 'AP1'), ...minutes(T0 + 600, T0 + 1500)];
  const m = buildTimeline(rows, T0 + 1000); // now before the last minute: capped
  assert.deepEqual(m.lanes, ['AP1', 'AP2']);
  assert.equal(stayEnd(T0 + 1200, Infinity, [T0 + 1200, T0 + 1260], T0 + 1400).end, T0 + 1320);
  assert.equal(stayEnd(T0 + 1200, Infinity, [T0 + 1200, T0 + 1260], T0 + 1290).end, T0 + 1290);
}

// Tick categories map to their colour class; anything unknown is shown as bad.
assert.equal(tickClass('Join'), 'join');
assert.equal(tickClass('Good'), 'good');
assert.equal(tickClass('Slow'), 'slow');
assert.equal(tickClass('Bad'), 'bad');
assert.equal(tickClass(undefined), 'bad');

// All-time range (info_min_time 0): starts at the first data point.
{
  const allTime = { info_min_time: '0' };
  const m = buildTimeline([assoc(T0 + 600, 'AP1', allTime), { kind: 'seen', t: T0 + 600, ...allTime, info_max_time: String(TO) }], NOW);
  assert.equal(m.from, T0 + 600);
}

// Empty input.
assert.equal(buildTimeline([], NOW).empty, true);

// Axis: round steps, at most 8 labels, inside the range.
// 1 h span: 10 min step (5 min gives 12 labels, over 8); T0 is not on a step.
assert.deepEqual(axisTicks(T0, T0 + 3600, 8), [1000200, 1000800, 1001400, 1002000, 1002600, 1003200]);
assert.ok(axisTicks(T0, T0 + 4 * 3600, 8).length <= 8);
assert.ok(axisTicks(T0, T0 + 4 * 3600, 8).every((t) => t >= T0 && t <= T0 + 4 * 3600));

console.log('check-roam: all assertions passed');
