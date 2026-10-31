import { VisualizationAPI } from '@splunk/dashboard-studio-extension';
import { axisTicks, buildTimeline, GAP_SECONDS, tickClass } from './model.js';
import './visualization.css';

// Muted band colours, readable on both themes.
const BAND = { '2.4 GHz': '#4c9a92', '5 GHz': '#4a72b8', '6 GHz': '#8a6bb5' };
// Roam tick colours by roam time (category from the search: Join, Good < 100 ms, Slow 100-500 ms, Bad > 500 ms).
const TICK = { join: '#9aa3ad', good: '#2fa34f', slow: '#dfb000', bad: '#e5493f' };
const COLORS = {
    dark: { text: '#dfe3e8', muted: '#8a929b', axis: '#5b6670', bg: '#1b1f24', lane: '#2c333b', gap: '#8a929b' },
    light: { text: '#1f2933', muted: '#5f6b76', axis: '#b8c0c8', bg: '#ffffff', lane: '#e6eaee', gap: '#5f6b76' },
};
// Layout in px: AP names on the left, lanes, then the time axis.
const PL = 118, PR = 14, TOP = 4, LANE = 24, BAR_H = 12, AXIS_H = 22;
const HIT_HALF = 8; // tick hit area: 8 px either side

const container = document.createElement('div');
container.className = 'rt-container';
const body = document.createElement('div');
body.className = 'rt-body';
const tip = document.createElement('div');
tip.className = 'rt-tip';
tip.hidden = true;
container.append(body, tip);
(document.getElementById('root') || document.body).appendChild(container);

const state = { data: null, loading: false, theme: 'dark', model: null, hover: null, width: 0, showDate: false, tzOff: 0 };
const colors = () => COLORS[state.theme] || COLORS.dark;

// Columnar search results to one object per row. Values arrive as strings.
function toRows(data) {
    const names = (data?.fields || []).map((f) => f.name ?? f);
    const columns = data?.columns || [];
    const count = columns[0]?.length || 0;
    return Array.from({ length: count }, (_, i) =>
        Object.fromEntries(names.map((name, j) => [name, columns[j][i]]))
    );
}

