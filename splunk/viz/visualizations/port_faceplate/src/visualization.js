import { VisualizationAPI } from '@splunk/dashboard-studio-extension';
import { layoutFaceplate, poeMark, portKind } from './layout.js';
import './visualization.css';

// Port colours after the Meraki switch view (see portKind). Down is black with a grey outline so it
// still shows on the dark theme.
const PORT = {
    copper: '#7ed321', 'copper-slow': '#0b7a32', fibre: '#7b9cf0', 'fibre-slow': '#3157d5',
    admin: '#a6a6a6', down: '#000000',
};
// PoE bolt: yellow when drawing, red when denied; the dark stroke keeps it readable on green, blue and black.
const BOLT = { on: '#f5d90a', deny: '#dc4e41' };
// Bolt outline in a unit box (x, y pairs), scaled into the middle of the port square.
const BOLT_SHAPE = [0.70, 0, 0.16, 0.58, 0.45, 0.58, 0.34, 1, 0.86, 0.40, 0.56, 0.40];
// Legend entries, in the order shown under the faceplate.
const LEGEND = [
    ['copper', 'Copper'], ['copper-slow', 'Copper, reduced speed'], ['fibre', 'Fibre'], ['fibre-slow', 'Fibre, reduced speed'],
    ['admin', 'Admin down'], ['down', 'Down'],
];
// Frame of a port with errors in the time range.
const ERROR_FRAME = '#ff3b30';
const errors = (row) => (Number(row.in_errs) || 0) + (Number(row.out_errs) || 0);
const COLORS = {
    dark: { outline: '#5b6670', text: '#dfe3e8', muted: '#8a929b' },
    light: { outline: '#3c444d', text: '#1f2933', muted: '#5f6b76' },
};

const container = document.createElement('div');
container.className = 'viz-container';
(document.getElementById('root') || document.body).appendChild(container);

const state = { data: null, rows: [], loading: false, theme: 'dark' };

// Columnar search results to one object per row. Values arrive as strings.
function toRows(data) {
    const names = (data?.fields || []).map((f) => f.name ?? f);
    const columns = data?.columns || [];
    const count = columns[0]?.length || 0;
    return Array.from({ length: count }, (_, i) =>
        Object.fromEntries(names.map((name, j) => [name, columns[j][i]]))
    );
}

// Same units as the Interfaces table on the dashboard.
function formatSpeed(bps) {
    const n = Number(bps);
    if (!(n > 0)) return '';
    return n >= 1000000000 ? `${Math.round(n / 1000000000 * 10) / 10} Gb/s` : `${Math.round(n / 1000000)} Mb/s`;
}

function tooltip(row) {
    const parts = [row.interface, row.state || 'down', formatSpeed(row.speed)];
    if (row.neighbour) parts.push(`CDP: ${row.neighbour}`);
    const macs = Number(row.macs) || 0;
    if (macs > 5) parts.push(`${macs} MACs`);
    else if (macs > 0) parts.push(`MACs: ${row.mac_list}`);
    if (row.poe_state === 'deny') parts.push('PoE denied');
    else if (row.poe_state === 'ok' && row.poe_w !== '' && row.poe_w != null) {
        const w = Math.round(Number(row.poe_w) * 10) / 10;
        parts.push(`PoE ${w} W${/^\d+$/.test(row.pd_class ?? '') ? `, class ${row.pd_class}` : ''}`);
    }
    if (errors(row) > 0) parts.push(`Errors: ${Number(row.in_errs) || 0} in, ${Number(row.out_errs) || 0} out`);
    return parts.filter(Boolean).join(' · ');
}

