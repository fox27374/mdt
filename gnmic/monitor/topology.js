// Constants for layout
const TARGET_X = 80;
const COLLECTOR_X = 285;
const NATS_X = 490;
const OUTPUT_X = 695;
const PROMETHEUS_X = 900;
const CONSUL_X = 285;
const NODE_RADIUS = 20;
const ROW = 76; // node diameter 40 + label (~14px below centre) + gap
const GROUP_GAP = 32;
const TOP = 64; // clears the tier headings drawn in the lane pills
const WIDTH = 980;
const COLUMNS = [
  { x: TARGET_X, label: "Targets" },
  { x: COLLECTOR_X, label: "Collectors" },
  { x: NATS_X, label: "NATS" },
  { x: OUTPUT_X, label: "Output" },
  { x: PROMETHEUS_X, label: "Prometheus" }
];

function buildTopology(data) {
  // Defensive: handle missing arrays
  const components = (data && data.components) || [];
  const targets = (data && data.targets) || [];

  // Helper: find a component by name
  function getComponent(name) {
    return components.find(c => c.name === name);
  }

  // Helper: determine status from component
  function getComponentStatus(comp) {
    if (!comp) return "UNKNOWN";
    return comp.ok ? "OK" : "ERROR";
  }

  // Helper: get detail from component or default
  function getComponentDetail(comp) {
    return comp ? comp.detail : "no data";
  }

  // Helper: find latest last_seen among target's subs
  function getLatestLastSeen(targetSubs) {
    if (!targetSubs || targetSubs.length === 0) return null;
    const validSubs = targetSubs.filter(s => s.last_seen);
    if (validSubs.length === 0) return null;
    // Parse and compare ISO strings
    let latest = null;
    for (const sub of validSubs) {
      if (!latest || sub.last_seen > latest) {
        latest = sub.last_seen;
      }
    }
    return latest;
  }

  const nodes = [];
  const nodeMap = {}; // Track nodes by id for edge generation

  // 1. Create collector nodes and determine which collectors exist
  const collectorsByName = {};

  // Collect all unique collectors from:
  // a) target owners
  for (const target of targets) {
    if (target.owner) {
      collectorsByName[target.owner] = true;
    }
  }

  // b) components named "collector <name>"
  for (const comp of components) {
    if (comp.name && comp.name.startsWith("collector ")) {
      const collectorName = comp.name.substring("collector ".length);
      collectorsByName[collectorName] = true;
    }
  }

  const collectorNames = Object.keys(collectorsByName).sort();

  // Map to store collector nodes by name (for positioning later)
  const collectorNodes = {};
  for (const name of collectorNames) {
    const comp = getComponent("collector " + name);
    const status = getComponentStatus(comp);
    const detail = getComponentDetail(comp);

    const node = {
      id: "collector:" + name,
      kind: "collector",
      label: name,
      x: COLLECTOR_X,
      y: 0, // Will be set in layout phase
      status: status,
      reason: "",
      detail: detail,
      target: "",
      lastSeen: null,
      notMonitored: false
    };

    nodes.push(node);
    nodeMap[node.id] = node;
    collectorNodes[name] = node;
  }

  // 2. Create target nodes and group them by owner
  const targetsByOwner = {};
  for (const target of targets) {
    const owner = target.owner || "__unowned__";
    if (!targetsByOwner[owner]) {
      targetsByOwner[owner] = [];
    }
    targetsByOwner[owner].push(target);
  }

  // Sort targets within each group by name
  for (const owner in targetsByOwner) {
    targetsByOwner[owner].sort((a, b) => a.name.localeCompare(b.name));
  }

  // Create target nodes in order
  const targetGroups = []; // { owner, targets: [target nodes] }

  // First, owned targets in collector order
  for (const collectorName of collectorNames) {
    if (targetsByOwner[collectorName]) {
      const groupTargets = [];
      for (const target of targetsByOwner[collectorName]) {
        const node = {
          id: "target:" + target.name,
          kind: "target",
          label: target.name,
          x: TARGET_X,
          y: 0, // Will be set in layout phase
          status: target.status,
          reason: target.reason || "",
          detail: target.address,
          target: target.name,
          lastSeen: getLatestLastSeen(target.subs),
          notMonitored: false
        };
        nodes.push(node);
        nodeMap[node.id] = node;
        groupTargets.push(node);
      }
      targetGroups.push({
        owner: collectorName,
        targets: groupTargets
      });
    }
  }

  // Then, unowned targets (if any)
  if (targetsByOwner["__unowned__"]) {
    const groupTargets = [];
    for (const target of targetsByOwner["__unowned__"]) {
      const node = {
        id: "target:" + target.name,
        kind: "target",
        label: target.name,
        x: TARGET_X,
        y: 0,
        status: target.status,
        reason: target.reason || "",
        detail: target.address,
        target: target.name,
        lastSeen: getLatestLastSeen(target.subs),
        notMonitored: false
      };
      nodes.push(node);
      nodeMap[node.id] = node;
      groupTargets.push(node);
    }
    targetGroups.push({
      owner: "__unowned__",
      targets: groupTargets
    });
  }

  // 3. Compute layout: positions for all nodes
  let cursor = TOP;
  const collectorYs = {}; // collector name -> y position

  for (const group of targetGroups) {
    const n = group.targets.length;

    // Position target nodes in this group
    for (let i = 0; i < n; i++) {
      group.targets[i].y = cursor + i * ROW;
    }

    // Position collector node (centered on group, if owner is a known collector)
    if (group.owner !== "__unowned__" && collectorNodes[group.owner]) {
      const collectorY = cursor + (n - 1) * ROW / 2;
      collectorNodes[group.owner].y = collectorY;
      collectorYs[group.owner] = collectorY;
    }

    // Move cursor for next group
    cursor += Math.max(1, n) * ROW + GROUP_GAP;
  }

  // For collectors with no targets (appearing only in components), position at TOP
  for (const collectorName of collectorNames) {
    if (collectorYs[collectorName] === undefined) {
      collectorNodes[collectorName].y = TOP;
      collectorYs[collectorName] = TOP;
    }
  }

  // 4. Create infrastructure nodes (nats, output, consul, prometheus)

  // Determine nats status
  const natsComp = getComponent("nats");
  const natsConsumerComp = getComponent("nats-consumer");
  let natsStatus = "UNKNOWN";
  let natsDetail = "";

  if (natsComp || natsConsumerComp) {
    const parts = [];
    let hasError = false;

    if (natsComp) {
      natsStatus = natsComp.ok ? "OK" : "ERROR";
      parts.push(natsComp.name + ": " + natsComp.detail);
      if (!natsComp.ok) hasError = true;
    }
    if (natsConsumerComp) {
      const compStatus = natsConsumerComp.ok ? "OK" : "ERROR";
      if (natsStatus === "UNKNOWN") natsStatus = compStatus;
      else if (compStatus === "ERROR") natsStatus = "ERROR";
      parts.push(natsConsumerComp.name + ": " + natsConsumerComp.detail);
      if (!natsConsumerComp.ok) hasError = true;
    }

    if (hasError) natsStatus = "ERROR";
    natsDetail = parts.join(" | ");
  }

  const natsNode = {
    id: "nats",
    kind: "nats",
    label: "NATS",
    x: NATS_X,
    y: 0, // Will be set below
    status: natsStatus,
    reason: "",
    detail: natsDetail,
    target: "",
    lastSeen: null,
    notMonitored: false
  };
  nodes.push(natsNode);
  nodeMap["nats"] = natsNode;

  // Output node
  const outputComp = getComponent("gnmic-output");
  const outputStatus = getComponentStatus(outputComp);
  const outputDetail = getComponentDetail(outputComp);

  const outputNode = {
    id: "output",
    kind: "output",
    label: "gnmic-output",
    x: OUTPUT_X,
    y: 0,
    status: outputStatus,
    reason: "",
    detail: outputDetail,
    target: "",
    lastSeen: null,
    notMonitored: false
  };
  nodes.push(outputNode);
  nodeMap["output"] = outputNode;

  // Consul node
  const consulComp = getComponent("consul");
  const consulStatus = getComponentStatus(consulComp);
  const consulDetail = getComponentDetail(consulComp);

  const consulNode = {
    id: "consul",
    kind: "consul",
    label: "Consul",
    x: CONSUL_X,
    y: 0,
    status: consulStatus,
    reason: "",
    detail: consulDetail,
    target: "",
    lastSeen: null,
    notMonitored: false
  };
  nodes.push(consulNode);
  nodeMap["consul"] = consulNode;

  // Prometheus node (always)
  const prometheusNode = {
    id: "prometheus",
    kind: "prometheus",
    label: "Prometheus",
    x: PROMETHEUS_X,
    y: 0,
    status: "UNKNOWN",
    reason: "",
    detail: "not monitored",
    target: "",
    lastSeen: null,
    notMonitored: true
  };
  nodes.push(prometheusNode);
  nodeMap["prometheus"] = prometheusNode;

  // 5. Calculate y positions for infrastructure nodes
  // nats, output, prometheus get y = average of first and last collector y (or TOP if no collectors)
  let infraY = TOP;
  if (collectorNames.length > 0) {
    const firstCollectorY = collectorNodes[collectorNames[0]].y;
    const lastCollectorY = collectorNodes[collectorNames[collectorNames.length - 1]].y;
    infraY = (firstCollectorY + lastCollectorY) / 2;
  }

  natsNode.y = infraY;
  outputNode.y = infraY;
  prometheusNode.y = infraY;

  // Consul gets the largest y of any other node + ROW
  let maxY = TOP;
  for (const node of nodes) {
    if (node.kind !== "consul") {
      if (node.y > maxY) {
        maxY = node.y;
      }
    }
  }
  consulNode.y = maxY + ROW;

  // 6. Create edges
  const edges = [];

  // Target to its owner collector
  for (const target of targets) {
    if (target.owner && collectorNodes[target.owner]) {
      const status = target.status;
      let style = "normal";
      if (status === "ERROR") style = "error";
      else if (status === "STALE") style = "stale";

      edges.push({
        from: "target:" + target.name,
        to: "collector:" + target.owner,
        style: style
      });
    }
  }

  // Every collector to nats
  for (const collectorName of collectorNames) {
    edges.push({
      from: "collector:" + collectorName,
      to: "nats",
      style: "normal"
    });
  }

  // NATS to output
  edges.push({
    from: "nats",
    to: "output",
    style: "normal"
  });

  // Output to prometheus
  edges.push({
    from: "output",
    to: "prometheus",
    style: "normal"
  });

  // Consul to every collector
  for (const collectorName of collectorNames) {
    edges.push({
      from: "consul",
      to: "collector:" + collectorName,
      style: "locker"
    });
  }

  // 7. Calculate height
  let maxNodeY = TOP;
  for (const node of nodes) {
    if (node.y > maxNodeY) {
      maxNodeY = node.y;
    }
  }
  const height = maxNodeY + TOP;

  return {
    width: WIDTH,
    height: height,
    radius: NODE_RADIUS,
    columns: COLUMNS,
    nodes: nodes,
    edges: edges
  };
}

if (typeof module !== "undefined") {
  module.exports = { buildTopology };
}
