<script>
  import { onMount, onDestroy } from 'svelte';
  import {
    apiLiveSensor, apiScenarios, apiActivateScenario, apiAutoInfer, apiExplain,
  } from '../lib/api.js';
  import { riskHistory, isAutoInferring, lastAutoResult, liveSensor } from '../lib/stores.js';
  import SensorCard  from '../components/SensorCard.svelte';
  import RiskGauge   from '../components/RiskGauge.svelte';
  import LineChart   from '../components/LineChart.svelte';

  const SENSOR_META = {
    te301020:    { label: 'DEA Temperature D304', unit: '°C'   },
    pdt31008:    { label: 'Pressure Diff D304',   unit: 'mbar' },
    pdt31001:    { label: 'Pressure Diff D301',   unit: 'mbar' },
    pdt31007:    { label: 'Flow Pressure',        unit: 'mbar' },
    fq31050:     { label: 'Steam Flow D304',      unit: 'm³/h' },
    lt301031:    { label: 'Level D304',           unit: '%'    },
    lic31012_pv: { label: 'Level Ctrl D304 PV',  unit: '%'    },
    lic31002_pv: { label: 'Level Ctrl D301 PV',  unit: '%'    },
    fic31011_pv: { label: 'Reflux Flow PV',      unit: 'm³/h' },
  };

  // ── State ──────────────────────────────────────────────────────────────────
  let sensorError   = '';
  let scenarios     = null;
  let autoError     = '';
  let autoRunning   = false;
  let prevReading   = null;
  let topDrivers    = [];  // top-3 SHAP drivers from last auto-inference

  let sensorTimer = null;
  let autoTimer   = null;

  // ── Sensor polling ─────────────────────────────────────────────────────────
  async function fetchLive() {
    try {
      const data = await apiLiveSensor();
      prevReading = $liveSensor?.reading ?? null;
      liveSensor.set(data);
      sensorError = '';
    } catch (e) {
      sensorError = 'Sensor API offline — start mock_sensor_api.py on port 8002';
    }
  }

  async function fetchScenarios() {
    try { scenarios = await apiScenarios(); } catch { /* offline */ }
  }

  // ── Auto-inference ─────────────────────────────────────────────────────────
  async function runAuto() {
    if (autoRunning) return;
    autoRunning = true;
    autoError = '';
    try {
      const result = await apiAutoInfer();
      lastAutoResult.set(result);
      riskHistory.update(h => {
        const next = [...h, { x: new Date().toISOString(), y: result.anomaly_probability }];
        return next.slice(-80);
      });

      // Fetch local SHAP drivers using the sensor snapshot returned by auto-infer
      if (result.sensor_snapshot) {
        apiExplain(result.sensor_snapshot).then(expl => {
          if (expl?.local_importance?.length) {
            topDrivers = expl.local_importance.slice(0, 3);
          }
        }).catch(() => {});
      }
    } catch (e) {
      autoError = e.message;
    } finally {
      autoRunning = false;
    }
  }

  function toggleAuto() {
    if ($isAutoInferring) {
      clearInterval(autoTimer);
      autoTimer = null;
      isAutoInferring.set(false);
    } else {
      isAutoInferring.set(true);
      runAuto();
      autoTimer = setInterval(runAuto, 5000);
    }
  }

  async function switchScenario(name) {
    try {
      await apiActivateScenario(name);
      await fetchScenarios();
    } catch { /* silent */ }
  }

  // ── Lifecycle ──────────────────────────────────────────────────────────────
  onMount(() => {
    fetchLive();
    fetchScenarios();
    sensorTimer = setInterval(fetchLive, 2000);
  });

  onDestroy(() => {
    clearInterval(sensorTimer);
    clearInterval(autoTimer);
    if ($isAutoInferring) isAutoInferring.set(false);
  });

  $: chartData  = $riskHistory;
  $: alarmColor = $lastAutoResult
    ? ($lastAutoResult.anomaly_probability >= 0.7 ? 'red' : $lastAutoResult.anomaly_probability >= 0.4 ? 'amber' : 'green')
    : 'green';
</script>

