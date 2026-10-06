const $ = (id) => document.getElementById(id);
let meta = null;
let lastTradeoff = null;
let selected = null;

const SELECTS = {
  core_type: () => meta.core_types,
  core_material: () => Object.keys(meta.core_materials),
  conductor_material: () => Object.keys(meta.conductor_materials),
  series_parallel: () => meta.series_parallel,
};

function fieldValue(section, key) {
  return meta.default_spec[section]?.[key];
}

function renderForm() {
  const form = $("spec-form");
  const adv = $("advanced-fields");
  form.innerHTML = "";
  adv.innerHTML = "";
  for (const group of meta.fields) {
    const host = group.advanced ? adv : form;
    const title = document.createElement("div");
    title.className = "group-title";
    title.textContent = group.group;
    host.appendChild(title);
    for (const [key, label, unit] of group.fields) {
      const lab = document.createElement("label");
      lab.className = "field";
      lab.innerHTML = `<span>${label}${unit ? ` (${unit})` : ""}</span>`;
      lab.dataset.section = group.section;
      lab.dataset.key = key;
      const options = SELECTS[key]?.();
      let control;
      if (options) {
        control = document.createElement("select");
        for (const opt of options) {
          const o = document.createElement("option");
          o.value = opt;
          o.textContent = opt;
          control.appendChild(o);
        }
      } else {
        control = document.createElement("input");
        control.type = "number";
        control.step = "any";
      }
      control.name = `${group.section}.${key}`;
      const val = fieldValue(group.section, key);
      if (val !== undefined && val !== null) control.value = val;
      lab.appendChild(control);
      host.appendChild(lab);
    }
  }
}

function collectSpec() {
  const spec = JSON.parse(JSON.stringify(meta.default_spec));
  document.querySelectorAll("label.field").forEach((lab) => {
    const section = lab.dataset.section;
    const key = lab.dataset.key;
    const el = lab.querySelector("input,select");
    if (!el) return;
    let value = el.value;
    if (el.tagName === "INPUT") {
      value = value === "" ? null : Number(value);
    }
    spec[section][key] = value;
  });
  return spec;
}

function fmt(n, d = 2, unit = "") {
  if (n === undefined || n === null || Number.isNaN(n)) return "—";
  return `${Number(n).toLocaleString(undefined, { maximumFractionDigits: d })}${unit ? " " + unit : ""}`;
}

function fillKpis(row) {
  if (!row) return;
  $("k-turns").textContent = row.turns ?? "—";
  $("k-loss").textContent = fmt(row.p_total_w, 1, "W");
  $("k-mass").textContent = fmt(row.total_mass_without_clamps_kg, 1, "kg");
  $("k-vol").textContent = fmt(row.envelope_litre, 2, "L");
  $("k-b").textContent = fmt(row.bmax_t, 2, "T");
  $("k-win").textContent = `${fmt(row.wh_utilization_pct, 0)} / ${fmt(row.ww_utilization_pct, 0)} %`;
}

function drawScatter(canvas, points, xKey, yKey, xLabel, yLabel) {
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#fbf7f1";
  ctx.fillRect(0, 0, w, h);
  if (!points.length) return;
  const pad = { l: 52, r: 16, t: 16, b: 40 };
  const xs = points.map((p) => p[xKey]);
  const ys = points.map((p) => p[yKey]);
  const xmin = Math.min(...xs);
  const xmax = Math.max(...xs);
  const ymin = Math.min(...ys);
  const ymax = Math.max(...ys);
  const xspan = xmax - xmin || 1;
  const yspan = ymax - ymin || 1;
  const X = (v) => pad.l + ((v - xmin) / xspan) * (w - pad.l - pad.r);
  const Y = (v) => h - pad.b - ((v - ymin) / yspan) * (h - pad.t - pad.b);

  ctx.strokeStyle = "#e4d5c5";
  ctx.beginPath();
  ctx.moveTo(pad.l, pad.t);
  ctx.lineTo(pad.l, h - pad.b);
  ctx.lineTo(w - pad.r, h - pad.b);
  ctx.stroke();
  ctx.fillStyle = "#7a6558";
  ctx.font = "12px Segoe UI, sans-serif";
  ctx.fillText(xLabel, w / 2 - 30, h - 12);
  ctx.save();
  ctx.translate(14, h / 2 + 30);
  ctx.rotate(-Math.PI / 2);
  ctx.fillText(yLabel, 0, 0);
  ctx.restore();
  ctx.fillText(fmt(xmin, 1), pad.l, h - 22);
  ctx.fillText(fmt(xmax, 1), w - pad.r - 40, h - 22);

  for (const p of points) {
    ctx.beginPath();
    const r = p.kind === "pareto" ? 5.5 : p.kind === "baseline" ? 6.5 : 3.2;
    ctx.fillStyle = p.kind === "pareto" ? "#e88a3c" : p.kind === "baseline" ? "#b42318" : "#c4b5a5";
    ctx.arc(X(p[xKey]), Y(p[yKey]), r, 0, Math.PI * 2);
    ctx.fill();
    if (p.kind === "baseline") {
      ctx.strokeStyle = "#2a1a14";
      ctx.lineWidth = 1.2;
      ctx.stroke();
    }
  }
}

