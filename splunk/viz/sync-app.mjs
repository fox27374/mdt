// Copies the built visualization and its config.json into the Splunk app (run via npm run sync).
import { copyFileSync, mkdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const viz = 'port_faceplate';
const dest = resolve(here, '../mdt_infra_monitoring/appserver/static/visualizations', viz);
mkdirSync(dest, { recursive: true });
copyFileSync(join(here, 'dist', viz, 'visualization.js'), join(dest, 'visualization.js'));
copyFileSync(join(here, 'visualizations', viz, 'config.json'), join(dest, 'config.json'));
console.log(`synced ${viz} to ${dest}`);
