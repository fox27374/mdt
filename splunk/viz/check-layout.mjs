// Runnable check for the faceplate layout: node check-layout.mjs (exits non-zero on failure).
import assert from 'node:assert/strict';
import { layoutFaceplate, memberLabel, parseInterface, poeMark, portKind } from './visualizations/port_faceplate/src/layout.js';

const range = (prefix, from, to) => Array.from({ length: to - from + 1 }, (_, i) => `${prefix}${from + i}`);
const rowsOf = (names) => names.map((interface_) => ({ interface: interface_ }));

// Parser: stack member, module (0 = main block), port, breakout lane.
assert.deepEqual(parseInterface('GigabitEthernet1/0/1'), { member: 1, module: 0, port: 1, lane: null });
assert.deepEqual(parseInterface('TenGigabitEthernet1/1/4'), { member: 1, module: 1, port: 4, lane: null });
assert.deepEqual(parseInterface('TwentyFiveGigE1/1/2'), { member: 1, module: 1, port: 2, lane: null });
assert.deepEqual(parseInterface('FiftyGigE1/1/7'), { member: 1, module: 1, port: 7, lane: null });
assert.deepEqual(parseInterface('HundredGigE2/0/12'), { member: 2, module: 0, port: 12, lane: null });
assert.deepEqual(parseInterface('Ethernet1/1'), { member: 1, module: 0, port: 1, lane: null });
assert.deepEqual(parseInterface('Ethernet1/49/3'), { member: 1, module: 0, port: 49, lane: 3 });
assert.deepEqual(parseInterface('eth1/49/4'), { member: 1, module: 0, port: 49, lane: 4 });
assert.deepEqual(parseInterface('eth1/12'), { member: 1, module: 0, port: 12, lane: null });
// PAN-OS names are lowercase ethernet1/x: copper, not NX-OS.
assert.deepEqual(parseInterface('ethernet1/3'), { member: 1, module: 0, port: 3, lane: null });
assert.equal(portKind({ interface: 'ethernet1/3', state: 'up', speed: 1e9 }), 'copper');
assert.equal(portKind({ interface: 'Ethernet1/1', state: 'up', speed: 1e10 }), 'fibre');
assert.equal(parseInterface('Vlan10'), null);
assert.equal(parseInterface('Port-channel1'), null);
assert.equal(parseInterface('Ethernet1/1/1/1'), null);

// Layout: no overlapping squares for the sample switch shapes, every port placed once.
function boxes(layout, rows) {
  assert.equal(layout.skipped, 0);
  assert.equal(layout.items.length, rows.length, 'every row placed once');
  assert.equal(new Set(layout.items.map((it) => it.index)).size, rows.length);
  const b = layout.items.map((it) => ({ ...it, x2: it.x + it.size, y2: it.y + it.size }));
  for (let i = 0; i < b.length; i++) for (let j = i + 1; j < b.length; j++) {
    const overlap = b[i].x < b[j].x2 && b[j].x < b[i].x2 && b[i].y < b[j].y2 && b[j].y < b[i].y2;
    assert.ok(!overlap, `overlap between ${rows[b[i].index].interface} and ${rows[b[j].index].interface}`);
  }
  return b;
}
const at = (layout, rows, name) => layout.items.find((it) => rows[it.index].interface === name);

// IOS-XE 9300: 48 copper ports plus an uplink module; 9300X style 25G ports; sw98/99 style 24 + 4.
const shapes = {
  ios9300: [...range('GigabitEthernet1/0/', 1, 48), ...range('TenGigabitEthernet1/1/', 1, 8)],
  edge03: [...range('GigabitEthernet1/0/', 1, 24), ...range('TwentyFiveGigE1/0/', 25, 28), ...range('FiftyGigE1/1/', 1, 2), ...range('HundredGigE1/1/', 3, 4)],
  sw98: [...range('GigabitEthernet1/0/', 1, 24), ...range('TenGigabitEthernet1/1/', 1, 4)],
  nxos: [...range('Ethernet1/', 1, 54)],
  nxosLower: [...range('eth1/', 1, 54)],
};
for (const [name, names] of Object.entries(shapes)) {
  const rows = rowsOf(names);
  const layout = layoutFaceplate(rows);
  boxes(layout, rows);
  assert.ok(layout.width > 0 && layout.height > 0, `${name} has a size`);
}

