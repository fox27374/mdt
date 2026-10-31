# Custom visualizations (port_faceplate, roam_timeline)

Dashboard Studio custom visualizations for the `mdt_infra_monitoring` app (`splunk/mdt_infra_monitoring`).

- `port_faceplate`: Switch Details dashboard. One square per switch port, coloured by state; click opens Interface Details.
  - `visualizations/port_faceplate/src/layout.js`: interface name to faceplate slot, and SVG layout (pure JS).
  - `visualizations/port_faceplate/src/visualization.js`: data, theme and click handling (`@splunk/dashboard-studio-extension`).
- `roam_timeline`: Wireless Client Details dashboard. One lane per AP, bars = time on the AP coloured by band,
  ticks = roams coloured by roam time, faint bands = client not seen for over 5 minutes. Plain SVG; hover only
  moves an outline and the tooltip (no re-render), so there is no flicker. No click action.
  - `visualizations/roam_timeline/src/model.js`: stays, gaps, lanes and axis from the search rows (pure JS, no DOM).
  - `visualizations/roam_timeline/src/visualization.js`: SVG, tooltip, legend, theme (`@splunk/dashboard-studio-extension`).
  - `visualizations/roam_timeline/src/visualization.css`: styles for the chart, legend and tooltip.
- `visualizations/<name>/config.json`: Dashboard Studio metadata, copied to the app. `loader.js`: copied as the app's `visualization.js`.

## Build and deploy

```bash
npm install
npm run check   # check-layout.mjs (faceplate parser and layout) and check-roam.mjs (roam model)
npm run sync    # production build of both, then copies each bundle (faceplate.js, roam_timeline.js), its loader.js as visualization.js and config.json into the app
```

The bundles are committed under `splunk/mdt_infra_monitoring/appserver/static/visualizations/<name>/`.
`sync-app.mjs` maps each visualization to its bundle name. The app registration is
`splunk/mdt_infra_monitoring/default/visualizations.conf` and the export in `metadata/default.meta`; both are written by hand, not generated.

The roam_timeline data source is `ds_roam_timeline` in `splunk/tools/gen_wireless_client_details.py`.

Node 22+ is required. `dist/` and `node_modules/` stay out of git.
