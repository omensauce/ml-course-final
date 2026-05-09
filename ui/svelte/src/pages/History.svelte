<script>
  import { onMount } from 'svelte';
  import { apiGetHistory, apiDeleteEntry, apiClearHistory } from '../lib/api.js';
  import LineChart from '../components/LineChart.svelte';

  let entries  = [];
  let loading  = true;
  let error    = '';
  let filter   = 'all';

  async function load() {
    loading = true; error = '';
    try { entries = await apiGetHistory(200); }
    catch (e) { error = e.message; }
    finally { loading = false; }
  }

  async function del(id) {
    await apiDeleteEntry(id).catch(() => {});
    entries = entries.filter(e => e.id !== id);
  }

  async function clearAll() {
    if (!confirm('Delete all inference history for this account?')) return;
    await apiClearHistory().catch(() => {});
    entries = [];
  }

  $: filtered = filter === 'all'
    ? entries
    : entries.filter(e => e.type.startsWith(filter));

  // Chart: chronological (oldest first) risk scores
  $: chartData = [...filtered]
    .reverse()
    .filter(e => getRisk(e) !== null)
    .map(e => ({ x: e.ts, y: getRisk(e) }));

  function getRisk(e) {
    const r = e.result;
    if (r.anomaly_probability !== undefined) return r.anomaly_probability;
    if (r.risk_score          !== undefined) return r.risk_score;
    return null;
  }

  function riskColor(v) {
    if (v === null) return '#9ca3af';
    return v >= 0.7 ? '#dc2626' : v >= 0.4 ? '#d97706' : '#16a34a';
  }

  function fmtTs(ts) {
    try { return new Date(ts).toLocaleString(); } catch { return ts; }
  }

  function typeColor(t) {
    if (t === 'predict')           return 'blue';
    if (t.startsWith('forecast'))  return 'purple';
    if (t.startsWith('auto'))      return 'green';
    return 'grey';
  }

  onMount(load);
</script>

