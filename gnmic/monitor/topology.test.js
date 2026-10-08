const test = require("node:test");
const assert = require("node:assert/strict");
const { buildTopology } = require("./topology.js");

test("1. Multiple targets and collectors with correct node kinds and grouping", () => {
  const data = {
    components: [
      { name: "collector gnmic-1", ok: true, detail: "healthy" },
      { name: "collector gnmic-2", ok: true, detail: "healthy" },
      { name: "nats", ok: true, detail: "ok" },
      { name: "gnmic-output", ok: true, detail: "ok" },
      { name: "consul", ok: true, detail: "ok" }
    ],
    targets: [
      { name: "target-a", address: "10.0.0.1:57400", owner: "gnmic-1", status: "OK", reason: "", subs: [] },
      { name: "target-b", address: "10.0.0.2:57400", owner: "gnmic-1", status: "OK", reason: "", subs: [] },
      { name: "target-c", address: "10.0.0.3:57400", owner: "gnmic-2", status: "OK", reason: "", subs: [] }
    ]
  };

  const topo = buildTopology(data);

  // Check node count: 3 targets + 2 collectors + 4 infrastructure = 9
  assert.equal(topo.nodes.length, 9);

  // Check node kinds
  const kinds = topo.nodes.map(n => n.kind);
  assert(kinds.includes("target"), "should have target nodes");
  assert(kinds.includes("collector"), "should have collector nodes");
  assert(kinds.includes("nats"), "should have nats node");
  assert(kinds.includes("output"), "should have output node");
  assert(kinds.includes("consul"), "should have consul node");
  assert(kinds.includes("prometheus"), "should have prometheus node");

  // Check targets are grouped by owner
  const gnmic1Targets = topo.nodes.filter(n => n.kind === "target" && n.target.startsWith("target"));
  const targetsByOwner = {};
  for (const t of topo.nodes) {
    if (t.kind === "target") {
      const ownerEdge = topo.edges.find(e => e.from === t.id);
      const ownerId = ownerEdge ? ownerEdge.to : null;
      if (!targetsByOwner[ownerId]) targetsByOwner[ownerId] = [];
      targetsByOwner[ownerId].push(t);
    }
  }

  // Check that targets in the same group have y positions differing by ROW
  for (const owner in targetsByOwner) {
    const groupTargets = targetsByOwner[owner].sort((a, b) => a.y - b.y);
    for (let i = 1; i < groupTargets.length; i++) {
      assert.equal(groupTargets[i].y - groupTargets[i-1].y, 64, `targets in group should be ROW=64 apart`);
    }
  }

  // Check collector y is centered
  for (const collector of topo.nodes.filter(n => n.kind === "collector")) {
    const collectorTargets = topo.nodes.filter(n =>
      n.kind === "target" &&
      topo.edges.some(e => e.from === n.id && e.to === collector.id)
    );
    if (collectorTargets.length > 0) {
      const minY = Math.min(...collectorTargets.map(t => t.y));
      const maxY = Math.max(...collectorTargets.map(t => t.y));
      const expectedY = minY + (maxY - minY) / 2;
      assert.equal(collector.y, expectedY, `collector y should be centered on targets`);
    }
  }
});

test("2. Owner-less target lands in extra group with no outgoing edge", () => {
  const data = {
    components: [
      { name: "collector gnmic-1", ok: true, detail: "healthy" },
      { name: "nats", ok: true, detail: "ok" },
      { name: "gnmic-output", ok: true, detail: "ok" },
      { name: "consul", ok: true, detail: "ok" }
    ],
    targets: [
      { name: "target-owned", address: "10.0.0.1:57400", owner: "gnmic-1", status: "OK", reason: "", subs: [] },
      { name: "target-orphan", address: "10.0.0.2:57400", owner: "", status: "OK", reason: "", subs: [] }
    ]
  };

  const topo = buildTopology(data);

  const orphanNode = topo.nodes.find(n => n.id === "target:target-orphan");
  assert(orphanNode, "should have orphan target node");

  const orphanEdges = topo.edges.filter(e => e.from === "target:target-orphan");
  assert.equal(orphanEdges.length, 0, "orphan target should have no outgoing edges");
});

