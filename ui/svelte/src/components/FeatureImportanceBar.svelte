<script>
  /**
   * Diverging bar chart for SHAP (local) or feature_importances_ (global).
   *
   * Local mode  — expects importances: [{feature, value, shap_value}]
   *   Red bars  → positive SHAP  (pushes toward alarm)
   *   Green bars → negative SHAP (pushes toward normal)
   *   Bars diverge from a center axis.
   *
   * Global mode — expects importances: [{feature, importance}]
   *   Single teal bars sorted by importance.
   */
  export let importances = [];
  export let mode = 'local';   // 'local' | 'global'
  export let topN = 12;

  $: items = importances.slice(0, topN);

  // Compute the max absolute value for proportional bar widths
  $: maxAbs = items.reduce((m, d) => {
    const v = mode === 'local' ? Math.abs(d.shap_value ?? 0) : (d.importance ?? 0);
    return Math.max(m, v);
  }, 1e-9);

  function pct(v) {
    return Math.min(100, (Math.abs(v) / maxAbs) * 100).toFixed(1) + '%';
  }

  function shortName(f) {
    // Trim long auto-generated suffixes for readability
    return f.replace(/_roll_mean$/, ' (mean)')
            .replace(/_roll_std$/,  ' (std)')
            .replace(/_delta$/,     ' (Δ)')
            .replace(/_wmean$/,     ' (wmean)')
            .replace(/_wstd$/,      ' (wstd)')
            .replace(/_wtrend$/,    ' (trend)');
  }
</script>

<div class="chart">
  {#if mode === 'local'}
    <!-- Diverging layout with center axis -->
    <div class="axis-header">
      <span class="axis-label left">← Normal</span>
      <span class="axis-label right">Alarm →</span>
    </div>
    {#each items as item (item.feature)}
      {@const sv = item.shap_value ?? 0}
      <div class="row">
        <span class="fname" title={item.feature}>{shortName(item.feature)}</span>
        <div class="bars">
          <!-- Left (negative / normal-pushing) half -->
          <div class="half left">
            {#if sv < 0}
              <div class="bar neg" style="width:{pct(sv)}"></div>
            {/if}
          </div>
          <div class="axis-line"></div>
          <!-- Right (positive / alarm-pushing) half -->
          <div class="half right">
            {#if sv > 0}
              <div class="bar pos" style="width:{pct(sv)}"></div>
            {/if}
          </div>
        </div>
        <span class="val" title="feature value">{item.value?.toFixed(2) ?? '—'}</span>
        <span class="shap" class:pos={sv > 0} class:neg={sv < 0}>
          {sv > 0 ? '+' : ''}{sv.toFixed(4)}
        </span>
      </div>
    {/each}

  {:else}
    <!-- Global: single bar from left -->
    {#each items as item (item.feature)}
      {@const iv = item.importance ?? 0}
      <div class="row global">
        <span class="fname" title={item.feature}>{shortName(item.feature)}</span>
        <div class="global-bar-wrap">
          <div class="bar global-bar" style="width:{pct(iv)}"></div>
        </div>
        <span class="shap">{iv.toFixed(4)}</span>
      </div>
    {/each}
  {/if}
</div>

<style>
  .chart { width: 100%; font-size: 0.78rem; }

  .axis-header {
    display: flex;
    justify-content: space-between;
    font-size: 0.7rem;
    color: #94a3b8;
    margin-bottom: 6px;
    padding: 0 0 0 140px; /* align with bar area */
  }
  .axis-label.left  { margin-right: auto; }
  .axis-label.right { margin-left: auto;  }

  .row {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 5px;
    min-height: 20px;
  }

  .fname {
    width: 136px;
    min-width: 136px;
    text-align: right;
    color: #475569;
    font-size: 0.72rem;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  /* Local mode bar area */
  .bars {
    flex: 1;
    display: flex;
    align-items: center;
    min-width: 0;
  }
  .half {
    flex: 1;
    display: flex;
    height: 14px;
  }
  .half.left  { justify-content: flex-end; }
  .half.right { justify-content: flex-start; }

  .axis-line {
    width: 2px;
    height: 18px;
    background: #cbd5e1;
    flex-shrink: 0;
  }

  .bar {
    height: 100%;
    border-radius: 2px;
    transition: width 0.3s ease;
  }
  .bar.pos { background: #ef4444; }
  .bar.neg { background: #22c55e; }

  .val {
    width: 54px;
    text-align: right;
    color: #64748b;
    font-size: 0.7rem;
    white-space: nowrap;
  }

  .shap {
    width: 60px;
    text-align: right;
    font-weight: 600;
    font-size: 0.72rem;
    color: #64748b;
  }
  .shap.pos { color: #dc2626; }
  .shap.neg { color: #16a34a; }

  /* Global mode */
  .row.global .fname { text-align: left; }
  .global-bar-wrap {
    flex: 1;
    height: 14px;
    background: #f1f5f9;
    border-radius: 3px;
    overflow: hidden;
  }
  .global-bar {
    height: 100%;
    background: #0f766e;
    border-radius: 3px;
  }
</style>
