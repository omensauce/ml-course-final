<script>
  import { apiForecast } from '../lib/api.js';
  import RiskGauge from '../components/RiskGauge.svelte';

  // 12-hour window showing gradual pressure escalation (anomaly scenario)
  const DEFAULT_OBS = [
    {"te301020":107.1,"pdt31008":220.0,"pdt31001":6.2,"pdt31007":53.0,"fq31050":84.0,"lt301031":47.0,"lic31012_pv":80.0,"lic31002_pv":70.0,"fic31011_pv":413.0},
    {"te301020":107.2,"pdt31008":221.5,"pdt31001":6.3,"pdt31007":53.2,"fq31050":84.1,"lt301031":46.5,"lic31012_pv":79.9,"lic31002_pv":70.1,"fic31011_pv":413.2},
    {"te301020":107.0,"pdt31008":222.0,"pdt31001":6.1,"pdt31007":52.8,"fq31050":84.0,"lt301031":47.2,"lic31012_pv":80.1,"lic31002_pv":70.0,"fic31011_pv":413.0},
    {"te301020":107.3,"pdt31008":224.0,"pdt31001":6.4,"pdt31007":53.5,"fq31050":83.9,"lt301031":46.0,"lic31012_pv":79.8,"lic31002_pv":70.2,"fic31011_pv":413.5},
    {"te301020":107.5,"pdt31008":226.0,"pdt31001":6.5,"pdt31007":54.0,"fq31050":83.8,"lt301031":45.0,"lic31012_pv":79.7,"lic31002_pv":70.4,"fic31011_pv":413.8},
    {"te301020":107.4,"pdt31008":228.0,"pdt31001":6.3,"pdt31007":53.9,"fq31050":83.7,"lt301031":44.0,"lic31012_pv":79.6,"lic31002_pv":70.6,"fic31011_pv":414.0},
    {"te301020":107.6,"pdt31008":230.5,"pdt31001":6.2,"pdt31007":53.7,"fq31050":83.5,"lt301031":43.0,"lic31012_pv":79.5,"lic31002_pv":70.8,"fic31011_pv":414.2},
    {"te301020":107.8,"pdt31008":235.0,"pdt31001":6.1,"pdt31007":53.5,"fq31050":83.4,"lt301031":42.0,"lic31012_pv":79.4,"lic31002_pv":71.0,"fic31011_pv":414.5},
    {"te301020":108.0,"pdt31008":240.0,"pdt31001":6.0,"pdt31007":53.3,"fq31050":83.2,"lt301031":41.0,"lic31012_pv":79.3,"lic31002_pv":71.2,"fic31011_pv":414.8},
    {"te301020":108.2,"pdt31008":250.0,"pdt31001":5.9,"pdt31007":53.1,"fq31050":83.0,"lt301031":40.0,"lic31012_pv":79.2,"lic31002_pv":71.5,"fic31011_pv":415.0},
    {"te301020":108.5,"pdt31008":265.0,"pdt31001":5.8,"pdt31007":52.9,"fq31050":82.8,"lt301031":38.0,"lic31012_pv":79.1,"lic31002_pv":71.8,"fic31011_pv":415.2},
    {"te301020":108.8,"pdt31008":280.0,"pdt31001":5.7,"pdt31007":52.7,"fq31050":82.6,"lt301031":36.0,"lic31012_pv":78.9,"lic31002_pv":72.1,"fic31011_pv":415.5},
  ];

  let obsText  = JSON.stringify(DEFAULT_OBS, null, 2);
  let horizon  = 1;
  let result   = null;
  let error    = '';
  let loading  = false;
  let parseErr = '';

  $: {
    try {
      const parsed = JSON.parse(obsText);
      if (!Array.isArray(parsed))      parseErr = 'Must be a JSON array';
      else if (parsed.length < 12)     parseErr = `Need ≥12 readings, got ${parsed.length}`;
      else                             parseErr = '';
    } catch (e) { parseErr = `JSON error: ${e.message}`; }
  }

  async function run() {
    error = ''; result = null; loading = true;
    try {
      const obs = JSON.parse(obsText);
      result = await apiForecast(obs, Number(horizon));
    } catch (e) {
      error = e.message;
    } finally {
      loading = false;
    }
  }
</script>