// Odd ports on the top row, even ports on the bottom row, pairs share a column.
const ios = rowsOf(shapes.ios9300);
const iosLayout = layoutFaceplate(ios);
assert.equal(at(iosLayout, ios, 'GigabitEthernet1/0/1').y, at(iosLayout, ios, 'GigabitEthernet1/0/3').y);
assert.equal(at(iosLayout, ios, 'GigabitEthernet1/0/2').y > at(iosLayout, ios, 'GigabitEthernet1/0/1').y, true);
assert.equal(at(iosLayout, ios, 'GigabitEthernet1/0/1').x, at(iosLayout, ios, 'GigabitEthernet1/0/2').x);
// Gap after every 12 ports: port 13 sits one pitch plus the group gap after port 12.
const p12 = at(iosLayout, ios, 'GigabitEthernet1/0/12').x, p13 = at(iosLayout, ios, 'GigabitEthernet1/0/13').x;
assert.ok(p13 - p12 > 30, 'gap before port 13');
// Uplink module sits to the right of the main block.
assert.ok(at(iosLayout, ios, 'TenGigabitEthernet1/1/1').x > at(iosLayout, ios, 'GigabitEthernet1/0/48').x);

// NX-OS breakout: slot 49 as four lanes in a 2x2 grid in the same column and row as port 49.
const nx = rowsOf([...range('Ethernet1/', 1, 48), 'Ethernet1/49/1', 'Ethernet1/49/2', 'Ethernet1/49/3', 'Ethernet1/49/4']);
const nxLayout = layoutFaceplate(nx);
const lanes = [1, 2, 3, 4].map((z) => at(nxLayout, nx, `Ethernet1/49/${z}`));
assert.equal(new Set(lanes.map((l) => l.size)).size, 1);
assert.ok(lanes[0].size < 24, 'lanes are smaller than a port square');
assert.equal(lanes[0].x, lanes[2].x);
assert.equal(lanes[1].y, lanes[0].y);
assert.ok(lanes[2].y > lanes[0].y);
assert.ok(lanes[0].x > at(nxLayout, nx, 'Ethernet1/47').x, 'slot 49 is after port 47');
assert.equal(lanes[0].y, at(nxLayout, nx, 'Ethernet1/1').y, 'slot 49 is on the top row like port 1');
boxes(nxLayout, nx);

// Members get their own strip, lower on the page.
const stack = rowsOf([...range('GigabitEthernet1/0/', 1, 4), ...range('GigabitEthernet2/0/', 1, 4)]);
const stackLayout = layoutFaceplate(stack);
assert.ok(at(stackLayout, stack, 'GigabitEthernet2/0/1').y > at(stackLayout, stack, 'GigabitEthernet1/0/1').y);
assert.deepEqual(stackLayout.heads.map((h) => h.text), ['Switch 1', 'Switch 2']);

// Member label carries the switch model when a row of that member has one (inventory or CDP fallback).
assert.equal(memberLabel(1, 'C9300-24P'), 'C9300-24P');
assert.equal(memberLabel(1, '  C9300L-24P-4X '), 'C9300L-24P-4X');
assert.equal(memberLabel(2, 'C9300-24P', true), 'Switch 2 · C9300-24P');
assert.equal(memberLabel(1, ''), 'Switch 1');
assert.equal(memberLabel(2, undefined), 'Switch 2');
const modelRows = [...rowsOf(range('GigabitEthernet1/0/', 1, 2)), { interface: 'GigabitEthernet2/0/1', model: 'C9200L-48P-4G' }, { interface: 'GigabitEthernet2/0/2', model: '' }];
assert.deepEqual(layoutFaceplate(modelRows).heads.map((h) => h.text), ['Switch 1', 'Switch 2 · C9200L-48P-4G']);
assert.deepEqual(layoutFaceplate(rowsOf(range('GigabitEthernet1/0/', 1, 2))).heads.map((h) => h.text), ['Switch 1']);
assert.deepEqual(layoutFaceplate([{ interface: 'GigabitEthernet1/0/1', model: 'C9300-24P' }, { interface: 'TenGigabitEthernet1/1/1' }]).heads.map((h) => h.text), ['C9300-24P']);

// Unparseable names are counted, not drawn.
const odd = layoutFaceplate(rowsOf(['Vlan10', 'GigabitEthernet1/0/1']));
assert.equal(odd.skipped, 1);
assert.equal(odd.items.length, 1);