test("3. Status mapping: collector component ok:false → ERROR, missing → UNKNOWN", () => {
  const data = {
    components: [
      { name: "collector gnmic-1", ok: false, detail: "error state" },
      { name: "collector gnmic-2", ok: true, detail: "ok" }
      // gnmic-3 missing
    ],
    targets: [
      { name: "target-a", address: "10.0.0.1:57400", owner: "gnmic-1", status: "OK", reason: "", subs: [] },
      { name: "target-b", address: "10.0.0.2:57400", owner: "gnmic-2", status: "OK", reason: "", subs: [] },
      { name: "target-c", address: "10.0.0.3:57400", owner: "gnmic-3", status: "OK", reason: "", subs: [] }
    ]
  };

  const topo = buildTopology(data);

  const gnmic1 = topo.nodes.find(n => n.id === "collector:gnmic-1");
  assert.equal(gnmic1.status, "ERROR", "collector with ok:false should be ERROR");

  const gnmic2 = topo.nodes.find(n => n.id === "collector:gnmic-2");
  assert.equal(gnmic2.status, "OK", "collector with ok:true should be OK");

  const gnmic3 = topo.nodes.find(n => n.id === "collector:gnmic-3");
  assert.equal(gnmic3.status, "UNKNOWN", "collector without component should be UNKNOWN");
});

test("3b. NATS status: both missing → UNKNOWN, any ERROR → ERROR, otherwise OK", () => {
  // Test 1: both missing
  let data = {
    components: [
      { name: "gnmic-output", ok: true, detail: "ok" },
      { name: "consul", ok: true, detail: "ok" }
    ],
    targets: []
  };
  let topo = buildTopology(data);
  let natsNode = topo.nodes.find(n => n.id === "nats");
  assert.equal(natsNode.status, "UNKNOWN", "both nats and nats-consumer missing → UNKNOWN");

  // Test 2: nats ok but nats-consumer error
  data = {
    components: [
      { name: "nats", ok: true, detail: "ok" },
      { name: "nats-consumer", ok: false, detail: "error" },
      { name: "gnmic-output", ok: true, detail: "ok" },
      { name: "consul", ok: true, detail: "ok" }
    ],
    targets: []
  };
  topo = buildTopology(data);
  natsNode = topo.nodes.find(n => n.id === "nats");
  assert.equal(natsNode.status, "ERROR", "if any nats component has ok:false → ERROR");

  // Test 3: both ok
  data = {
    components: [
      { name: "nats", ok: true, detail: "ok" },
      { name: "nats-consumer", ok: true, detail: "ok" },
      { name: "gnmic-output", ok: true, detail: "ok" },
      { name: "consul", ok: true, detail: "ok" }
    ],
    targets: []
  };
  topo = buildTopology(data);
  natsNode = topo.nodes.find(n => n.id === "nats");
  assert.equal(natsNode.status, "OK", "both nats components ok → OK");
});

test("4. Edge styles: ERROR target → error, STALE → stale, OK → normal, consul → locker", () => {
  const data = {
    components: [
      { name: "collector gnmic-1", ok: true, detail: "healthy" },
      { name: "nats", ok: true, detail: "ok" },
      { name: "gnmic-output", ok: true, detail: "ok" },
      { name: "consul", ok: true, detail: "ok" }
    ],
    targets: [
      { name: "error-target", address: "10.0.0.1:57400", owner: "gnmic-1", status: "ERROR", reason: "lost contact", subs: [] },
      { name: "stale-target", address: "10.0.0.2:57400", owner: "gnmic-1", status: "STALE", reason: "", subs: [] },
      { name: "ok-target", address: "10.0.0.3:57400", owner: "gnmic-1", status: "OK", reason: "", subs: [] }
    ]
  };

  const topo = buildTopology(data);

  const errorEdge = topo.edges.find(e => e.from === "target:error-target");
  assert.equal(errorEdge.style, "error", "ERROR target edge should have error style");

  const staleEdge = topo.edges.find(e => e.from === "target:stale-target");
  assert.equal(staleEdge.style, "stale", "STALE target edge should have stale style");

  const okEdge = topo.edges.find(e => e.from === "target:ok-target");
  assert.equal(okEdge.style, "normal", "OK target edge should have normal style");

  const consulEdges = topo.edges.filter(e => e.from === "consul");
  for (const edge of consulEdges) {
    assert.equal(edge.style, "locker", "consul edges should always be locker");
  }
});

