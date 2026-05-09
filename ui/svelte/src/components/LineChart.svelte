<!--
  Pure-SVG time-series line chart. No dependencies.
  Props:
    data      — array of { x: string (timestamp), y: number 0..1 }
    width     — SVG width in px (default 680)
    height    — SVG height in px (default 140)
    threshold — horizontal dashed alert line (default 0.7)
    color     — line/fill color (default #0f766e)
-->
<script>
  export let data      = [];
  export let width     = 680;
  export let height    = 140;
  export let threshold = 0.7;
  export let color     = '#0f766e';

  const PAD = { top: 10, right: 16, bottom: 28, left: 38 };

  $: iW = width  - PAD.left - PAD.right;
  $: iH = height - PAD.top  - PAD.bottom;

  $: pts = data.length < 2 ? [] : data.map((d, i) => ({
    x: PAD.left + (i / (data.length - 1)) * iW,
    y: PAD.top  + (1 - Math.max(0, Math.min(1, d.y))) * iH,
    v: d.y,
    ts: d.x,
  }));

  $: lineD = pts.length < 2 ? ''
    : 'M ' + pts.map(p => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' L ');

  $: areaD = pts.length < 2 ? ''
    : `${lineD} L ${pts[pts.length-1].x},${PAD.top + iH} L ${pts[0].x},${PAD.top + iH} Z`;

  $: thY = PAD.top + (1 - threshold) * iH;

  // X-axis: show first, middle, last timestamps
  $: xLabels = pts.length < 2 ? [] : [pts[0], pts[Math.floor(pts.length / 2)], pts[pts.length - 1]];

  function fmt(ts) {
    try {
      return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch { return ''; }
  }
</script>

<svg {width} {height} viewBox="0 0 {width} {height}" class="chart">
  <!-- Y grid + labels -->
  {#each [0, 0.25, 0.5, 0.75, 1.0] as tick}
    {@const gy = PAD.top + (1 - tick) * iH}
    <line x1={PAD.left} y1={gy} x2={PAD.left + iW} y2={gy} stroke="#f1f5f9" stroke-width="1"/>
    <text x={PAD.left - 5} y={gy + 4} text-anchor="end" font-size="9" fill="#94a3b8">
      {(tick * 100).toFixed(0)}%
    </text>
  {/each}

  <!-- Alarm threshold -->
  <line x1={PAD.left} y1={thY} x2={PAD.left + iW} y2={thY}
        stroke="#ef4444" stroke-width="1" stroke-dasharray="5,4" opacity="0.7"/>
  <text x={PAD.left + iW - 2} y={thY - 3} text-anchor="end" font-size="9" fill="#ef4444">alarm</text>

  <!-- Area + line -->
  {#if pts.length >= 2}
    <path d={areaD} fill={color} opacity="0.10"/>
    <path d={lineD} fill="none" stroke={color} stroke-width="2"
          stroke-linejoin="round" stroke-linecap="round"/>
    <!-- Alarm dots -->
    {#each pts as p}
      {#if p.v >= 0.7}
        <circle cx={p.x} cy={p.y} r="3.5" fill="#ef4444" opacity="0.85"/>
      {/if}
    {/each}
    <!-- Latest dot -->
    <circle cx={pts[pts.length-1].x} cy={pts[pts.length-1].y}
            r="4" fill={pts[pts.length-1].v >= 0.7 ? '#ef4444' : color}/>
  {/if}

  <!-- X-axis labels -->
  {#each xLabels as p}
    <text x={p.x} y={height - 4} text-anchor="middle" font-size="9" fill="#94a3b8">
      {fmt(p.ts)}
    </text>
  {/each}

  <!-- Axes -->
  <line x1={PAD.left} y1={PAD.top} x2={PAD.left} y2={PAD.top + iH}
        stroke="#e2e8f0" stroke-width="1"/>
  <line x1={PAD.left} y1={PAD.top + iH} x2={PAD.left + iW} y2={PAD.top + iH}
        stroke="#e2e8f0" stroke-width="1"/>
</svg>

<style>
  .chart { display: block; overflow: visible; }
</style>
