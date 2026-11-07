"""Phone-friendly, browser-driven public countdowns anchored to server time.

These count down to the next *scheduled UTC time boundary*, not to a
verified active contract. No trading controls, database writes, APIs, or keys.
"""
from __future__ import annotations

import math
import time

DURATIONS = {'5m': 300, '15m': 900, '1h': 3600}


def seconds_to_next_boundary(now_utc: float, timeframe: str) -> int:
    """Remaining whole seconds; 1..duration, including exactly at a boundary."""
    if timeframe not in DURATIONS:
        raise ValueError('Unsupported timeframe')
    if not math.isfinite(now_utc):
        raise ValueError('Timestamp must be finite')
    dur = DURATIONS[timeframe]
    return int((math.floor(now_utc / dur) + 1) * dur - math.floor(now_utc))


def timer_html(server_epoch_ms: int | None = None) -> str:
    """Self-contained HTML/CSS/JS for a stable phone clock.

    IMPORTANT: this HTML is trusted static source. Never interpolate market,
    user, database or other untrusted content into the iframe.
    """
    if server_epoch_ms is None:
        server_epoch_ms = round(time.time() * 1000)
    if not isinstance(server_epoch_ms, int) or server_epoch_ms < 0:
        raise ValueError('Server timestamp must be a positive integer in milliseconds')
    markup = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<style>
* {box-sizing:border-box}
html,body {margin:0;padding:0;background:transparent;color:#ffebf5;font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
.timers {display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;padding:3px 1px 5px}
.round-timer {min-width:0;padding:12px 11px 10px;border:1px solid rgba(255,171,214,.32);border-radius:15px;background:linear-gradient(148deg,#332237,#241b2d);box-shadow:0 9px 17px rgba(0,0,0,.13);}
.topline {display:flex;justify-content:space-between;align-items:center;gap:4px}
.label {color:#ffb2d3;font-size:11px;letter-spacing:.85px;font-weight:800;white-space:nowrap}
.petal {font-size:14px;flex-shrink:0}
.remaining {display:block;font-weight:850;font-variant-numeric:tabular-nums;letter-spacing:.45px;font-size:clamp(21px,3.3vw,31px);line-height:1.35;margin-top:7px;color:#fff1f9;white-space:nowrap}
.track {width:100%;height:5px;overflow:hidden;border-radius:10px;background:#51354d;margin-top:8px}
.fill {height:100%;width:100%;background:linear-gradient(90deg,#ffa8cc,#ef77b5);transform-origin:left center;transition:transform .16s linear}
.caption {font-size:9px;font-weight:650;letter-spacing:.3px;color:#c8a4ba;margin-top:7px;line-height:1.25}
@media (max-width:480px){.timers{gap:5px}.round-timer{padding:10px 7px;border-radius:12px}.label{font-size:9px}.remaining{font-size:clamp(18px,5vw,26px)}.caption{font-size:8px}.petal{font-size:11px}}
</style></head><body>
<div class="timers" role="group" aria-label="Countdown to next UTC time boundaries">
  <section class="round-timer"><div class="topline"><span class="label">5 MINUTES</span><span class="petal">🌸</span></div><output id="clock-5m" class="remaining" aria-label="Five-minute interval countdown">--:--</output><div class="track"><div id="fill-5m" class="fill"></div></div><div class="caption">NEXT UTC BOUNDARY</div></section>
  <section class="round-timer"><div class="topline"><span class="label">15 MINUTES</span><span class="petal">🌷</span></div><output id="clock-15m" class="remaining" aria-label="Fifteen-minute interval countdown">--:--</output><div class="track"><div id="fill-15m" class="fill"></div></div><div class="caption">NEXT UTC BOUNDARY</div></section>
  <section class="round-timer"><div class="topline"><span class="label">1 HOUR</span><span class="petal">✿</span></div><output id="clock-1h" class="remaining" aria-label="One-hour interval countdown">--:--</output><div class="track"><div id="fill-1h" class="fill"></div></div><div class="caption">NEXT UTC BOUNDARY</div></section>
</div>
<script>
(() => {
  'use strict';
  // Anchor browser wall time to a monotonic clock. Streamlit's eight-second
  // market data fragment refreshes separately and never resets these clocks.
  // Absolute time comes from the PC hosting the private collector.
  // The phone wall clock might be set incorrectly, so only use local elapsed time.
  const hostEpochMs = __SERVER_EPOCH_MS__;
  const browserStartWall = Date.now();
  const browserStartPerf = performance.now();
  let lastSyncedMs = hostEpochMs;
  function utcNowMs() {
    // Date.now elapsed covers phone sleep; performance.now covers wall-clock changes.
    const elapsed = Math.max(0, Date.now() - browserStartWall,
                             performance.now() - browserStartPerf);
    lastSyncedMs = Math.max(lastSyncedMs, hostEpochMs + elapsed);
    return lastSyncedMs;
  }
  const intervals = [ ['5m', 300], ['15m', 900], ['1h', 3600] ];
  const clocks = intervals.map(([key, secs]) => ({
    secs, output: document.getElementById('clock-' + key),
    fill: document.getElementById('fill-' + key), lastText: null
  }));
  function pad2(n) { return String(n).padStart(2, '0'); }
  function show() {
    const now = utcNowMs();
    for (const row of clocks) {
      const period = row.secs * 1000;
      const boundary = (Math.floor(now / period) + 1) * period;
      const left = Math.max(0, Math.ceil((boundary - now) / 1000));
      const mins = Math.floor(left / 60);
      const sec = left % 60;
      const text = pad2(mins) + ':' + pad2(sec);
      if (text !== row.lastText) { row.output.textContent = text; row.lastText = text; }
      const fraction = Math.max(0, Math.min(1, (boundary - now) / period));
      row.fill.style.transform = 'scaleX(' + fraction + ')';
    }
  }
  show();
  setInterval(show, 150);
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) show();
  });
})();
</script></body></html>'''
    return markup.replace('__SERVER_EPOCH_MS__', str(server_epoch_ms))