test("5. lastSeen is latest of sub.last_seen values, null when all null", () => {
  const data = {
    components: [
      { name: "collector gnmic-1", ok: true, detail: "healthy" },
      { name: "nats", ok: true, detail: "ok" },
      { name: "gnmic-output", ok: true, detail: "ok" },
      { name: "consul", ok: true, detail: "ok" }
    ],
    targets: [
      {
        name: "multi-sub",
        address: "10.0.0.1:57400",
        owner: "gnmic-1",
        status: "OK",
        reason: "",
        subs: [
          { name: "sub1", last_seen: "2026-10-08T10:00:00Z" },
          { name: "sub2", last_seen: "2026-10-08T10:05:00Z" },
          { name: "sub3", last_seen: "2026-10-08T10:02:00Z" }
        ]
      },
      {
        name: "no-last-seen",
        address: "10.0.0.2:57400",
        owner: "gnmic-1",
        status: "OK",
        reason: "",
        subs: [
          { name: "sub1", last_seen: null },
          { name: "sub2", last_seen: null }
        ]
      }
    ]
  };

  const topo = buildTopology(data);

  const multiSubNode = topo.nodes.find(n => n.id === "target:multi-sub");
  assert.equal(multiSubNode.lastSeen, "2026-10-08T10:05:00Z", "lastSeen should be the latest timestamp");

  const noLastSeenNode = topo.nodes.find(n => n.id === "target:no-last-seen");
  assert.equal(noLastSeenNode.lastSeen, null, "lastSeen should be null when all subs have null");
});

test("6. Empty input and missing arrays don't throw, contain infrastructure nodes", () => {
  // Empty input
  let topo = buildTopology({});
  assert(topo.nodes.some(n => n.kind === "nats"), "should have nats node");
  assert(topo.nodes.some(n => n.kind === "output"), "should have output node");
  assert(topo.nodes.some(n => n.kind === "consul"), "should have consul node");
  assert(topo.nodes.some(n => n.kind === "prometheus"), "should have prometheus node");

  // Empty arrays
  topo = buildTopology({ components: [], targets: [] });
  assert(topo.nodes.some(n => n.kind === "nats"), "should have nats node with empty arrays");
  assert(topo.nodes.length >= 4, "should have at least infrastructure nodes");

  // Null input
  topo = buildTopology(null);
  assert(topo.nodes.some(n => n.kind === "nats"), "should handle null input");
});

test("7. Input object is not modified, two calls give deep-equal results", () => {
  const data = {
    components: [
      { name: "collector gnmic-1", ok: true, detail: "healthy" }
    ],
    targets: [
      { name: "target-a", address: "10.0.0.1:57400", owner: "gnmic-1", status: "OK", reason: "", subs: [] }
    ]
  };

  const before = JSON.stringify(data);
  const topo1 = buildTopology(data);
  const after = JSON.stringify(data);

  assert.equal(before, after, "input should not be modified");

  const topo2 = buildTopology(data);

  // Deep equality check
  assert.deepEqual(topo1.width, topo2.width, "two calls should give same width");
  assert.deepEqual(topo1.height, topo2.height, "two calls should give same height");
  assert.deepEqual(topo1.nodes, topo2.nodes, "two calls should give same nodes");
  assert.deepEqual(topo1.edges, topo2.edges, "two calls should give same edges");
});

test("8. All x and y are finite, no two nodes share same (x, y)", () => {
  const data = {
    components: [
      { name: "collector gnmic-1", ok: true, detail: "healthy" },
      { name: "collector gnmic-2", ok: true, detail: "healthy" },
      { name: "nats", ok: true, detail: "ok" },
      { name: "gnmic-output", ok: true, detail: "ok" },
      { name: "consul", ok: true, detail: "ok" }
    ],
    targets: [
      { name: "target-a", address: "10.0.0.1:57400", owner: "gnmic-1", status: "OK", reason: "", subs: [] },
      { name: "target-b", address: "10.0.0.2:57400", owner: "gnmic-1", status: "OK", reason: "", subs: [] },
      { name: "target-c", address: "10.0.0.3:57400", owner: "gnmic-2", status: "OK", reason: "", subs: [] },
      { name: "target-d", address: "10.0.0.4:57400", owner: "gnmic-2", status: "OK", reason: "", subs: [] }
    ]
  };

  const topo = buildTopology(data);

  // Check all x and y are finite
  for (const node of topo.nodes) {
    assert(isFinite(node.x), `x should be finite for ${node.id}`);
    assert(isFinite(node.y), `y should be finite for ${node.id}`);
  }

  // Check no two nodes share same (x, y)
  const positions = new Set();
  for (const node of topo.nodes) {
    const key = `${node.x},${node.y}`;
    assert(!positions.has(key), `position (${node.x}, ${node.y}) shared by multiple nodes`);
    positions.add(key);
  }
});
