<script>
  export let key      = '';
  export let label    = '';
  export let value    = null;
  export let unit     = '';
  export let prev     = null;  // previous value for trend arrow
  export let anomalous = false;

  $: display = value === null ? '—' : typeof value === 'number' ? value.toFixed(2) : String(value);
  $: trend   = prev === null || value === null ? '' : value > prev + 0.05 ? '↑' : value < prev - 0.05 ? '↓' : '';
  $: trendCls = trend === '↑' ? 'up' : trend === '↓' ? 'down' : '';
</script>

<div class="card" class:anomalous>
  <div class="label">{label}</div>
  <div class="value">
    {display}
    <span class="unit">{unit}</span>
    {#if trend}<span class="trend {trendCls}">{trend}</span>{/if}
  </div>
  <div class="key">{key}</div>
</div>

<style>
  .card {
    background: #fff;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 12px 14px;
    transition: border-color 0.4s, background 0.4s;
    min-width: 0;
  }
  .card.anomalous {
    background: #fff1f2;
    border-color: #fca5a5;
    box-shadow: 0 0 0 2px rgba(220,38,38,0.08);
  }
  .label {
    font-size: 0.72rem;
    color: #64748b;
    margin-bottom: 5px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .value {
    font-size: 1.25rem;
    font-weight: 700;
    color: #0f172a;
    display: flex;
    align-items: baseline;
    gap: 4px;
  }
  .unit {
    font-size: 0.72rem;
    font-weight: 400;
    color: #94a3b8;
  }
  .trend { font-size: 0.9rem; font-weight: 700; }
  .trend.up   { color: #dc2626; }
  .trend.down { color: #2563eb; }
  .key {
    font-size: 0.62rem;
    color: #cbd5e1;
    font-family: Consolas, monospace;
    margin-top: 3px;
  }
</style>