function escapeHtml(text) {
    return String(text ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
}

const pad = (n) => String(n).padStart(2, '0');
// Times in the Splunk user's time zone (tz_offset from the search, "+0100"), like the other panels, not the browser's.
const parseOffset = (z) => (/^[+-]\d{4}$/.test(z || '') ? (z[0] === '-' ? -1 : 1) * (Number(z.slice(1, 3)) * 3600 + Number(z.slice(3)) * 60) : 0);
function fmtTime(sec) {
    const d = new Date((sec + state.tzOff) * 1000);
    const hm = `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
    return state.showDate ? `${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ${hm}` : hm;
}

function fmtDuration(sec) {
    if (sec < 60) return `${Math.round(sec)} s`;
    if (sec < 3600) return `${Math.floor(sec / 60)} min`;
    return `${Math.floor(sec / 3600)} h ${Math.floor((sec % 3600) / 60)} min`;
}

const roamLabel = (roam) => (roam === 'none' ? 'First join' : roam || '-');

// Tooltip, three lines so it fits the short panel: AP and band, time, roam details.
// A stay (s) shows its whole time on the AP; a tick (t) the association's roam.
function tipHtml(key) {
    const m = state.model;
    const kind = key[0];
    const i = Number(key.slice(1));
    if (kind === 'g') {
        const g = m.gaps[i];
        return `<b>Not seen ${fmtTime(g.start)} – ${fmtTime(g.end)}</b><br>(${Math.round((g.end - g.start) / 60)} min)`;
    }
    const s = m.stays[i];
    const roam = `${escapeHtml(roamLabel(s.roam))} · ${Number.isFinite(s.runLatency) ? Math.round(s.runLatency) + ' ms' : '-'} · BSSID ${escapeHtml(s.bssid || '-')}`;
    const head = `<b>${escapeHtml(s.ap)}</b> · ${escapeHtml(s.band || '-')}`;
    if (kind === 't') return `${head}<br>Roamed ${fmtTime(s.start)}<br>${roam}`;
    const from = `${fmtTime(s.start)}${s.inRange ? '' : ' (before range)'}`;
    const to = `${fmtTime(s.end)}${s.endReason === 'last' ? ' (last seen)' : ''}`;
    return `${head}<br>${from} – ${to} (${fmtDuration(s.end - s.start)})<br>${roam}`;
}

function setOutline(key, on) {
    if (!key) return;
    body.querySelectorAll(`[data-h="${key}"]:not(.rt-hit)`).forEach((el) => el.classList.toggle('rt-hover', on));
}

function placeTip(clientX, clientY) {
    const r = container.getBoundingClientRect();
    const tw = tip.offsetWidth, th = tip.offsetHeight, off = 14;
    // Beside the pointer (right, or left near the edge), never under it; vertically centred on it and kept
    // inside the panel, which clips anything outside.
    let x = clientX - r.left + off;
    if (x + tw > r.width) x = clientX - r.left - tw - off;
    const y = Math.min(Math.max(0, clientY - r.top - th / 2), Math.max(0, r.height - th));
    tip.style.left = `${Math.max(0, x)}px`;
    tip.style.top = `${y}px`;
}

// Hover only moves an outline and the tooltip: the SVG is not rebuilt.
function setHover(key, clientX, clientY) {
    if (key !== state.hover) {
        setOutline(state.hover, false);
        state.hover = key;
        setOutline(key, true);
        tip.hidden = !key;
        if (key) tip.innerHTML = tipHtml(key);
    }
    if (key) placeTip(clientX, clientY);
}

body.addEventListener('pointermove', (event) => {
    const el = event.target.closest?.('[data-h]');
    setHover(el ? el.dataset.h : null, event.clientX, event.clientY);
});
body.addEventListener('pointerleave', () => setHover(null));

function renderMessage(text) {
    state.hover = null;
    tip.hidden = true;
    body.innerHTML = `<div class="rt-message" style="color:${colors().muted}">${escapeHtml(text)}</div>`;
}

function renderChart(m) {
    const c = colors();
    const W = Math.max(320, body.clientWidth || 1200);
    state.width = body.clientWidth;
    state.showDate = m.to - m.from > 86400;
    const plotW = W - PL - PR;
    const span = m.to - m.from;
    const x = (t) => (PL + ((t - m.from) / span) * plotW).toFixed(2);
    const lanesH = m.lanes.length * LANE;
    const H = TOP + lanesH + AXIS_H;
    const laneY = (lane) => TOP + lane * LANE;

    const lanes = m.lanes.map((ap, i) =>
        (i % 2 ? `<rect x="${PL}" y="${laneY(i)}" width="${plotW}" height="${LANE}" fill="${c.lane}" fill-opacity="0.4"/>` : '') +
        `<text x="${PL - 8}" y="${laneY(i) + LANE / 2 + 4}" text-anchor="end" font-size="11" fill="${c.text}">${escapeHtml(ap)}</text>`
    ).join('');
    // Gaps first, so bars and ticks stay on top of them.
    const gaps = m.gaps.map((g, k) =>
        `<rect class="rt-gap" data-h="g${k}" x="${x(g.start)}" y="${TOP}" width="${(x(g.end) - x(g.start)).toFixed(2)}" height="${lanesH}" fill="${c.gap}"/>`
    ).join('');
    const bars = m.stays.map((s, i) => {
        if (!(s.barEnd > s.barStart)) return '';
        const w = Math.max(1.5, Number(x(s.barEnd)) - Number(x(s.barStart)));
        return `<rect data-h="s${i}" x="${x(s.barStart)}" y="${laneY(s.lane) + (LANE - BAR_H) / 2}" width="${w.toFixed(2)}" height="${BAR_H}" rx="2" fill="${BAND[s.band] || c.muted}"/>`;
    }).join('');
    // Ticks last, each with a wider hit rect drawn after the visible tick, so a tick wins over the bar under it.
    const ticks = m.stays.map((s, i) => {
        if (!s.inRange) return '';
        const cx = Number(x(s.start));
        const visible = `<rect class="rt-tick" data-h="t${i}" x="${(cx - 1.5).toFixed(2)}" y="${laneY(s.lane) + 2}" width="3" height="${LANE - 4}" fill="${TICK[tickClass(s.category)]}" stroke="${c.bg}" stroke-width="1"/>`;
        const hit = `<rect class="rt-hit" data-h="t${i}" x="${(cx - HIT_HALF).toFixed(2)}" y="${laneY(s.lane)}" width="${HIT_HALF * 2}" height="${LANE}"/>`;
        return visible + hit;
    }).join('');
    const axisY = TOP + lanesH;
    const axis = `<line x1="${PL}" y1="${axisY}" x2="${W - PR}" y2="${axisY}" stroke="${c.axis}"/>` +
        axisTicks(m.from, m.to, 8, state.tzOff).map((t) => {
            const tx = Number(x(t));
            const anchor = tx < PL + 24 ? 'start' : tx > W - PR - 24 ? 'end' : 'middle';
            return `<line x1="${tx}" y1="${axisY}" x2="${tx}" y2="${axisY + 4}" stroke="${c.axis}"/>` +
                `<text x="${tx}" y="${axisY + 16}" text-anchor="${anchor}" font-size="10" fill="${c.muted}">${fmtTime(t)}</text>`;
        }).join('');

    const legend = legendHtml(c);
    body.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" style="color:${c.text}">${gaps}${lanes}${bars}${ticks}${axis}</svg>${legend}`;
}

function legendHtml(c) {
    const bands = Object.keys(BAND).map((b) => `<span><i class="rt-swatch" style="background:${BAND[b]}"></i>${b}</span>`).join('');
    const ticks = [['good', 'Good (under 100 ms)'], ['slow', 'Slow (100–500 ms)'], ['bad', 'Bad (over 500 ms)'], ['join', 'First join']]
        .map(([k, label]) => `<span><i class="rt-swatch rt-tick-swatch" style="background:${TICK[k]}"></i>${label}</span>`).join('');
    const offline = `<span><i class="rt-swatch" style="background:${c.gap};opacity:0.3"></i>Offline (not seen over ${GAP_SECONDS / 60} min)</span>`;
    return `<div class="rt-legend" style="color:${c.muted}"><div style="display:flex;gap:16px;flex-wrap:wrap">${bands}</div>` +
        `<div style="display:flex;gap:16px;flex-wrap:wrap">${ticks}${offline}</div></div>`;
}

function update() {
    if (state.loading) return renderMessage('Loading roaming...');
    const rows = state.data ? toRows(state.data) : [];
    state.tzOff = parseOffset(rows[0]?.tz_offset);
    state.model = buildTimeline(rows, Date.now() / 1000);
    const m = state.model;
    if (m.empty || m.lanes.length === 0 || !(m.to > m.from)) return renderMessage('No roaming data in this range');
    state.hover = null;
    tip.hidden = true;
    renderChart(m);
}

VisualizationAPI.addDataSourcesListener(
    ({ dataSources, loading }) => {
        state.loading = loading;
        state.data = dataSources?.primary?.data || null;
        update();
    },
    { invokeImmediately: true }
);

VisualizationAPI.addThemeListener(
    ({ theme }) => {
        state.theme = theme;
        container.dataset.theme = theme;
        update();
    },
    { invokeImmediately: true }
);

// Redraw only when the width changes (the SVG scales with its width otherwise).
if (window.ResizeObserver) {
    new ResizeObserver(() => {
        if (state.model && body.clientWidth !== state.width) update();
    }).observe(container);
}
