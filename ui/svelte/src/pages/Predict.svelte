<script>
  import { apiPredict, apiExplain, apiGlobalImportance } from '../lib/api.js';
  import RiskGauge from '../components/RiskGauge.svelte';
  import FeatureImportanceBar from '../components/FeatureImportanceBar.svelte';

  // Default feature vector — representative normal operating point
  let featuresText = JSON.stringify({
    "te301020": 107.2, "pdt31008": 225.0, "pdt31001": 6.2, "pdt31007": 53.1,
    "lt31013": 62.0, "fq31050": 83.5, "lt301031": 44.0,
    "lic31012_pv": 79.8, "lic31012_op": 50.0, "lic31012_sp": 80.0,
    "lic31002_pv": 70.3, "lic31002_op": 48.0, "lic31002_sp": 70.0,
    "fic31011_pv": 413.5, "fic31011_op": 52.0, "fic31011_sp": 413.0,
    "te301020_max": 108.5, "pdt31008_max": 260.0, "pdt31001_max": 6.5,
    "pdt31007_max": 54.0, "lt31013_max": 65.0, "fq31050_max": 84.1,
    "lt301031_max": 47.0, "lic31012_pv_max": 80.2, "lic31002_pv_max": 71.5,
    "fic31011_pv_max": 415.0,
    "te301020_min": 106.5, "pdt31008_min": 218.0, "pdt31001_min": 5.9,
    "pdt31007_min": 52.5, "lt31013_min": 60.0, "fq31050_min": 82.8,
    "lt301031_min": 40.0, "lic31012_pv_min": 79.0, "lic31002_pv_min": 69.8,
    "fic31011_pv_min": 412.0,
    "lt31013_saturated": 0, "lic31012_deviation": 0.2, "lic31002_deviation": 0.3,
    "lic31002_deviation_max": 1.5, "fic31011_deviation": 0.5,
    "fic31011_deviation_max": 2.0,
    "pdt31008_roll3h_mean": 228.0, "pdt31008_roll3h_std": 15.2,
    "lt301031_roll3h_mean": 43.5, "lt301031_roll3h_std": 2.1,
    "fq31050_roll3h_mean": 83.3, "fq31050_roll3h_std": 0.4,
    "te301020_roll3h_mean": 107.3, "te301020_roll3h_std": 0.5,
    "hour_of_day": 14, "day_of_week": 2, "regime": 1,
    "pdt31008_roll_mean": 230.0, "pdt31008_roll_std": 14.8,
    "lic31002_pv_roll_mean": 70.2, "lic31002_pv_roll_std": 0.13,
    "fic31011_pv_roll_mean": 413.3, "fic31011_pv_roll_std": 0.8,
    "te301020_roll_mean": 107.2, "te301020_roll_std": 0.4,
    "failure_frequency_48": 2
  }, null, 2);

  // High-risk preset
  const HIGH_RISK_FEATURES = JSON.stringify({
    "te301020": 109.8, "pdt31008": 340.0, "pdt31001": 5.2, "pdt31007": 51.0,
    "lt31013": 62.0, "fq31050": 80.1, "lt301031": 8.0,
    "lic31012_pv": 76.5, "lic31012_op": 80.0, "lic31012_sp": 80.0,
    "lic31002_pv": 90.5, "lic31002_op": 95.0, "lic31002_sp": 70.0,
    "fic31011_pv": 420.0, "fic31011_op": 78.0, "fic31011_sp": 413.0,
    "te301020_max": 111.0, "pdt31008_max": 360.0, "pdt31001_max": 5.5,
    "pdt31007_max": 52.0, "lt31013_max": 65.0, "fq31050_max": 81.0,
    "lt301031_max": 15.0, "lic31012_pv_max": 78.0, "lic31002_pv_max": 93.0,
    "fic31011_pv_max": 422.0,
    "te301020_min": 108.5, "pdt31008_min": 305.0, "pdt31001_min": 4.8,
    "pdt31007_min": 49.5, "lt31013_min": 60.0, "fq31050_min": 79.5,
    "lt301031_min": 5.0, "lic31012_pv_min": 74.0, "lic31002_pv_min": 85.0,
    "fic31011_pv_min": 416.0,
    "lt31013_saturated": 1, "lic31012_deviation": 3.5, "lic31002_deviation": 20.5,
    "lic31002_deviation_max": 23.0, "fic31011_deviation": 7.0,
    "fic31011_deviation_max": 9.0,
    "pdt31008_roll3h_mean": 320.0, "pdt31008_roll3h_std": 22.0,
    "lt301031_roll3h_mean": 11.0, "lt301031_roll3h_std": 3.5,
    "fq31050_roll3h_mean": 80.5, "fq31050_roll3h_std": 0.9,
    "te301020_roll3h_mean": 110.0, "te301020_roll3h_std": 0.9,
    "hour_of_day": 3, "day_of_week": 0, "regime": 2,
    "pdt31008_roll_mean": 315.0, "pdt31008_roll_std": 20.5,
    "lic31002_pv_roll_mean": 88.0, "lic31002_pv_roll_std": 3.2,
    "fic31011_pv_roll_mean": 418.0, "fic31011_pv_roll_std": 2.1,
    "te301020_roll_mean": 109.5, "te301020_roll_std": 1.1,
    "failure_frequency_48": 9
  }, null, 2);

  let result       = null;
  let error        = '';
  let loading      = false;
  let parseError   = '';

  // Interpretability state
  let explainResult      = null;
  let showLocalImportance = true;
  let globalResult       = null;
  let showGlobal         = false;
  let globalLoading      = false;

  $: {
    try { JSON.parse(featuresText); parseError = ''; }
    catch (e) { parseError = `JSON error: ${e.message}`; }
  }

  async function run() {
    error = ''; result = null; explainResult = null; loading = true;
    try {
      const features = JSON.parse(featuresText);
      // Fire prediction and explanation in parallel
      const [pred, expl] = await Promise.allSettled([
        apiPredict(features),
        apiExplain(features),
      ]);
      if (pred.status === 'fulfilled') result = pred.value;
      else throw new Error(pred.reason?.message ?? 'Prediction failed');
      if (expl.status === 'fulfilled' && expl.value?.local_importance?.length)
        explainResult = expl.value;
    } catch (e) {
      error = e.message;
    } finally {
      loading = false;
    }
  }

  async function loadGlobal() {
    if (globalResult) { showGlobal = !showGlobal; return; }
    showGlobal = true;
    globalLoading = true;
    try {
      const r = await apiGlobalImportance();
      if (r?.importances?.length) globalResult = r;
    } catch { /* silently fail */ } finally {
      globalLoading = false;
    }
  }

  function loadHighRisk() { featuresText = HIGH_RISK_FEATURES; }