function renderCharts(result) {
  const baseline = result.baseline;
  const paretoIds = new Set(result.pareto.map((p) => p.id));
  const pts = result.candidates.map((c) => ({
    ...c,
    kind: paretoIds.has(c.id) ? "pareto" : "cand",
  }));
  pts.push({ ...baseline, kind: "baseline" });
  drawScatter($("chart-mass"), pts, "total_mass_without_clamps_kg", "p_total_w", "Mass (kg)", "Loss (W)");
  drawScatter($("chart-vol"), pts, "envelope_litre", "p_total_w", "Envelope (L)", "Loss (W)");
}

function renderTable(result) {
  const body = $("pareto-body");
  const rows = result.pareto;
  $("search-meta").textContent =
    `${result.evaluated} evaluated · ${result.feasible} feasible · ${rows.length} on Pareto front`;
  if (!rows.length) {
    body.innerHTML = `<tr><td colspan="12" class="empty">No feasible designs. Loosen Bmax, window fill, or current-density limits.</td></tr>`;
    return;
  }
  body.innerHTML = rows.map((r, i) => `
    <tr class="clickable" data-idx="${i}">
      <td>${i === 0 ? '<span class="pill">best loss</span>' : ""}</td>
      <td>${r.core_material}</td>
      <td>${r.conductor_material}</td>
      <td>${r.layers}</td>
      <td>${fmt(r.core_stack_mm, 0)} mm</td>
      <td>${r.turns}</td>
      <td>${fmt(r.p_total_w, 1)} W</td>
      <td>${fmt(r.total_mass_without_clamps_kg, 1)} kg</td>
      <td>${fmt(r.envelope_litre, 2)} L</td>
      <td>${fmt(r.bmax_t, 2)} T</td>
      <td>${fmt(r.current_density_a_per_mm2, 2)}</td>
      <td>${fmt(r.wh_utilization_pct, 0)}</td>
    </tr>`).join("");
  body.querySelectorAll("tr.clickable").forEach((tr) => {
    tr.addEventListener("click", () => selectRow(Number(tr.dataset.idx)));
  });
}

function selectRow(idx) {
  selected = lastTradeoff.pareto[idx];
  document.querySelectorAll("#pareto-body tr").forEach((tr, i) => {
    tr.classList.toggle("selected", i === idx);
  });
  $("detail-card").hidden = false;
  const show = {
    core: selected.core_material,
    conductor: selected.conductor_material,
    construction: selected.core_type,
    layers: selected.layers,
    parallels: `${selected.parallel_t} × ${selected.parallel_w}`,
    stack_mm: selected.core_stack_mm,
    turns: selected.turns,
    loss_W: selected.p_total_w,
    copper_W: selected.dc_coil_loss_150c_w_three_phase_total,
    core_W: selected.core_loss_total_w,
    mass_kg: selected.total_mass_without_clamps_kg,
    envelope_L: selected.envelope_litre,
    Bpk_T: selected.bmax_t,
    J_A_mm2: selected.current_density_a_per_mm2,
    window_H_pct: selected.wh_utilization_pct,
    window_W_pct: selected.ww_utilization_pct,
    feasible: selected.feasible,
    reasons: selected.reasons,
  };
  $("detail").textContent = JSON.stringify(show, null, 2);
  fillKpis(selected);
}

async function post(url, payload) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

function setBusy(busy, msg) {
  $("btn-design").disabled = busy;
  $("btn-tradeoff").disabled = busy;
  $("status").textContent = msg;
}

$("btn-design").addEventListener("click", async () => {
  try {
    setBusy(true, "Evaluating baseline…");
    const data = await post("/api/design", collectSpec());
    fillKpis(data.baseline);
    $("status").textContent = data.baseline.feasible
      ? "Baseline is feasible."
      : "Baseline infeasible: " + (data.baseline.reasons || []).join("; ");
  } catch (err) {
    $("status").textContent = String(err);
  } finally {
    setBusy(false, $("status").textContent);
  }
});

$("btn-tradeoff").addEventListener("click", async () => {
  try {
    setBusy(true, "Sweeping candidates…");
    const t0 = performance.now();
    const data = await post("/api/tradeoff", collectSpec());
    lastTradeoff = data;
    fillKpis(data.best || data.baseline);
    renderCharts(data);
    renderTable(data);
    const dt = ((performance.now() - t0) / 1000).toFixed(2);
    $("status").textContent = `Done in ${dt} s — ${data.evaluated} candidates, ${data.feasible} feasible.`;
    if (data.pareto.length) selectRow(0);
  } catch (err) {
    $("status").textContent = String(err);
  } finally {
    setBusy(false, $("status").textContent);
  }
});

(async function init() {
  meta = await (await fetch("/api/meta")).json();
  renderForm();
  $("status").textContent = "Loaded default 180 µH / 180 A / 50 Hz spec.";
})();
