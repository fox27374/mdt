# port_faceplate

Dashboard Studio custom visualization for the Switch Details dashboard in the `mdt_infra_monitoring`
app (`splunk/mdt_infra_monitoring`). It draws one square per switch port, coloured by state, and opens
Interface Details when a port is clicked.

- `visualizations/port_faceplate/src/layout.js`: interface name to faceplate slot, and SVG layout (pure JS).
- `visualizations/port_faceplate/src/visualization.js`: data, theme and click handling (`@splunk/dashboard-studio-extension`).
- `visualizations/port_faceplate/config.json`: Dashboard Studio metadata, copied to the app.

## Build and deploy

```bash
npm install
npm run check   # layout parser checks
npm run sync    # production build, copies dist/port_faceplate/visualization.js and config.json into the app
```

The built bundle is committed under `splunk/mdt_infra_monitoring/appserver/static/visualizations/port_faceplate/`.
The app registration is `splunk/mdt_infra_monitoring/default/visualizations.conf` and the export in
`metadata/default.meta`; both are written by hand, not generated.

Node 22+ is required. `dist/` and `node_modules/` stay out of git.
