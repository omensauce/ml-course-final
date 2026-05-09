<script>
  export let value = 0;   // 0..1
  export let size  = 140;

  const R  = 50;
  const CX = 70, CY = 70;
  const CIRC = 2 * Math.PI * R;

  $: pct    = Math.max(0, Math.min(1, value));
  $: color  = pct >= 0.7 ? '#dc2626' : pct >= 0.4 ? '#d97706' : '#16a34a';
  $: bg     = pct >= 0.7 ? '#fee2e2' : pct >= 0.4 ? '#fef3c7' : '#dcfce7';
  $: label  = pct >= 0.7 ? 'ALARM'   : pct >= 0.4 ? 'WARNING' : 'NORMAL';
  $: dash   = pct * CIRC;
  $: gap    = CIRC - dash;
</script>

<div class="gauge-wrap" style="width:{size}px;height:{size}px;background:{bg};border-color:{color}">
  <svg width={size} height={size} viewBox="0 0 140 140">
    <circle cx={CX} cy={CY} r={R} fill="none" stroke="#e2e8f0" stroke-width="12"/>
    <circle
      cx={CX} cy={CY} r={R}
      fill="none"
      stroke={color}
      stroke-width="12"
      stroke-dasharray="{dash} {gap}"
      stroke-dashoffset={CIRC / 4}
      stroke-linecap="round"
      transform="rotate(-90, {CX}, {CY})"
      style="transition: stroke-dasharray 0.6s ease, stroke 0.5s ease"
    />
    <text x={CX} y={CY - 5} text-anchor="middle" font-size="23" font-weight="700" fill={color}>
      {(pct * 100).toFixed(0)}%
    </text>
    <text x={CX} y={CY + 15} text-anchor="middle" font-size="11" font-weight="600" fill={color} letter-spacing="1">
      {label}
    </text>
  </svg>
</div>

<style>
  .gauge-wrap {
    border-radius: 50%;
    border: 2px solid;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    transition: background 0.5s, border-color 0.5s;
    overflow: hidden;
    flex-shrink: 0;
  }
</style>