function escapeHtml(text) {
    return String(text ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
}

// Bolt polygon inside a port square of the given size.
function boltPoints(x, y, size) {
    const w = size * 0.7, x0 = x + size * 0.15, y0 = y + size * 0.15;
    const pts = [];
    for (let i = 0; i < BOLT_SHAPE.length; i += 2) pts.push(`${(x0 + BOLT_SHAPE[i] * w).toFixed(2)},${(y0 + BOLT_SHAPE[i + 1] * w).toFixed(2)}`);
    return pts.join(' ');
}

function renderPorts(rows) {
    const colors = COLORS[state.theme] || COLORS.dark;
    const layout = layoutFaceplate(rows);
    const heads = layout.heads
        .map((h) => `<text x="${h.x}" y="${h.y}" font-size="10" fill="${colors.muted}">${escapeHtml(h.text)}</text>`)
        .join('');
    const labels = layout.labels
        .map((l) => `<text x="${l.x}" y="${l.y}" text-anchor="middle" font-size="9" fill="${colors.text}">${escapeHtml(l.text)}</text>`)
        .join('');
    const ports = layout.items
        .map((it) => {
            const row = rows[it.index];
            const mark = poeMark(row);
            const bolt = mark
                ? `<polygon points="${boltPoints(it.x, it.y, it.size)}" fill="${BOLT[mark]}" stroke="#1a1a1a" stroke-width="0.8" stroke-linejoin="round"/>`
                : '';
            return `<g class="viz-port" data-i="${it.index}"><title>${escapeHtml(tooltip(row))}</title>` +
                `<rect x="${it.x}" y="${it.y}" width="${it.size}" height="${it.size}" rx="3" fill="${PORT[portKind(row)]}" ` +
                (errors(row) > 0 ? `stroke="${ERROR_FRAME}" stroke-width="2.5"` : `stroke="${colors.outline}"`) + `/>${bolt}</g>`;
        })
        .join('');
    const note = layout.skipped
        ? `<div class="viz-note" style="color:${colors.muted}">${layout.skipped} port(s) with no slot in the faceplate are in the Interfaces table.</div>`
        : '';
    // Chassis frame around the faceplate, with more room left and right than above and below.
    const inset = 7, insetX = 20, pad = 14, padX = 27;
    const frame = `<rect x="${-insetX}" y="${-inset}" width="${layout.width + 2 * insetX}" height="${layout.height + 2 * inset}" rx="6" fill="none" stroke="${colors.outline}" stroke-width="1.5"/>`;
    const swatch = (fill) => `<span class="viz-swatch" style="background:${fill};border-color:${colors.outline}"></span>`;
    const bolt = (fill) => `<svg class="viz-legend-bolt" viewBox="0 0 10 10"><polygon points="${boltPoints(0, 0, 10)}" fill="${fill}" stroke="#1a1a1a" stroke-width="0.5"/></svg>`;
    const legend = `<div class="viz-legend" style="color:${colors.muted}">` +
        LEGEND.map(([k, label]) => `<span>${swatch(PORT[k])}${label}</span>`).join('') +
        `<span>${bolt(BOLT.on)}PoE</span><span>${bolt(BOLT.deny)}PoE denied</span>` +
        `<span><span class="viz-swatch" style="border:2px solid ${ERROR_FRAME}"></span>Errors</span></div>`;
    container.innerHTML =
        `<svg class="viz-svg" viewBox="${-padX} ${-pad} ${layout.width + 2 * padX} ${layout.height + 2 * pad}" preserveAspectRatio="xMidYMid meet" role="img">` +
        frame + heads + ports + labels + '</svg>' + legend + note;
    container.classList.remove('viz-container--empty');
}

function renderMessage(text) {
    container.innerHTML = `<div class="viz-message">${escapeHtml(text)}</div>`;
    container.classList.add('viz-container--empty');
}

function update() {
    if (state.loading) return renderMessage('Loading ports...');
    state.rows = state.data ? toRows(state.data) : [];
    if (state.rows.length === 0) return renderMessage('No ports to show for this switch');
    renderPorts(state.rows);
}

// A click opens Interface Details for the port. The payload carries the port under
// click.value and row.interface.value, the tokens the dashboard's drilldown reads.
// Studio keeps only top-level name, value, row.* and click.* keys of the payload.
container.addEventListener('click', (event) => {
    const port = event.target.closest('.viz-port');
    if (!port) return;
    const row = state.rows[Number(port.dataset.i)];
    if (!row) return;
    VisualizationAPI.triggerDrilldown({
        action: 'point.click',
        payload: {
            name: 'interface',
            value: row.interface,
            'click.name': 'interface',
            'click.value': row.interface,
            'row.interface.value': row.interface,
        },
        originalEvent: event,
    });
});

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
