// Maps interface names to faceplate slots and lays the ports out as SVG coordinates.
// Name paths: x/0/y and x/N/y on IOS-XE (main block, module N), x/y on NX-OS (main block),
// x/y/z on NX-OS Ethernet names (breakout lane z of slot y). x is the stack member.

const PATH = /^\D+(\d+(?:\/\d+)+)/;
const NX_OS = /^(Ethernet|eth)\d/i; // lowercase eth1/x is used on some NX-OS switches

// Units are SVG user units; the SVG scales to the panel.
const PITCH = 30; // column pitch: two ports per column (odd port top, even port bottom)
const GROUP_GAP = 18; // extra gap after every 6 columns (12 ports)
const BLOCK_GAP = 54; // gap before a module block
const SQ = 24; // port square
const LANE = 11; // breakout lane square: four lanes fill one slot
const ROW = 44; // distance between the top and bottom row
const LABEL = 34; // port number, below its square
const STRIP = 84; // height of one member strip, including its row labels
const HEAD = 16; // room above a strip for its member label
const STRIP_GAP = 10;

export function parseInterface(name) {
  const m = PATH.exec(name ?? "");
  if (!m) return null;
  const parts = m[1].split("/").map(Number);
  // ponytail: paths with four or more parts are not drawn, none seen on the lab switches
  if (parts.length > 3) return null;
  const [member, a, b] = parts;
  if (parts.length === 2) return { member, module: 0, port: a, lane: null };
  if (NX_OS.test(name)) return { member, module: 0, port: a, lane: b };
  return { member, module: a, port: b, lane: null };
}

// Colour key for a port, after the Meraki switch view: copper green, fibre blue, light at full speed
// (1 Gb/s and up on copper, 10 Gb/s and up on fibre), dark at reduced speed; admin down and down
// (disconnected) are the same for both.
const FIBRE = /^(TwentyFive|Forty|Fifty|Hundred|FourHundred)/i;
export function portKind(row) {
  if (row.state === "admin down") return "admin";
  if (row.state !== "up") return "down";
  const p = parseInterface(row.interface);
  const fibre = !!p && (p.module !== 0 || NX_OS.test(row.interface) || FIBRE.test(row.interface));
  const full = Number(row.speed) >= (fibre ? 1e10 : 1e9);
  return (fibre ? "fibre" : "copper") + (full ? "" : "-slow");
}

const colX = (col) => col * PITCH + Math.floor(col / 6) * GROUP_GAP;
const slotCol = (port) => Math.floor((port - 1) / 2);
const slotY = (port) => (port % 2 === 1 ? 0 : ROW);

// rows: [{interface, ...}]. Returns {items, labels, heads, skipped, width, height}.
// items: {index, x, y, size} with index into rows; labels: {text, x, y}; heads: {text, x, y}.
export function layoutFaceplate(rows) {
  const members = new Map();
  let skipped = 0;
  rows.forEach((row, index) => {
    const p = parseInterface(row.interface);
    if (!p) {
      skipped += 1;
      return;
    }
    if (!members.has(p.member)) members.set(p.member, []);
    members.get(p.member).push({ ...p, index });
  });

  const items = [];
  const labels = [];
  const heads = [];
  let top = 0;
  let width = 0;
  [...members.keys()].sort((a, b) => a - b).forEach((member) => {
    // Port slots per module; a breakout slot holds its lanes, a plain port holds one square.
    const slots = new Map();
    members.get(member).forEach((p) => {
      const key = `${p.module}:${p.port}`;
      if (!slots.has(key)) slots.set(key, { module: p.module, port: p.port, ports: [] });
      slots.get(key).ports.push(p);
    });
    const blocks = new Map();
    slots.forEach((slot) => {
      if (!blocks.has(slot.module)) blocks.set(slot.module, []);
      blocks.get(slot.module).push(slot);
    });

    const y0 = top + HEAD;
    heads.push({ text: `Switch ${member}`, x: 0, y: top + 11 });
    let x0 = 0;
    [...blocks.keys()].sort((a, b) => a - b).forEach((module) => {
      if (module !== 0) {
        heads.push({ text: `Module ${module}`, x: x0, y: top + 11 });
      }
      let blockWidth = 0;
      blocks.get(module).forEach((slot) => {
        const x = x0 + colX(slotCol(slot.port));
        const y = y0 + slotY(slot.port);
        blockWidth = Math.max(blockWidth, colX(slotCol(slot.port)) + SQ);
        if (slot.ports.length === 1 && slot.ports[0].lane === null) {
          items.push({ index: slot.ports[0].index, x, y, size: SQ });
        } else {
          // breakout: lane z goes to the 2x2 grid in the slot, lanes beyond 4 wrap around
          slot.ports.forEach((p) => {
            const i = ((p.lane ?? 1) - 1) % 4;
            items.push({
              index: p.index,
              x: x + (i % 2) * (LANE + 2),
              y: y + Math.floor(i / 2) * (LANE + 2),
              size: LANE,
            });
          });
        }
        labels.push({ text: String(slot.port), x: x + SQ / 2, y: y + LABEL });
      });
      x0 += blockWidth + BLOCK_GAP;
      width = Math.max(width, x0 - BLOCK_GAP);
    });
    top += STRIP + HEAD + STRIP_GAP;
  });

  return { items, labels, heads, skipped, width, height: Math.max(top - STRIP_GAP, 0) };
}
