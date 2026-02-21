"""Flask web UI for browsing earnings2 metrics."""
from __future__ import annotations

from flask import Flask, jsonify, request

from earnings2.db.schema import get_conn, init_db

app = Flask(__name__)

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Earnings2 — Data Browser</title>
<script src="https://cdn.jsdelivr.net/npm/ag-grid-community@31.3.2/dist/ag-grid-community.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: system-ui, -apple-system, sans-serif; background: #f5f6fa; color: #333; }
  .header { background: #1a1a2e; color: #fff; padding: 16px 24px; display: flex; align-items: center; gap: 16px; }
  .header h1 { font-size: 20px; font-weight: 600; }
  .tabs { display: flex; gap: 4px; margin-left: auto; }
  .tab-btn { background: transparent; color: #aaa; border: none; padding: 8px 20px; cursor: pointer;
             font-size: 14px; border-radius: 6px 6px 0 0; transition: all .15s; }
  .tab-btn.active { background: #f5f6fa; color: #333; }
  .tab-btn:hover:not(.active) { color: #fff; }
  .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
  .panel { display: none; }
  .panel.active { display: block; }
  .company-bar { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; align-items: center; }
  .company-bar span { font-size: 13px; font-weight: 600; color: #555; }
  .company-btn { padding: 6px 16px; border: 2px solid #ddd; border-radius: 20px; background: #fff;
                 cursor: pointer; font-size: 13px; font-weight: 500; transition: all .15s; color: #555; }
  .company-btn:hover { border-color: #999; }
  .company-btn.active { border-color: #4e79a7; background: #4e79a7; color: #fff; }
  #grid-panel .ag-theme-alpine { height: 72vh; width: 100%; border-radius: 8px; overflow: hidden;
                                  box-shadow: 0 1px 4px rgba(0,0,0,.1); }
  #chart-panel { background: #fff; border-radius: 8px; padding: 20px; box-shadow: 0 1px 4px rgba(0,0,0,.1); }
  .chart-controls { margin-bottom: 16px; }
  .chart-row { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; padding: 6px 0; }
  .chart-row + .chart-row { border-top: 1px solid #eee; }
  .chart-row label { font-size: 13px; display: flex; align-items: center; gap: 4px; cursor: pointer; }
  .chart-row strong { font-size: 13px; min-width: 70px; color: #555; }
  .chart-wrap { position: relative; height: 58vh; }
  .consolidate-btn { background: #e67e22; color: #fff; border: none; padding: 8px 18px; border-radius: 6px;
                     cursor: pointer; font-size: 13px; font-weight: 600; transition: all .15s; display: none; }
  .consolidate-btn:hover { background: #d35400; }
  .consolidate-btn.visible { display: inline-block; }
  /* Feedback modal */
  .modal-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%;
                   background: rgba(0,0,0,.5); z-index: 1000; align-items: center; justify-content: center; }
  .modal-overlay.open { display: flex; }
  .modal { background: #fff; border-radius: 12px; padding: 24px; width: 480px; max-width: 90vw;
           box-shadow: 0 8px 32px rgba(0,0,0,.25); }
  .modal h3 { margin-bottom: 12px; font-size: 16px; }
  .modal .meta { font-size: 13px; color: #666; margin-bottom: 16px; line-height: 1.5; }
  .modal .meta strong { color: #333; }
  .modal label { display: block; font-size: 13px; font-weight: 600; margin-bottom: 4px; color: #555; }
  .modal select, .modal textarea { width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 6px;
                                   font-size: 13px; font-family: inherit; }
  .modal textarea { height: 100px; resize: vertical; margin-bottom: 16px; }
  .modal select { margin-bottom: 12px; }
  .modal .btn-row { display: flex; gap: 8px; justify-content: flex-end; }
  .modal .btn-row button { padding: 8px 20px; border-radius: 6px; font-size: 13px; font-weight: 600; cursor: pointer; border: none; }
  .modal .btn-save { background: #4e79a7; color: #fff; }
  .modal .btn-save:hover { background: #3b6490; }
  .modal .btn-cancel { background: #eee; color: #555; }
  .modal .btn-cancel:hover { background: #ddd; }
  .feedback-icon { cursor: pointer; font-size: 15px; }
</style>
</head>
<body>
<div class="header">
  <h1>Earnings2 Data Browser</h1>
  <button class="consolidate-btn" id="consolidate-btn" onclick="consolidateFeedback()">Consolidate Feedback to Docs</button>
  <div class="tabs">
    <button class="tab-btn active" data-tab="grid-panel">Grid</button>
    <button class="tab-btn" data-tab="chart-panel">Chart</button>
  </div>
</div>
<!-- Feedback modal -->
<div class="modal-overlay" id="feedback-modal">
  <div class="modal">
    <h3>Verification Feedback</h3>
    <div class="meta" id="feedback-meta"></div>
    <label for="feedback-blame">Where is the problem?</label>
    <select id="feedback-blame">
      <option value="original_source">Original source (our parser extracted wrong value)</option>
      <option value="verification_source">Verification source (CNBC reported different number)</option>
    </select>
    <label for="feedback-text">Explanation</label>
    <textarea id="feedback-text" placeholder="Describe why the values don't match..."></textarea>
    <div class="btn-row">
      <button class="btn-cancel" onclick="closeFeedbackModal()">Cancel</button>
      <button class="btn-save" onclick="saveFeedback()">Save</button>
    </div>
  </div>
</div>
<div class="container">
  <div class="company-bar">
    <span>Company:</span>
    <button class="company-btn active" data-company="all">All</button>
  </div>
  <div id="grid-panel" class="panel active">
    <div id="grid" class="ag-theme-alpine"></div>
  </div>
  <div id="chart-panel" class="panel">
    <div class="chart-controls" id="chart-controls"></div>
    <div class="chart-wrap"><canvas id="chart"></canvas></div>
  </div>
</div>
<script>
const COLORS = ['#4e79a7','#f28e2b','#e15759','#76b7b2','#59a14f','#edc948','#b07aa1','#ff9da7','#9c755f','#bab0ac'];
let allData = [];
let companies = {};
let selectedCompany = 'all';
let chart = null;
let gridApi = null;
const feedbackMap = {};

async function loadData() {
  const [metricsResp, companiesResp] = await Promise.all([
    fetch('/api/metrics'),
    fetch('/api/companies'),
  ]);
  allData = await metricsResp.json();
  companies = {};
  (await companiesResp.json()).forEach(c => { companies[c.slug] = c.name; });
  buildCompanyBar();
  initGrid();
}

/* ---- Company bar ---- */
function buildCompanyBar() {
  const bar = document.querySelector('.company-bar');
  // Remove old company buttons (keep the "All" button)
  bar.querySelectorAll('.company-btn:not([data-company="all"])').forEach(b => b.remove());
  Object.entries(companies).forEach(([slug, name]) => {
    const btn = document.createElement('button');
    btn.className = 'company-btn';
    btn.dataset.company = slug;
    btn.textContent = name;
    bar.appendChild(btn);
  });
  bar.querySelectorAll('.company-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      bar.querySelectorAll('.company-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      selectedCompany = btn.dataset.company;
      applyCompanyFilter();
    });
  });
}

function getFilteredData() {
  if (selectedCompany === 'all') return allData;
  return allData.filter(r => r.company_slug === selectedCompany);
}

function applyCompanyFilter() {
  if (gridApi) {
    gridApi.setGridOption('rowData', getFilteredData());
  }
  if (chart) {
    rebuildChart();
  }
}

/* ---- Tabs ---- */
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById(btn.dataset.tab).classList.add('active');
    if (btn.dataset.tab === 'chart-panel') {
      if (!chart) initChart(); else rebuildChart();
    }
  });
});

/* ---- AG Grid ---- */
function initGrid() {
  const columnDefs = [
    { field: 'company_name', headerName: 'Company', width: 160, filter: 'agTextColumnFilter' },
    { field: 'quarter', headerName: 'Quarter', width: 120, sort: 'asc',
      comparator: (a, b) => quarterSort(a) - quarterSort(b) },
    { field: 'metric_name', headerName: 'Metric', flex: 1, filter: 'agTextColumnFilter' },
    { field: 'value_millions', headerName: 'Value ($M)', width: 140, type: 'numericColumn',
      valueFormatter: p => p.value != null ? p.value.toLocaleString('en-US', {maximumFractionDigits: 0}) : '' },
    { field: 'confidence', headerName: 'Confidence', width: 120, type: 'numericColumn',
      valueFormatter: p => p.value != null ? p.value.toFixed(2) : '' },
    { field: 'source_page', headerName: 'Source Page', width: 120, type: 'numericColumn' },
    { field: 'verification', headerName: 'Verification', width: 130, filter: 'agTextColumnFilter',
      cellStyle: p => {
        if (p.value === 'Correct') return { color: '#fff', backgroundColor: '#2e7d32', fontWeight: 600, textAlign: 'center' };
        if (p.value === 'Incorrect') return { color: '#fff', backgroundColor: '#c62828', fontWeight: 600, textAlign: 'center' };
        return { color: '#888', backgroundColor: '#f0f0f0', textAlign: 'center' };
      }},
    { field: 'verification_value', headerName: 'CNBC Value ($M)', width: 150, type: 'numericColumn',
      valueFormatter: p => p.value != null ? p.value.toLocaleString('en-US', {maximumFractionDigits: 0}) : '' },
    { field: 'verification_source_url', headerName: 'Source', width: 90,
      cellRenderer: p => {
        if (!p.value) return '';
        return `<a href="${p.value}" target="_blank" rel="noopener" style="color:#1a73e8;text-decoration:none">CNBC &#x2197;</a>`;
      }},
    { headerName: 'Feedback', width: 100,
      cellRenderer: p => {
        const d = p.data;
        if (d.verification === 'Incorrect') {
          const key = d.company_slug + '|' + d.quarter + '|' + d.metric_name;
          feedbackMap[key] = d;
          const safeKey = key.replace(/'/g, "\\'");
          if (d.verification_feedback) {
            const blame = d.verification_blame === 'original_source' ? 'Parser' : 'CNBC';
            const tip = (blame + ': ' + d.verification_feedback).replace(/'/g, '&#39;').replace(/"/g, '&quot;');
            return '<span class="feedback-icon" title="' + tip + '" onclick="openFeedbackModal(\'' + safeKey + '\')">&#x1F4DD;</span>';
          }
          return '<button style="padding:2px 10px;font-size:12px;cursor:pointer;border:1px solid #c62828;border-radius:4px;background:#fff;color:#c62828" onclick="openFeedbackModal(\'' + safeKey + '\')">Why?</button>';
        }
        return '';
      }},
  ];
  const gridOptions = {
    columnDefs,
    rowData: getFilteredData(),
    defaultColDef: { sortable: true, resizable: true },
    animateRows: true,
    pagination: false,
  };
  const el = document.getElementById('grid');
  gridApi = agGrid.createGrid(el, gridOptions);
}

function quarterSort(q) {
  const m = q.match(/Q(\d)\s+(\d{4})/);
  return m ? parseInt(m[2]) * 10 + parseInt(m[1]) : 0;
}

/* ---- Chart.js ---- */
function initChart() {
  chart = new Chart(document.getElementById('chart'), {
    type: 'line',
    data: { labels: [], datasets: [] },
    plugins: [yearBandsPlugin],
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { display: false } },
      scales: {
        y: { title: { display: true, text: 'Value ($M)' } },
        x: { title: { display: true, text: 'Quarter' } },
      },
    },
  });
  rebuildChart();
}

let checkedCompanies = new Set();
let selectedMetric = null;

function rebuildChart() {
  const data = allData;

  // Unique companies & metrics from the full dataset
  const companyList = [...new Set(data.map(r => r.company_name))].sort();
  const metricList = [...new Set(data.map(r => r.metric_name))].sort();

  // Initialize selections on first build
  if (checkedCompanies.size === 0) companyList.forEach(c => checkedCompanies.add(c));
  if (selectedMetric === null && metricList.length > 0) selectedMetric = metricList[0];

  // Build controls — two rows
  const controlsEl = document.getElementById('chart-controls');
  controlsEl.innerHTML = '';

  // Row 1: Companies (checkboxes, color-coded lines)
  const compRow = document.createElement('div');
  compRow.className = 'chart-row';
  compRow.innerHTML = '<strong>Companies:</strong>';
  companyList.forEach((name, ci) => {
    const lbl = document.createElement('label');
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = checkedCompanies.has(name);
    cb.addEventListener('change', () => {
      if (cb.checked) checkedCompanies.add(name); else checkedCompanies.delete(name);
      updateChartData();
    });
    const line = document.createElement('span');
    line.style.cssText = `display:inline-block;width:18px;height:0;border-top:3px solid ${COLORS[ci % COLORS.length]};vertical-align:middle;`;
    lbl.appendChild(cb); lbl.appendChild(line); lbl.append(' ' + name);
    compRow.appendChild(lbl);
  });
  controlsEl.appendChild(compRow);

  // Row 2: Metrics (radio buttons, mutually exclusive)
  const metricRow = document.createElement('div');
  metricRow.className = 'chart-row';
  metricRow.innerHTML = '<strong>Metrics:</strong>';
  metricList.forEach((name) => {
    const lbl = document.createElement('label');
    const rb = document.createElement('input');
    rb.type = 'radio';
    rb.name = 'chart-metric';
    rb.checked = selectedMetric === name;
    rb.addEventListener('change', () => {
      selectedMetric = name;
      updateChartData();
    });
    lbl.appendChild(rb); lbl.append(' ' + name);
    metricRow.appendChild(lbl);
  });
  controlsEl.appendChild(metricRow);

  updateChartData();
}

function updateChartData() {
  if (!selectedMetric) return;
  const data = allData.filter(r => checkedCompanies.has(r.company_name) && r.metric_name === selectedMetric);
  const qSet = [...new Set(data.map(r => r.quarter))];
  qSet.sort((a, b) => quarterSort(a) - quarterSort(b));

  const companyList = [...checkedCompanies].sort();

  // One dataset per company, color = company
  const datasets = [];
  companyList.forEach((comp, ci) => {
    const lookup = {};
    data.filter(r => r.company_name === comp)
        .forEach(r => { lookup[r.quarter] = r.value_millions; });
    const hasData = qSet.some(q => lookup[q] != null);
    if (!hasData) return;
    datasets.push({
      label: comp,
      data: qSet.map(q => lookup[q] ?? null),
      borderColor: COLORS[ci % COLORS.length],
      backgroundColor: COLORS[ci % COLORS.length] + '22',
      tension: 0.3,
      spanGaps: true,
      borderWidth: 2,
    });
  });

  chart.data.labels = qSet;
  chart.data.datasets = datasets;
  chart.update();
}

// Plugin: draw gray bands behind odd-year columns
const yearBandsPlugin = {
  id: 'yearBands',
  beforeDraw(c) {
    const { ctx, chartArea: { top, bottom }, scales: { x } } = c;
    const labels = c.data.labels;
    labels.forEach((label, i) => {
      const m = label.match(/(\d{4})/);
      if (!m || parseInt(m[1]) % 2 === 0) return;
      const left = i === 0 ? x.left : (x.getPixelForValue(i - 1) + x.getPixelForValue(i)) / 2;
      const right = i === labels.length - 1 ? x.right : (x.getPixelForValue(i) + x.getPixelForValue(i + 1)) / 2;
      ctx.save();
      ctx.fillStyle = 'rgba(0, 0, 0, 0.05)';
      ctx.fillRect(left, top, right - left, bottom - top);
      ctx.restore();
    });
  }
};

/* ---- Feedback Modal ---- */
let feedbackRow = null;

function openFeedbackModal(key) {
  feedbackRow = feedbackMap[key];
  if (!feedbackRow) return;
  const d = feedbackRow;
  const stored = d.value_millions != null ? d.value_millions.toLocaleString('en-US', {maximumFractionDigits: 0}) : '?';
  const cnbc = d.verification_value != null ? d.verification_value.toLocaleString('en-US', {maximumFractionDigits: 0}) : '?';
  document.getElementById('feedback-meta').innerHTML =
    `<strong>${d.company_name}</strong> &mdash; ${d.quarter} &mdash; ${d.metric_name}<br>` +
    `Our value: <strong>$${stored}M</strong> &nbsp;|&nbsp; CNBC value: <strong>$${cnbc}M</strong>`;
  document.getElementById('feedback-blame').value = d.verification_blame || 'original_source';
  document.getElementById('feedback-text').value = d.verification_feedback || '';
  document.getElementById('feedback-modal').classList.add('open');
}

function closeFeedbackModal() {
  document.getElementById('feedback-modal').classList.remove('open');
  feedbackRow = null;
}

async function saveFeedback() {
  if (!feedbackRow) return;
  const blame = document.getElementById('feedback-blame').value;
  const text = document.getElementById('feedback-text').value.trim();
  if (!text) { alert('Please enter an explanation.'); return; }
  const resp = await fetch('/api/feedback', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      company_slug: feedbackRow.company_slug,
      quarter: feedbackRow.quarter,
      metric_name: feedbackRow.metric_name,
      blame, feedback: text,
    }),
  });
  if (resp.ok) {
    // Update local data so grid reflects feedback without full reload
    const match = allData.find(r =>
      r.company_slug === feedbackRow.company_slug &&
      r.quarter === feedbackRow.quarter &&
      r.metric_name === feedbackRow.metric_name);
    if (match) { match.verification_feedback = text; match.verification_blame = blame; }
    if (gridApi) gridApi.setGridOption('rowData', getFilteredData());
    updateConsolidateBtn();
    closeFeedbackModal();
  } else {
    alert('Error saving feedback');
  }
}

function updateConsolidateBtn() {
  const hasFeedback = allData.some(r => r.verification_feedback);
  document.getElementById('consolidate-btn').classList.toggle('visible', hasFeedback);
}

async function consolidateFeedback() {
  if (!confirm('This will consolidate all feedback into ADDING_A_COMPANY.md and VERIFY.md, then clear the feedback. Continue?')) return;
  const btn = document.getElementById('consolidate-btn');
  btn.textContent = 'Consolidating...';
  btn.disabled = true;
  const resp = await fetch('/api/consolidate-feedback', { method: 'POST' });
  const result = await resp.json();
  btn.disabled = false;
  btn.textContent = 'Consolidate Feedback to Docs';
  if (resp.ok) {
    alert(result.message);
    // Clear feedback in local data
    allData.forEach(r => { r.verification_feedback = null; r.verification_blame = null; });
    if (gridApi) gridApi.setGridOption('rowData', getFilteredData());
    updateConsolidateBtn();
  } else {
    alert('Error: ' + (result.error || 'unknown'));
  }
}

loadData().then(() => updateConsolidateBtn());
</script>
</body>
</html>"""


@app.route("/")
def index():
    return HTML_PAGE


@app.route("/api/companies")
def api_companies():
    conn = get_conn()
    rows = conn.execute(
        "SELECT slug, name, ticker FROM companies ORDER BY name"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/metrics")
def api_metrics():
    conn = get_conn()
    rows = conn.execute(
        "SELECT m.company_slug, c.name AS company_name, m.quarter, m.metric_name, "
        "m.value_millions, m.confidence, m.source_page, m.verification, "
        "m.verification_value, m.verification_source_url, "
        "m.verification_feedback, m.verification_blame "
        "FROM metrics m JOIN companies c ON m.company_slug = c.slug "
        "ORDER BY c.name, m.quarter, m.metric_name"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/feedback", methods=["POST"])
def api_save_feedback():
    from earnings2.db.queries import update_feedback

    data = request.get_json()
    update_feedback(
        data["company_slug"],
        data["quarter"],
        data["metric_name"],
        data["blame"],
        data["feedback"],
    )
    return jsonify({"ok": True})


@app.route("/api/consolidate-feedback", methods=["POST"])
def api_consolidate_feedback():
    from pathlib import Path
    from earnings2.config import PROJECT_ROOT
    from earnings2.db.queries import get_all_feedback, clear_feedback

    feedback = get_all_feedback()
    if not feedback:
        return jsonify({"message": "No feedback to consolidate."})

    # Group by blame type
    original_issues = [f for f in feedback if f["verification_blame"] == "original_source"]
    verification_issues = [f for f in feedback if f["verification_blame"] == "verification_source"]

    files_updated = []

    if original_issues:
        section = _format_feedback_section(
            "Verification Feedback — Parser Issues",
            original_issues,
            "These mismatches were attributed to problems in our parser/extraction logic:",
        )
        md_path = PROJECT_ROOT / "ADDING_A_COMPANY.md"
        with open(md_path, "a", encoding="utf-8") as f:
            f.write(section)
        files_updated.append("ADDING_A_COMPANY.md")

    if verification_issues:
        section = _format_feedback_section(
            "Verification Feedback — CNBC Source Issues",
            verification_issues,
            "These mismatches were attributed to problems in the CNBC verification source:",
        )
        md_path = PROJECT_ROOT / "VERIFY.md"
        with open(md_path, "a", encoding="utf-8") as f:
            f.write(section)
        files_updated.append("VERIFY.md")

    count = clear_feedback()
    return jsonify({
        "message": f"Consolidated {count} feedback entries into {', '.join(files_updated)}.",
        "files_updated": files_updated,
        "count": count,
    })


def _format_feedback_section(title: str, items: list[dict], intro: str) -> str:
    from datetime import datetime

    lines = [
        f"\n\n## {title} ({datetime.now().strftime('%Y-%m-%d')})\n\n",
        f"{intro}\n\n",
    ]
    # Group by company
    by_company: dict[str, list[dict]] = {}
    for item in items:
        by_company.setdefault(item["company_slug"], []).append(item)

    for company, entries in sorted(by_company.items()):
        lines.append(f"### {company}\n\n")
        for e in entries:
            stored = f"${e['value_millions']:,.0f}M" if e["value_millions"] else "?"
            cnbc = f"${e['verification_value']:,.0f}M" if e["verification_value"] else "?"
            lines.append(
                f"- **{e['quarter']} — {e['metric_name']}**: "
                f"Stored {stored} vs CNBC {cnbc}. "
                f"_{e['verification_feedback']}_\n"
            )
        lines.append("\n")

    return "".join(lines)


def run_server(host: str = "127.0.0.1", port: int = 5000) -> None:
    init_db()
    app.run(host=host, port=port, debug=True)