<div class="page">

  <div class="page-header">
    <div>
      <h2>Horizon Forecast</h2>
      <p class="sub">
        Provide ≥12 hourly sensor readings (oldest first) and predict anomaly probability
        at a chosen horizon ahead. Results are saved to your history.
      </p>
    </div>
  </div>

  <div class="layout">

    <!-- Config + input -->
    <div class="input-panel">

      <div class="horizon-row">
        <span class="field-label">Forecast horizon</span>
        <div class="horizon-btns">
          {#each [[1,'+1h (immediate)'],[3,'+3h (short-term)'],[6,'+6h (shift plan)']] as [h, label]}
            <button
              class="h-btn"
              class:active={horizon === h}
              on:click={() => horizon = h}
            >{label}</button>
          {/each}
        </div>
      </div>

      <div class="obs-header">
        <span class="field-label">Observations — JSON array, oldest first</span>
        <span class="obs-count">{#if !parseErr}
          {JSON.parse(obsText).length} readings
        {/if}</span>
      </div>
      <textarea
        class:invalid={!!parseErr}
        bind:value={obsText}
        rows="20"
        spellcheck="false"
      ></textarea>
      {#if parseErr}
        <p class="parse-error">{parseErr}</p>
      {/if}

      <button class="btn-run" on:click={run} disabled={loading || !!parseErr}>
        {loading ? `Forecasting t+${horizon}h…` : `Run t+${horizon}h forecast`}
      </button>
    </div>

    <!-- Result -->
    <div class="result-panel">
      {#if result}
        <div class="result-card">
          <div class="gauge-row">
            <RiskGauge value={result.anomaly_probability} size={150} />
          </div>
          <div class="metrics">
            <div class="metric">
              <span class="metric-label">Horizon</span>
              <span class="metric-value">t+{result.horizon_hours}h</span>
            </div>
            <div class="metric">
              <span class="metric-label">Anomaly probability</span>
              <span class="metric-value">{(result.anomaly_probability * 100).toFixed(2)}%</span>
            </div>
            <div class="metric">
              <span class="metric-label">Alarm</span>
              <span class="metric-value" class:alarm={result.alarm === 1}>
                {result.alarm === 1 ? '⚠ ALARM' : '✓ Normal'}
              </span>
            </div>
            <div class="metric">
              <span class="metric-label">Observations used</span>
              <span class="metric-value">{result.n_observations}</span>
            </div>
          </div>
          <p class="saved-note">✓ Saved to your inference history</p>
        </div>
      {:else if error}
        <div class="error-card">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#dc2626" stroke-width="1.5">
            <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/>
            <line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          <p class="error">{error}</p>
          <p class="hint">Check that both APIs are running (ports 8000 and 8001).</p>
        </div>
      {:else}
        <div class="placeholder">
          <svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="#e2e8f0" stroke-width="1.2">
            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
          </svg>
          <p>Submit {horizon}h-ahead forecast</p>
          <p class="hint">The demo data shows escalating PDT31008 pressure — a realistic pre-alarm scenario.</p>
        </div>
      {/if}
    </div>

  </div>
</div>

<style>
  .page { padding: 24px; max-width: 1100px; }
  .page-header { margin-bottom: 20px; }
  h2 { margin: 0; font-size: 1.3rem; color: #0f172a; }
  .sub { margin: 3px 0 0; font-size: 0.78rem; color: #64748b; max-width: 640px; }

  .layout { display: grid; grid-template-columns: 1fr 340px; gap: 20px; align-items: start; }

  .input-panel {
    background: #fff;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    padding: 18px;
  }

  .horizon-row {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 18px;
    flex-wrap: wrap;
  }
  .field-label { font-size: 0.82rem; font-weight: 600; color: #374151; white-space: nowrap; }
  .horizon-btns { display: flex; gap: 6px; flex-wrap: wrap; }
  .h-btn {
    padding: 5px 13px;
    border-radius: 7px;
    border: 1px solid #e2e8f0;
    background: #f8fafc;
    font-size: 0.8rem;
    cursor: pointer;
    color: #475569;
    transition: all 0.15s;
  }
  .h-btn:hover  { border-color: #0f766e; color: #0f766e; }
  .h-btn.active { background: #0f766e; color: #fff; border-color: #0f766e; }

  .obs-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 8px;
  }
  .obs-count { font-size: 0.75rem; color: #94a3b8; }

  textarea {
    width: 100%;
    padding: 12px;
    font-family: Consolas, 'Cascadia Code', monospace;
    font-size: 0.79rem;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    box-sizing: border-box;
    resize: vertical;
    line-height: 1.5;
    transition: border-color 0.15s;
    background: #fafafa;
  }
  textarea:focus  { outline: none; border-color: #0f766e; background: #fff; }
  textarea.invalid { border-color: #fca5a5; background: #fff1f2; }
  .parse-error    { color: #dc2626; font-size: 0.75rem; margin: 4px 0; }

  .btn-run {
    margin-top: 12px;
    padding: 10px 22px;
    background: #0f766e;
    color: #fff;
    border: none;
    border-radius: 8px;
    font-weight: 600;
    font-size: 0.9rem;
    cursor: pointer;
    transition: background 0.15s;
    width: 100%;
  }
  .btn-run:hover:not(:disabled) { background: #0d6460; }
  .btn-run:disabled { opacity: 0.6; cursor: wait; }

  /* Result */
  .result-panel {
    background: #fff;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    padding: 22px 18px;
    min-height: 320px;
    display: flex;
    align-items: flex-start;
  }
  .result-card { width: 100%; }
  .gauge-row   { display: flex; justify-content: center; margin-bottom: 20px; }

  .metrics { display: flex; flex-direction: column; gap: 8px; margin-bottom: 16px; }
  .metric {
    display: flex;
    justify-content: space-between;
    padding: 9px 13px;
    background: #f8fafc;
    border-radius: 8px;
    font-size: 0.85rem;
  }
  .metric-label { color: #64748b; font-weight: 500; }
  .metric-value { font-weight: 700; color: #0f172a; }
  .metric-value.alarm { color: #dc2626; }

  .saved-note { font-size: 0.75rem; color: #16a34a; text-align: center; }

  .error-card {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 10px;
    padding: 20px;
    text-align: center;
    width: 100%;
  }
  .error { color: #dc2626; font-size: 0.85rem; }
  .hint  { font-size: 0.75rem; color: #94a3b8; }

  .placeholder {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    width: 100%;
    gap: 10px;
    color: #cbd5e1;
    font-size: 0.85rem;
    text-align: center;
    padding: 20px;
  }
  .placeholder p { margin: 0; }

  @media (max-width: 800px) {
    .layout { grid-template-columns: 1fr; }
  }
</style>