// Colour keys: copper vs fibre, full vs reduced speed, admin down, down.
const kind = (name, state, speed) => portKind({ interface: name, state, speed: String(speed) });
assert.equal(kind('GigabitEthernet1/0/1', 'up', 1e9), 'copper');
assert.equal(kind('GigabitEthernet1/0/1', 'up', 1e8), 'copper-slow');
assert.equal(kind('TenGigabitEthernet1/1/1', 'up', 1e10), 'fibre');
assert.equal(kind('GigabitEthernet1/1/1', 'up', 1e9), 'fibre-slow');
assert.equal(kind('TwentyFiveGigE1/0/3', 'up', 25e9), 'fibre');
assert.equal(kind('eth1/12', 'up', 1e10), 'fibre');
assert.equal(kind('Ethernet1/3', 'up', 1e9), 'fibre-slow');
assert.equal(kind('GigabitEthernet1/0/2', 'admin down', 0), 'admin');
assert.equal(kind('GigabitEthernet1/0/2', 'down', 0), 'down');

// Known firewall model (PA-550 / PA-560): all 24 ports drawn; ports with a row fill their slot, the rest are placeholders.
const paRows = ['ethernet1/3', 'ethernet1/4', 'ethernet1/15', 'ethernet1/16', 'ethernet1/22']
  .map((name) => ({ interface: name, model: 'PA-560', state: 'up', speed: '1000000000' }));
const pa = layoutFaceplate(paRows);
assert.equal(pa.items.length, 24);
assert.equal(new Set(pa.items.map((it) => it.port)).size, 24, 'every profile port once');
assert.equal(pa.items.filter((it) => it.index !== null).length, 5);
assert.equal(pa.items.filter((it) => it.index === null).length, 19);
assert.equal(pa.skipped, 0);
assert.deepEqual(pa.heads.map((h) => h.text), ['PA-560']);
const paBoxes = pa.items.map((it) => ({ ...it, x2: it.x + it.size, y2: it.y + it.size }));
for (let i = 0; i < paBoxes.length; i++) for (let j = i + 1; j < paBoxes.length; j++) {
  const a = paBoxes[i], b = paBoxes[j];
  assert.ok(!(a.x < b.x2 && b.x < a.x2 && a.y < b.y2 && b.y < a.y2), `overlap ports ${a.port} and ${b.port}`);
}
const paPort = (n) => pa.items.find((it) => it.port === n);
assert.ok(paPort(17).x - paPort(15).x > 18, 'extra gap between port 16 and the SFP block (group gap is 18)');
// Odd ports on the top row, even ports on the bottom row, each pair in one column.
assert.ok(paPort(3).y < paPort(4).y, 'even port on the bottom row');
assert.equal(paPort(3).x, paPort(4).x, 'ports 3 and 4 share a column');
assert.equal(layoutFaceplate([{ interface: 'ethernet1/25', model: 'PA-560' }]).skipped, 1, 'port outside the profile is counted');
// Firewall port colours: profile fibre for 17..24, copper below; an up port with no speed is full.
assert.equal(portKind({ interface: 'ethernet1/3', state: 'up', speed: '1000000000', model: 'PA-560' }), 'copper');
assert.equal(portKind({ interface: 'ethernet1/22', state: 'up', speed: '', model: 'PA-560' }), 'fibre');
assert.equal(portKind({ interface: 'ethernet1/22', state: 'up', speed: 'SPEED_UNKNOWN', model: 'PA-560' }), 'fibre');
assert.equal(portKind({ interface: 'ethernet1/3', state: 'down', speed: '', model: 'PA-560' }), 'down');
// Switch rows keep the switch layout and colours (model is not a firewall profile).
const sw = layoutFaceplate([{ interface: 'GigabitEthernet1/0/1', model: 'C9300-24P' }, { interface: 'GigabitEthernet1/0/2', model: 'C9300-24P' }]);
assert.equal(sw.items.length, 2);
assert.ok(sw.items.every((it) => it.index !== null));
assert.deepEqual(sw.heads.map((h) => h.text), ['C9300-24P']);
assert.equal(portKind({ interface: 'GigabitEthernet1/0/1', state: 'up', speed: '', model: 'C9300-24P' }), 'copper');

// PoE bolt: on while drawing power (state ok, watts above 0), deny when refused, nothing otherwise.
assert.equal(poeMark({ poe_state: 'ok', poe_w: '6.5' }), 'on');
assert.equal(poeMark({ state: 'down', poe_state: 'ok', poe_w: '5' }), 'on', 'a down port still drawing shows the bolt');
assert.equal(poeMark({ poe_state: 'ok', poe_w: '0' }), null);
assert.equal(poeMark({ poe_state: 'ok', poe_w: '' }), null);
assert.equal(poeMark({ poe_state: 'off', poe_w: '0' }), null);
assert.equal(poeMark({ poe_state: 'deny', poe_w: '0' }), 'deny');
assert.equal(poeMark({ interface: 'GigabitEthernet1/0/1' }), null, 'no PoE data');

console.log('check-layout: all assertions passed');
