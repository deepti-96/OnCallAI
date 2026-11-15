// Memory graph: this incident -> its service -> services it calls -> past incidents from MIND.
// Solid iris edge: the past incident is backed by current logs. Dashed: shown for reference only.
(function () {
  const NS = "http://www.w3.org/2000/svg";
  const W = 640, COL = [4, 222, 430], NODE_W = [170, 160, 206];

  function el(tag, attrs, parent) {
    const n = document.createElementNS(NS, tag);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(n);
    return n;
  }
  function clip(s, n) { s = String(s || ""); return s.length > n ? s.slice(0, n - 1) + "…" : s; }
  function curve(x1, y1, x2, y2) { const m = (x1 + x2) / 2; return `M${x1},${y1} C${m},${y1} ${m},${y2} ${x2},${y2}`; }

  // data: { incident: {title, service, dependencies[]}, past: [{key, service, cause, corroborated, note}] }
  window.renderMemoryGraph = function (host, data) {
    host.innerHTML = "";
    const svcs = [data.incident.service];
    (data.incident.dependencies || []).forEach(d => { if (!svcs.includes(d)) svcs.push(d); });
    data.past.forEach(p => { if (p.service && !svcs.includes(p.service)) svcs.push(p.service); });

    const rowH = 70, top = 58;
    const svcY = {}; svcs.forEach((s, i) => svcY[s] = top + i * rowH);
    const pastY = []; let cursor = top;
    data.past.forEach((p, i) => { const want = svcY[p.service] ?? cursor; const y = Math.max(want, cursor); pastY[i] = y; cursor = y + rowH; });
    const H = Math.max(cursor, top + svcs.length * rowH) - rowH + 34;

    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, class: "mg", role: "img",
      "aria-label": `Memory graph for ${data.incident.service}: ${data.past.length} related past incidents` }, host);
    el("text", { x: COL[0], y: 16, class: "lbl" }, svg).textContent = "This incident";
    el("text", { x: COL[1], y: 16, class: "lbl" }, svg).textContent = "Services";
    el("text", { x: COL[2], y: 16, class: "lbl" }, svg).textContent = "Past incidents in MIND";
    const edges = el("g", {}, svg);

    // incident node
    const incY = svcY[data.incident.service];
    const gi = el("g", { class: "n-inc" }, svg);
    el("rect", { x: COL[0], y: incY - 21, width: NODE_W[0], height: 42, rx: 6 }, gi);
    el("text", { x: COL[0] + 12, y: incY - 3, "font-size": 13 }, gi).textContent = clip(data.incident.title, 22);
    el("text", { x: COL[0] + 12, y: incY + 13, "font-size": 11, "font-weight": 400 }, gi).textContent = "alerting now";
    el("path", { d: curve(COL[0] + NODE_W[0], incY, COL[1], incY), class: "e e-live" }, edges);

    // services
    svcs.forEach((s, i) => {
      const y = svcY[s];
      const g = el("g", { class: "n-svc" }, svg);
      el("rect", { x: COL[1], y: y - 17, width: NODE_W[1], height: 34, rx: 17 }, g);
      el("text", { x: COL[1] + 16, y: y + 5 }, g).textContent = clip(s, 20);
      if (i > 0 && (data.incident.dependencies || []).includes(s)) {
        // spine to the left of the service column, so the line never crosses a node
        const y0 = svcY[data.incident.service], sx = COL[1] - 16;
        el("path", { d: `M${COL[1]},${y0 + 8} H${sx} V${y} H${COL[1]}`, class: "e e-dep" }, edges);
        if (!svg.querySelector(".calls")) {
          const t = el("text", { x: sx - 6, y: (y0 + svcY[(data.incident.dependencies || [])[0]]) / 2 + 4, class: "lbl calls", "text-anchor": "end" }, svg);
          t.textContent = "calls";
        }
      }
    });

    // past incidents
    data.past.forEach((p, i) => {
      const y = pastY[i];
      const g = el("g", { class: "n-past" + (p.corroborated ? "" : " off") }, svg);
      el("rect", { x: COL[2], y: y - 28, width: NODE_W[2], height: 56, rx: 4 }, g);
      el("text", { x: COL[2] + 10, y: y - 11, class: "k" }, g).textContent = clip(p.key, 28);
      el("text", { x: COL[2] + 10, y: y + 5 }, g).textContent = clip(p.cause, 30);
      el("text", { x: COL[2] + 10, y: y + 20, class: "lbl" }, g).textContent = clip(p.note, 32);
      if (svcY[p.service] != null) {
        el("path", { d: curve(COL[1] + NODE_W[1], svcY[p.service], COL[2], y), class: "e " + (p.corroborated ? "e-mem" : "e-off") }, edges);
      }
    });
    return svg;
  };
})();
