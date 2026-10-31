// Copies each built visualization and its config.json into the Splunk app (run via npm run sync).
import { copyFileSync, mkdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
// Bundle name per visualization. visualization.js in the app is the loader that fetches the bundle past the browser cache.
const bundles = { port_faceplate: 'faceplate.js', roam_timeline: 'roam_timeline.js' };
for (const [viz, bundle] of Object.entries(bundles)) {
    const dest = resolve(here, '../mdt_infra_monitoring/appserver/static/visualizations', viz);
    mkdirSync(dest, { recursive: true });
    copyFileSync(join(here, 'dist', viz, 'visualization.js'), join(dest, bundle));
    copyFileSync(join(here, 'visualizations', viz, 'loader.js'), join(dest, 'visualization.js'));
    copyFileSync(join(here, 'visualizations', viz, 'config.json'), join(dest, 'config.json'));
    console.log(`synced ${viz} to ${dest} (${bundle})`);
}
