"""Maps Prospector workspace — Maps Search preview, opens SolverHunter in browser."""
from __future__ import annotations

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from jarvis_ui import theme as T

try:
    from PyQt6.QtWebEngineCore import QWebEnginePage
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    _WEB_ENGINE = True
except Exception:  # pragma: no cover - depends on optional dep
    QWebEnginePage = None
    QWebEngineView = None
    _WEB_ENGINE = False


_BASE = QUrl("https://prospector.local/")
_SOLVERHUNTER_URL = "https://www.solverhunter.com/"


def _dashboard_html() -> str:
    return _HTML_TEMPLATE.replace("%%TARGET_URL%%", _SOLVERHUNTER_URL)


if _WEB_ENGINE:

    class _ExternalBrowserPage(QWebEnginePage):
        """Open SolverHunter in the system browser instead of the embedded view."""

        def acceptNavigationRequest(self, url, nav_type, is_main_frame):
            if is_main_frame and url.scheme() in ("http", "https"):
                host = (url.host() or "").lower().removeprefix("www.")
                if host == "solverhunter.com":
                    QDesktopServices.openUrl(url)
                    return False
            return super().acceptNavigationRequest(url, nav_type, is_main_frame)


class MapsProspectorView(QWidget):
    """Maps Search dashboard preview — any click opens SolverHunter in browser."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {T.BG};")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        if _WEB_ENGINE:
            self._web = QWebEngineView()
            self._web.setPage(_ExternalBrowserPage(self._web))
            self._web.setStyleSheet("background: #f8fafc;")
            self._show_maps_search()
            lay.addWidget(self._web)
        else:
            self._web = None
            msg = QLabel(
                "QtWebEngine is not installed — Maps Prospector preview unavailable.\n"
                "Install with:  pip install PyQt6-WebEngine"
            )
            msg.setWordWrap(True)
            msg.setStyleSheet(f"color: {T.TEXT}; padding: 32px;")
            lay.addWidget(msg)

    def _show_maps_search(self):
        if self._web is not None:
            self._web.setHtml(_dashboard_html(), _BASE)

    def reset_overlay(self):
        """Reload Maps Search whenever the section opens."""
        self._show_maps_search()


_HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {
    --emerald:#10b981; --emerald-600:#059669; --emerald-700:#047857;
    --slate-50:#f8fafc; --slate-200:#e2e8f0; --slate-400:#94a3b8;
    --slate-500:#64748b; --slate-600:#475569; --slate-900:#0f172a;
  }
  * { box-sizing:border-box; }
  html,body { height:100%; margin:0; }
  body {
    font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
    background:var(--slate-50); color:var(--slate-900);
    -webkit-font-smoothing:antialiased; overflow:hidden;
    cursor:pointer;
  }
  .app { height:100vh; display:flex; flex-direction:column; }

  .topbar {
    height:48px; flex:0 0 48px; display:flex; align-items:center; gap:14px;
    padding:0 20px; background:#fff; border-bottom:1px solid var(--slate-200);
  }
  .topbar .title { font-size:14px; font-weight:600; }
  .tabs { display:flex; gap:4px; margin-left:8px; }
  .tab {
    height:30px; padding:0 12px; border-radius:8px; border:none;
    background:transparent; font-size:12px; font-weight:600; color:var(--slate-500);
    cursor:pointer;
  }
  .tab.active { background:var(--slate-900); color:#fff; }
  .search {
    margin:0 auto; display:flex; align-items:center; gap:8px; width:100%;
    max-width:560px; height:32px; padding:0 10px; border-radius:8px;
    border:1px solid var(--slate-200); background:var(--slate-50); color:var(--slate-500);
    font-size:12px;
  }
  .search .dot { width:20px;height:20px;border-radius:50%;background:var(--emerald);
    display:grid;place-items:center;color:#fff;font-size:11px;margin-left:auto; }
  .chip { display:flex;align-items:center;gap:8px;border:1px solid var(--slate-200);
    border-radius:999px;padding:4px 10px;font-size:12px;font-weight:500;color:var(--slate-600); }
  .chip .av { width:22px;height:22px;border-radius:50%;background:#d1fae5;color:var(--emerald-700);
    display:grid;place-items:center;font-size:10px;font-weight:700; }
  .plus { width:26px;height:26px;border-radius:50%;border:1px solid var(--slate-200);
    color:var(--slate-500);display:grid;place-items:center;font-size:15px; }

  .body { flex:1; overflow:auto; padding:18px 22px 28px; }
  .row { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:14px; }
  h1 { font-size:16px; font-weight:600; margin:0; }
  h1 b { color:var(--emerald-600); }
  .actions { display:flex; gap:8px; }
  .btn { display:inline-flex; align-items:center; gap:8px; height:36px; padding:0 16px;
    border-radius:9px; font-size:13px; font-weight:500; cursor:pointer; border:1px solid transparent; }
  .btn.ghost { background:#fff; border-color:var(--slate-200); color:var(--slate-600); }
  .btn.primary { background:var(--emerald-600); color:#fff; }
  .btn.dark { background:var(--slate-900); color:#fff; }

  .aibar { display:flex; align-items:center; gap:10px; padding:10px;
    border-radius:14px; border:1px solid #bbf7d0;
    background:linear-gradient(90deg,#ecfdf5,#ffffff 40%,#ecfdf5);
    box-shadow:0 1px 2px rgba(15,23,42,.04); margin-bottom:16px; }
  .aibar .spark { width:32px;height:32px;border-radius:9px;background:var(--emerald-600);
    color:#fff;display:grid;place-items:center;font-size:15px; }
  .aibar input { flex:1; height:36px; border:1px solid var(--slate-200); border-radius:9px;
    padding:0 12px; font-size:13px; color:var(--slate-600); background:#fff; outline:none; pointer-events:none; }

  .grid { display:grid; grid-template-columns:280px 1fr; gap:16px; }
  .card { background:#fff; border:1px solid var(--slate-200); border-radius:14px;
    box-shadow:0 1px 2px rgba(15,23,42,.04); }
  .filters { padding:16px; display:flex; flex-direction:column; gap:16px; }
  .lbl { font-size:12px; font-weight:600; color:var(--slate-600); margin-bottom:6px; display:block; }
  .field { display:flex; align-items:center; gap:8px; border:1px solid var(--slate-200);
    border-radius:9px; padding:8px 11px; font-size:13px; color:var(--slate-900); pointer-events:none; }
  .field .pin { color:var(--emerald-600); }
  select.field { width:100%; appearance:none; background:#fff; pointer-events:none; }
  .range { border:1px solid var(--slate-200); border-radius:9px; padding:9px 11px; pointer-events:none; }
  .range .top { display:flex; justify-content:space-between; font-size:11px; color:var(--slate-500); margin-bottom:5px; }
  .range .top b { color:var(--emerald-600); }
  input[type=range] { width:100%; accent-color:var(--emerald-600); pointer-events:none; }
  .range .scale { display:flex; justify-content:space-between; font-size:10px; color:var(--slate-400); margin-top:4px; }
  .twocol { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
  .mini { display:flex; align-items:center; justify-content:center; gap:6px; height:36px;
    border:1px solid var(--slate-200); border-radius:9px; font-size:12px; font-weight:500;
    color:var(--slate-600); cursor:pointer; }

  .map { position:relative; min-height:420px; border-radius:14px; overflow:hidden;
    border:1px solid var(--slate-200);
    background:
      radial-gradient(120px 120px at 30% 40%, rgba(16,185,129,.10), transparent 70%),
      radial-gradient(160px 160px at 70% 60%, rgba(56,189,248,.10), transparent 70%),
      linear-gradient(0deg, rgba(148,163,184,.10) 1px, transparent 1px),
      linear-gradient(90deg, rgba(148,163,184,.10) 1px, transparent 1px),
      #eef2f6;
    background-size:auto,auto,28px 28px,28px 28px,auto; }
  .map .tag { position:absolute; top:12px; left:12px; display:flex; gap:6px;
    background:#fff; border:1px solid var(--slate-200); border-radius:8px; padding:4px;
    font-size:12px; font-weight:600; color:var(--slate-600); }
  .map .tag .on { background:var(--slate-900); color:#fff; padding:3px 10px; border-radius:6px; }
  .map .tag .off { padding:3px 10px; }
  .map .marker { position:absolute; width:14px; height:14px; border-radius:50%;
    background:var(--emerald); border:2px solid #fff; box-shadow:0 1px 4px rgba(0,0,0,.25); }
  .map .pinbig { position:absolute; left:46%; top:48%; font-size:26px; filter:drop-shadow(0 3px 4px rgba(0,0,0,.3)); }

  .list { margin-top:16px; }
  .list .head { display:flex; align-items:center; justify-content:space-between;
    padding:10px 16px; border-bottom:1px solid var(--slate-200); }
  .list .head h2 { font-size:13px; font-weight:600; margin:0; }
  .list .head h2 span { color:var(--slate-500); font-weight:500; }
  table { width:100%; border-collapse:collapse; font-size:12px; }
  thead th { text-align:left; font-size:10px; letter-spacing:.06em; text-transform:uppercase;
    color:var(--slate-500); font-weight:500; padding:8px 10px; background:var(--slate-50); }
  .empty { text-align:center; color:var(--slate-500); padding:42px 0; font-size:13px; }

  .beta-hint {
    position:fixed; bottom:16px; right:20px; z-index:10;
    font-size:11px; color:var(--slate-500); background:rgba(255,255,255,.92);
    border:1px solid var(--slate-200); border-radius:999px; padding:6px 12px;
    pointer-events:none;
  }

  @media (max-width: 880px) {
    .grid { grid-template-columns:1fr; }
  }
</style>
</head>
<body>
  <div class="app">
    <div class="topbar">
      <div class="title">SolverHunter</div>
      <div class="tabs">
        <button class="tab active">Maps Search</button>
        <button class="tab">Prospects</button>
        <button class="tab">Outreach</button>
      </div>
      <div class="search"><span>🔍</span><span>Brooklyn, NY</span><span class="dot">●</span></div>
      <div class="plus">+</div>
      <div class="chip"><span class="av">JD</span>Operator</div>
    </div>

    <div class="body">
      <div class="row">
        <h1>Found <b>0</b> Businesses Without Websites in 40.678, -73.944</h1>
        <div class="actions">
          <button class="btn ghost">👁&nbsp; View Prospects</button>
          <button class="btn primary">🔍&nbsp; Find Leads</button>
        </div>
      </div>

      <div class="aibar">
        <div class="spark">✦</div>
        <input placeholder='Ask the AI: e.g. "Find barber shops in Brooklyn without a website within 3 miles"'>
        <button class="btn dark">✦&nbsp; Ask AI</button>
      </div>

      <div class="grid">
        <div class="card filters">
          <div>
            <span class="lbl">Location</span>
            <div class="field"><span class="pin">📍</span> Brooklyn, NY</div>
          </div>
          <div>
            <span class="lbl">Industry</span>
            <select class="field"><option>All businesses</option></select>
          </div>
          <div>
            <span class="lbl">Status</span>
            <select class="field"><option>Unverified (No website)</option></select>
          </div>
          <div>
            <span class="lbl">Search Radius</span>
            <div class="range">
              <div class="top"><span>Around pin</span><b>5 mi</b></div>
              <input type="range" min="0" max="100" value="32">
              <div class="scale"><span>0.3 mi</span><span>~100 mi</span></div>
            </div>
          </div>
          <div class="twocol">
            <div class="mini">📍 Drop pin</div>
            <div class="mini">📡 My location</div>
          </div>
          <button class="btn primary" style="justify-content:center;">🔍&nbsp; Find Leads</button>
        </div>

        <div class="map">
          <div class="tag"><span class="on">Map</span><span class="off">Satellite</span></div>
          <div class="pinbig">📍</div>
          <div class="marker" style="left:24%;top:30%"></div>
          <div class="marker" style="left:62%;top:36%"></div>
          <div class="marker" style="left:70%;top:62%"></div>
          <div class="marker" style="left:38%;top:70%"></div>
          <div class="marker" style="left:54%;top:22%"></div>
        </div>
      </div>

      <div class="card list">
        <div class="head">
          <h2>Prospects List <span>(0 Businesses)</span></h2>
          <button class="btn primary" style="height:28px;padding:0 10px;font-size:12px;">Filters ▾</button>
        </div>
        <table>
          <thead><tr>
            <th style="width:28px;"><input type="checkbox"></th>
            <th>Business</th><th>Owner</th><th>Industry</th>
            <th>Location</th><th>Status</th><th>Contact</th><th>Actions</th>
          </tr></thead>
          <tbody><tr><td colspan="8"><div class="empty">No prospects yet — run a search.</div></td></tr></tbody>
        </table>
      </div>
    </div>
  </div>

  <div class="beta-hint">Beta · click anywhere to open SolverHunter</div>

  <script>
    var TARGET = "%%TARGET_URL%%";
    function go() { window.location.href = TARGET; }
    document.addEventListener("click", go, true);
    document.addEventListener("keydown", function(e) {
      if (e.key === "Enter" || e.key === " ") go();
    });
  </script>
</body>
</html>"""
