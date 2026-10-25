import { VisualizationAPI } from '@splunk/dashboard-studio-extension';
import { layoutFaceplate, portKind } from './layout.js';
import './visualization.css';

// Port colours after the Meraki switch view (see portKind). Down is black with a grey outline so it
// still shows on the dark theme.
const PORT = {
    copper: '#7ed321', 'copper-slow': '#0b7a32', fibre: '#7b9cf0', 'fibre-slow': '#3157d5',
    admin: '#a6a6a6', down: '#000000',
};
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
    return parts.filter(Boolean).join(' · ');
}

function escapeHtml(text) {
    return String(text ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
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
            return `<g class="viz-port" data-i="${it.index}"><title>${escapeHtml(tooltip(row))}</title>` +
                `<rect x="${it.x}" y="${it.y}" width="${it.size}" height="${it.size}" rx="3" fill="${PORT[portKind(row)]}" stroke="${colors.outline}"/></g>`;
        })
        .join('');
    const note = layout.skipped
        ? `<div class="viz-note" style="color:${colors.muted}">${layout.skipped} port(s) with no slot in the faceplate are in the Interfaces table.</div>`
        : '';
    const pad = 4;
    container.innerHTML =
        `<svg class="viz-svg" viewBox="${-pad} ${-pad} ${layout.width + 2 * pad} ${layout.height + 2 * pad}" preserveAspectRatio="xMidYMid meet" role="img">` +
        heads + ports + labels + '</svg>' + note;
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