<div class="page">

  <!-- ── Header ────────────────────────────────────────────────────────────── -->
  <div class="page-header">
    <div>
      <h2>Live Sensor Dashboard</h2>
      <p class="sub">DEA gas treatment plant — D301 / D304</p>
    </div>
    <div class="status-row">
      {#if sensorError}
        <span class="badge red">{sensorError}</span>
      {:else if $liveSensor}
        <span class="badge {$liveSensor.scenario_color}">{$liveSensor.scenario_description}</span>
      {:else}
        <span class="badge grey">Connecting to sensor API…</span>
      {/if}
    </div>
  </div>

  <!-- ── Scenario switcher ─────────────────────────────────────────────────── -->
  {#if scenarios}
    <div class="scenario-bar">
      <span class="sc-label">Simulate:</span>
      {#each Object.entries(scenarios.scenarios) as [name, meta]}
        <button
          class="sc-btn"
          class:active={scenarios.active === name}
          data-color={meta.color}
          on:click={() => switchScenario(name)}
          title={meta.description}
        >
          {name.replace(/_/g, ' ')}
        </button>
      {/each}
    </div>
  {/if}

  <!-- ── Sensor grid ────────────────────────────────────────────────────────── -->
  <div class="sensor-grid">
    {#each Object.entries(SENSOR_META) as [key, meta]}
      <SensorCard
        {key}
        label={meta.label}
        unit={meta.unit}
        value={$liveSensor?.reading?.[key] ?? null}
        prev={prevReading?.[key] ?? null}
      />
    {/each}
  </div>

  <!-- ── Auto-inference panel ───────────────────────────────────────────────── -->
  <div class="infer-panel">

    <div class="infer-left">
      <h3>Automatic Live Inference
        {#if $isAutoInferring}<span class="pulse-dot"></span>{/if}
      </h3>
      <p class="hint">
        Fetches the last 20 live readings from the sensor API and runs a
        <strong>1-hour-ahead alarm forecast</strong> via the ML model.
        Results are saved to your history.
      </p>
      <div class="btn-row">
        <button
          class="btn-toggle"
          class:running={$isAutoInferring}
          on:click={toggleAuto}
        >
          {$isAutoInferring ? '■ Stop auto-inference' : '▶ Start auto-inference'}
        </button>
        {#if !$isAutoInferring}
          <button class="btn-once" on:click={runAuto} disabled={autoRunning}>
            {autoRunning ? 'Running…' : 'Run once'}
          </button>
        {/if}
      </div>
      {#if autoError}
        <p class="error">{autoError}</p>
      {/if}
    </div>

    <div class="infer-right">
      {#if $lastAutoResult}
        <RiskGauge value={$lastAutoResult.anomaly_probability} size={128} />
        <div class="result-text">
          <div class="prob-big">{($lastAutoResult.anomaly_probability * 100).toFixed(1)}%</div>
          <div class="prob-label">t+1h probability</div>
          <div class="alarm-badge" data-alarm={$lastAutoResult.alarm === 1}>
            {$lastAutoResult.alarm === 1 ? '⚠ ALARM' : '✓ Normal'}
          </div>
          <div class="obs-note">{$lastAutoResult.n_observations ?? '—'} observations</div>
          {#if topDrivers.length}
            <div class="drivers">
              <div class="drivers-label">Top risk drivers</div>
              {#each topDrivers as d}
                <div class="driver-row">
                  <span class="driver-dot" class:pos={d.shap_value > 0} class:neg={d.shap_value < 0}></span>
                  <span class="driver-name" title={d.feature}>{d.feature.replace(/_/g, ' ')}</span>
                  <span class="driver-shap" class:pos={d.shap_value > 0} class:neg={d.shap_value < 0}>
                    {d.shap_value > 0 ? '+' : ''}{d.shap_value.toFixed(3)}
                  </span>
                </div>
              {/each}
            </div>
          {/if}
        </div>
      {:else}
        <div class="no-result">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#cbd5e1" stroke-width="1.5">
            <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/>
            <line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          <p>No inference run yet</p>
        </div>
      {/if}
    </div>
  </div>

  <!-- ── Risk history chart ─────────────────────────────────────────────────── -->
  {#if chartData.length >= 2}
    <div class="chart-panel">
      <div class="chart-header">
        <h3>Risk Score — Session History</h3>
        <span class="chart-count">{chartData.length} point{chartData.length !== 1 ? 's' : ''}</span>
      </div>
      <div class="chart-scroll">
        <LineChart data={chartData} width={Math.max(680, chartData.length * 14)} height={150} />
      </div>
      <p class="hint">Red dashed line = alarm threshold (70%). Red dots = alarm events.</p>
    </div>
  {/if}

</div>

<style>
  .page { padding: 24px; max-width: 1120px; margin: 0 auto; }

  .page-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    margin-bottom: 14px;
    gap: 16px;
  }
  h2 { margin: 0; font-size: 1.3rem; color: #0f172a; }
  h3 { margin: 0 0 6px; font-size: 1rem; color: #1e293b; }
  .sub { margin: 2px 0 0; font-size: 0.78rem; color: #64748b; }
  .hint { font-size: 0.78rem; color: #94a3b8; margin: 6px 0 0; }

  .badge {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 0.78rem;
    font-weight: 600;
  }
  .badge.green  { background: #dcfce7; color: #15803d; }
  .badge.amber  { background: #fef3c7; color: #92400e; }
  .badge.red    { background: #fee2e2; color: #991b1b; }
  .badge.grey   { background: #f1f5f9; color: #64748b; }

  /* Scenario bar */
  .scenario-bar {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 18px;
    flex-wrap: wrap;
  }
  .sc-label { font-size: 0.78rem; color: #94a3b8; }
  .sc-btn {
    padding: 4px 13px;
    border-radius: 20px;
    border: 1px solid #e2e8f0;
    background: #fff;
    cursor: pointer;
    font-size: 0.78rem;
    font-weight: 500;
    transition: all 0.15s;
    text-transform: capitalize;
  }
  .sc-btn:hover { background: #f8fafc; border-color: #94a3b8; }
  .sc-btn.active { color: #fff; border-color: transparent; }
  .sc-btn.active[data-color="green"] { background: #16a34a; }
  .sc-btn.active[data-color="amber"] { background: #d97706; }
  .sc-btn.active[data-color="red"]   { background: #dc2626; }

  /* Sensor grid */
  .sensor-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(175px, 1fr));
    gap: 10px;
    margin-bottom: 22px;
  }

  /* Inference panel */
  .infer-panel {
    display: flex;
    gap: 28px;
    align-items: center;
    background: #fff;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    padding: 22px 24px;
    margin-bottom: 22px;
  }
  .infer-left { flex: 1; }
  .infer-right {
    display: flex;
    align-items: center;
    gap: 20px;
    min-width: 220px;
    justify-content: center;
  }

  .pulse-dot {
    display: inline-block;
    width: 8px; height: 8px;
    background: #22c55e;
    border-radius: 50%;
    margin-left: 8px;
    animation: pulse 1.2s ease-in-out infinite;
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50%       { opacity: 0.5; transform: scale(0.7); }
  }

  .btn-row { display: flex; gap: 8px; margin-top: 14px; }
  .btn-toggle {
    padding: 9px 18px;
    border: none;
    border-radius: 8px;
    background: #0f766e;
    color: #fff;
    font-weight: 600;
    font-size: 0.88rem;
    cursor: pointer;
    transition: background 0.15s;
  }
  .btn-toggle.running  { background: #dc2626; }
  .btn-toggle:hover    { filter: brightness(1.1); }
  .btn-once {
    padding: 9px 16px;
    border: 1px solid #0f766e;
    border-radius: 8px;
    background: transparent;
    color: #0f766e;
    font-weight: 500;
    font-size: 0.88rem;
    cursor: pointer;
    transition: background 0.15s;
  }
  .btn-once:hover:not(:disabled) { background: #f0fdf4; }
  .btn-once:disabled { opacity: 0.5; cursor: wait; }

  .result-text { text-align: center; }
  .prob-big { font-size: 2rem; font-weight: 800; color: #0f172a; line-height: 1; }
  .prob-label { font-size: 0.75rem; color: #94a3b8; margin: 3px 0 6px; }
  .alarm-badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 12px;
    font-size: 0.78rem;
    font-weight: 700;
    background: #dcfce7;
    color: #15803d;
  }
  .alarm-badge[data-alarm="true"] { background: #fee2e2; color: #991b1b; }
  .obs-note { font-size: 0.72rem; color: #cbd5e1; margin-top: 5px; }

  .drivers { margin-top: 10px; text-align: left; }
  .drivers-label { font-size: 0.68rem; color: #94a3b8; font-weight: 600; margin-bottom: 5px; text-transform: uppercase; letter-spacing: 0.04em; }
  .driver-row {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 3px;
    font-size: 0.72rem;
  }
  .driver-dot {
    width: 7px; height: 7px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .driver-dot.pos { background: #ef4444; }
  .driver-dot.neg { background: #22c55e; }
  .driver-name { color: #475569; flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 110px; }
  .driver-shap { font-weight: 700; white-space: nowrap; }
  .driver-shap.pos { color: #dc2626; }
  .driver-shap.neg { color: #16a34a; }

  .no-result {
    display: flex;
    flex-direction: column;
    align-items: center;
    color: #cbd5e1;
    font-size: 0.85rem;
    gap: 6px;
    padding: 12px;
  }

  .error { color: #dc2626; font-size: 0.82rem; margin-top: 8px; }

  /* Chart */
  .chart-panel {
    background: #fff;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    padding: 18px 22px;
  }
  .chart-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 12px;
  }
  .chart-count {
    font-size: 0.78rem;
    color: #94a3b8;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 2px 10px;
  }
  .chart-scroll { overflow-x: auto; }
</style>