<div class="page">

  <div class="page-header">
    <div>
      <h2>Inference History</h2>
      <p class="sub">All predictions and forecasts are stored per account in the database.</p>
    </div>
    <div class="header-controls">
      <select bind:value={filter}>
        <option value="all">All types</option>
        <option value="predict">Point-in-time predict</option>
        <option value="forecast">Horizon forecast</option>
        <option value="auto">Auto (live sensor)</option>
      </select>
      <button class="btn-refresh" on:click={load}>↻ Refresh</button>
      {#if entries.length > 0}
        <button class="btn-clear" on:click={clearAll}>Clear all</button>
      {/if}
    </div>
  </div>

  <!-- Risk chart -->
  {#if chartData.length >= 2}
    <div class="chart-panel">
      <div class="chart-hdr">
        <h3>Risk Score Over Time</h3>
        <span class="count-badge">{chartData.length} entries</span>
      </div>
      <div class="chart-scroll">
        <LineChart data={chartData} width={Math.max(680, chartData.length * 16)} height={150} />
      </div>
      <p class="hint">Chronological order, oldest left. Red dashes = alarm threshold (70%).</p>
    </div>
  {/if}

  <!-- Table -->
  {#if loading}
    <div class="state-msg">Loading history…</div>
  {:else if error}
    <div class="state-msg error">{error}</div>
  {:else if filtered.length === 0}
    <div class="empty">
      <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#cbd5e1" stroke-width="1.5">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
        <polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/>
        <line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/>
      </svg>
      <p>No records yet.</p>
      <p class="hint">Run inferences from the Dashboard, Predict, or Forecast pages.</p>
    </div>
  {:else}
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Timestamp</th>
            <th>Type</th>
            <th>Risk / Prob</th>
            <th>Alarm</th>
            <th>Details</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {#each filtered as e (e.id)}
            {@const risk = getRisk(e)}
            <tr>
              <td class="id-cell">{e.id}</td>
              <td class="ts-cell">{fmtTs(e.ts)}</td>
              <td>
                <span class="type-badge {typeColor(e.type)}">{e.type}</span>
              </td>
              <td class="risk-cell">
                {#if risk !== null}
                  <span style="color:{riskColor(risk)};font-weight:700">
                    {(risk * 100).toFixed(1)}%
                  </span>
                {:else}—{/if}
              </td>
              <td class="alarm-cell">
                {#if e.result.alarm === 1}
                  <span class="alarm-yes">⚠ Yes</span>
                {:else}
                  <span class="alarm-no">✓ No</span>
                {/if}
              </td>
              <td class="detail-cell">
                {#if e.type === 'predict' && e.result.recommendation}
                  <span class="rec" title={e.result.recommendation}>
                    {e.result.recommendation.slice(0, 40)}{e.result.recommendation.length > 40 ? '…' : ''}
                  </span>
                {:else if e.type.startsWith('forecast') || e.type.startsWith('auto')}
                  <span class="dim">horizon: {e.result.horizon_hours ?? 1}h · {e.result.n_observations ?? e.input.n_obs} obs</span>
                {:else}—{/if}
              </td>
              <td>
                <button class="btn-del" on:click={() => del(e.id)} title="Delete">×</button>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}

</div>

<style>
  .page { padding: 24px; max-width: 1100px; }

  .page-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    margin-bottom: 20px;
    gap: 16px;
    flex-wrap: wrap;
  }
  h2 { margin: 0; font-size: 1.3rem; color: #0f172a; }
  h3 { margin: 0; font-size: 1rem; color: #1e293b; }
  .sub  { margin: 3px 0 0; font-size: 0.78rem; color: #64748b; }
  .hint { font-size: 0.75rem; color: #94a3b8; margin: 6px 0 0; }

  .header-controls { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
  select {
    padding: 6px 10px;
    border-radius: 7px;
    border: 1px solid #e2e8f0;
    font-size: 0.82rem;
    background: #fff;
  }
  .btn-refresh {
    padding: 6px 13px;
    border-radius: 7px;
    border: 1px solid #0f766e;
    background: transparent;
    color: #0f766e;
    font-size: 0.82rem;
    cursor: pointer;
  }
  .btn-clear {
    padding: 6px 13px;
    border-radius: 7px;
    border: 1px solid #dc2626;
    background: transparent;
    color: #dc2626;
    font-size: 0.82rem;
    cursor: pointer;
  }

  /* Chart */
  .chart-panel {
    background: #fff;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    padding: 18px 22px;
    margin-bottom: 20px;
  }
  .chart-hdr {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 12px;
  }
  .chart-scroll { overflow-x: auto; }
  .count-badge {
    font-size: 0.75rem;
    color: #94a3b8;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 2px 10px;
  }

  /* Table */
  .table-wrap {
    background: #fff;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    overflow: hidden;
  }
  table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
  thead { background: #f8fafc; }
  th {
    text-align: left;
    padding: 11px 14px;
    border-bottom: 1px solid #e2e8f0;
    font-weight: 600;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: #475569;
  }
  td { padding: 10px 14px; border-bottom: 1px solid #f1f5f9; vertical-align: middle; }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: #fafafa; }

  .id-cell  { color: #94a3b8; font-size: 0.75rem; }
  .ts-cell  { white-space: nowrap; color: #64748b; }
  .risk-cell { white-space: nowrap; }
  .detail-cell { max-width: 260px; }

  .type-badge {
    display: inline-block;
    padding: 2px 9px;
    border-radius: 10px;
    font-size: 0.72rem;
    font-weight: 600;
  }
  .type-badge.blue   { background: #dbeafe; color: #1d4ed8; }
  .type-badge.purple { background: #ede9fe; color: #6d28d9; }
  .type-badge.green  { background: #dcfce7; color: #15803d; }
  .type-badge.grey   { background: #f1f5f9; color: #475569; }

  .alarm-yes { font-size: 0.78rem; font-weight: 700; color: #dc2626; }
  .alarm-no  { font-size: 0.78rem; font-weight: 600; color: #16a34a; }

  .rec  { color: #475569; font-size: 0.78rem; }
  .dim  { color: #94a3b8; font-size: 0.78rem; }

  .btn-del {
    border: none;
    background: transparent;
    color: #cbd5e1;
    cursor: pointer;
    font-size: 1.1rem;
    padding: 2px 7px;
    border-radius: 5px;
    line-height: 1;
  }
  .btn-del:hover { background: #fee2e2; color: #dc2626; }

  .state-msg { text-align: center; padding: 60px; color: #94a3b8; }
  .state-msg.error { color: #dc2626; }
  .empty {
    text-align: center;
    padding: 60px 20px;
    color: #94a3b8;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6px;
  }
  .empty p { margin: 0; }
</style>