</script>

<div class="page">

  <div class="page-header">
    <div>
      <h2>Point-in-Time Predict</h2>
      <p class="sub">Submit a flat feature vector to the champion model and receive an anomaly risk score.</p>
    </div>
  </div>

  <div class="layout">
    <!-- Input panel -->
    <div class="input-panel">
      <div class="input-header">
        <span class="field-label">Feature vector (JSON)</span>
        <div class="preset-row">
          <button class="preset-btn" on:click={() => featuresText = JSON.stringify(JSON.parse(featuresText), null, 2)}>
            Format
          </button>
          <button class="preset-btn danger" on:click={loadHighRisk}>
            Load high-risk example
          </button>
        </div>
      </div>
      <textarea
        class:invalid={!!parseError}
        bind:value={featuresText}
        rows="20"
        spellcheck="false"
      ></textarea>
      {#if parseError}
        <p class="parse-error">{parseError}</p>
      {/if}

      <button class="btn-run" on:click={run} disabled={loading || !!parseError}>
        {loading ? 'Running prediction…' : 'Run prediction'}
      </button>
    </div>

    <!-- Result panel -->
    <div class="result-panel">
      {#if result}
        <div class="result-card">
          <div class="gauge-row">
            <RiskGauge value={result.risk_score} size={150} />
          </div>

          <div class="metrics">
            <div class="metric">
              <span class="metric-label">Risk score</span>
              <span class="metric-value">{result.risk_score?.toFixed(4)}</span>
            </div>
            <div class="metric">
              <span class="metric-label">Alarm</span>
              <span class="metric-value" class:alarm={result.alarm === 1}>
                {result.alarm === 1 ? '⚠ ALARM' : '✓ Normal'}
              </span>
            </div>
          </div>

          {#if result.recommendation}
            <div class="rec-box">
              <div class="rec-title">Maintenance recommendation</div>
              <div class="rec-body">{result.recommendation}</div>
            </div>
          {/if}

          <p class="saved-note">✓ Saved to your inference history</p>
        </div>
      {:else if error}
        <div class="error-card">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#dc2626" stroke-width="1.5">
            <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/>
            <line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          <p class="error">{error}</p>
          <p class="hint">Make sure the frontend API (port 8001) and inference API (port 8000) are running.</p>
        </div>
      {:else}
        <div class="placeholder">
          <svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="#e2e8f0" stroke-width="1.2">
            <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
          </svg>
          <p>Submit a feature vector to see results</p>
        </div>
      {/if}
    </div>
  </div>

  <!-- Local SHAP contributions (shown after a prediction run) -->
  {#if explainResult}
    <div class="explain-panel">
      <button class="explain-toggle" on:click={() => showLocalImportance = !showLocalImportance}>
        <span>Feature Contributions (SHAP)</span>
        <svg class="chevron" class:open={showLocalImportance} width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </button>
      {#if showLocalImportance}
        <p class="explain-hint">
          Red = pushes toward alarm · Green = pushes toward normal · Values = actual sensor reading
        </p>
        <FeatureImportanceBar importances={explainResult.local_importance} mode="local" topN={12} />
      {/if}
    </div>
  {/if}

  <!-- Global feature importance (lazy-loaded on first expand) -->
  <div class="global-panel">
    <button class="explain-toggle" on:click={loadGlobal}>
      <span>Model Feature Importance (Global)</span>
      <svg class="chevron" class:open={showGlobal} width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <polyline points="6 9 12 15 18 9"/>
      </svg>
    </button>
    {#if showGlobal}
      {#if globalLoading}
        <p class="explain-hint">Loading…</p>
      {:else if globalResult}
        <p class="explain-hint">
          Mean impurity decrease across all trees — which sensors the model relies on most overall.
        </p>
        <FeatureImportanceBar importances={globalResult.importances} mode="global" topN={15} />
      {:else}
        <p class="explain-hint">Global importance unavailable (model not loaded or no feature_importances_).</p>
      {/if}
    {/if}
  </div>

</div>

<style>
  .page { padding: 24px; max-width: 1100px; margin: 0 auto; }
  .page-header { margin-bottom: 20px; }
  h2 { margin: 0; font-size: 1.3rem; color: #0f172a; }
  .sub { margin: 3px 0 0; font-size: 0.78rem; color: #64748b; }

  .layout { display: grid; grid-template-columns: 1fr 340px; gap: 20px; align-items: start; }

  .input-panel {
    background: #fff;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    padding: 18px;
  }
  .input-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 10px;
    flex-wrap: wrap;
    gap: 8px;
  }
  .field-label { font-size: 0.82rem; font-weight: 600; color: #374151; }
  .preset-row { display: flex; gap: 6px; }
  .preset-btn {
    padding: 4px 10px;
    border-radius: 6px;
    border: 1px solid #e2e8f0;
    background: #f8fafc;
    font-size: 0.75rem;
    cursor: pointer;
    color: #475569;
    transition: background 0.15s;
  }
  .preset-btn:hover { background: #e2e8f0; }
  .preset-btn.danger { border-color: #fca5a5; color: #dc2626; }
  .preset-btn.danger:hover { background: #fee2e2; }

  textarea {
    width: 100%;
    padding: 12px;
    font-family: Consolas, 'Cascadia Code', monospace;
    font-size: 0.8rem;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    box-sizing: border-box;
    resize: vertical;
    line-height: 1.5;
    transition: border-color 0.15s;
    background: #fafafa;
  }
  textarea:focus { outline: none; border-color: #0f766e; background: #fff; }
  textarea.invalid { border-color: #fca5a5; background: #fff1f2; }
  .parse-error { color: #dc2626; font-size: 0.75rem; margin: 4px 0; }

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
  .gauge-row { display: flex; justify-content: center; margin-bottom: 20px; }

  .metrics { display: flex; flex-direction: column; gap: 10px; margin-bottom: 18px; }
  .metric {
    display: flex;
    justify-content: space-between;
    padding: 10px 14px;
    background: #f8fafc;
    border-radius: 8px;
    font-size: 0.88rem;
  }
  .metric-label { color: #64748b; font-weight: 500; }
  .metric-value { font-weight: 700; color: #0f172a; }
  .metric-value.alarm { color: #dc2626; }

  .rec-box {
    background: #fffbeb;
    border: 1px solid #fde68a;
    border-radius: 8px;
    padding: 12px 14px;
    margin-bottom: 14px;
  }
  .rec-title { font-size: 0.75rem; font-weight: 600; color: #92400e; margin-bottom: 4px; }
  .rec-body { font-size: 0.85rem; color: #78350f; }

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
  .error  { color: #dc2626; font-size: 0.85rem; }
  .hint   { font-size: 0.75rem; color: #94a3b8; }

  .placeholder {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    width: 100%;
    gap: 12px;
    color: #cbd5e1;
    font-size: 0.85rem;
    text-align: center;
    padding: 20px;
  }
  .placeholder p { margin: 0; }

  /* Interpretability panels */
  .explain-panel {
    margin-top: 18px;
    background: #fff;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    padding: 16px 18px;
  }

  .global-panel {
    margin-top: 18px;
    background: #fff;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    padding: 16px 18px;
  }

  .explain-toggle {
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
    background: none;
    border: none;
    padding: 0;
    cursor: pointer;
    font-size: 0.82rem;
    font-weight: 600;
    color: #1e293b;
    text-align: left;
    gap: 8px;
  }
  .explain-toggle:hover { color: #0f766e; }

  .chevron { transition: transform 0.2s; color: #94a3b8; flex-shrink: 0; }
  .chevron.open { transform: rotate(180deg); }

  .explain-hint {
    font-size: 0.72rem;
    color: #94a3b8;
    margin: 8px 0 12px;
  }

  @media (max-width: 800px) {
    .layout { grid-template-columns: 1fr; }
  }
</style>
