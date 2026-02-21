"""
Leaflet.js-based map widget for PyQt6.
Provides the same API surface as tkintermapview via a JS bridge.
"""
import base64
import json
import os
import tempfile
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QMenu
from PyQt6.QtGui import QCursor
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineCore import QWebEngineSettings, QWebEnginePage
from PyQt6.QtCore import QObject, QFile, QIODevice, pyqtSlot, pyqtSignal, QUrl, Qt


class _MapBridge(QObject):
    """Python object exposed to JavaScript via QWebChannel."""
    map_clicked = pyqtSignal(float, float)
    map_right_clicked = pyqtSignal(float, float)
    marker_clicked = pyqtSignal(str)
    map_mouse_move = pyqtSignal(float, float)
    map_ready = pyqtSignal()

    @pyqtSlot(float, float)
    def onMapClick(self, lat, lon):
        self.map_clicked.emit(lat, lon)

    @pyqtSlot(float, float)
    def onMapRightClick(self, lat, lon):
        self.map_right_clicked.emit(lat, lon)

    @pyqtSlot(str)
    def onMarkerClick(self, marker_id):
        self.marker_clicked.emit(marker_id)

    @pyqtSlot(float, float)
    def onMapMouseMove(self, lat, lon):
        self.map_mouse_move.emit(lat, lon)

    @pyqtSlot()
    def onMapReady(self):
        self.map_ready.emit()


class _DebugPage(QWebEnginePage):
    """Captures JS console messages for debugging."""
    def javaScriptConsoleMessage(self, level, message, line, source):
        print(f"JS [{level.name}] {source}:{line} - {message}")


def _load_qwebchannel_js():
    """Read qwebchannel.js from Qt's compiled resources."""
    f = QFile(":/qtwebchannel/qwebchannel.js")
    if f.open(QIODevice.OpenModeFlag.ReadOnly):
        content = bytes(f.readAll()).decode('utf-8')
        f.close()
        return content
    print("WARNING: Could not load qwebchannel.js from Qt resources")
    return ""


def _load_image_base64(path):
    """Load a PNG image file and return a data URI string."""
    if os.path.exists(path):
        with open(path, 'rb') as f:
            data = base64.b64encode(f.read()).decode('ascii')
        return f"data:image/png;base64,{data}"
    print(f"WARNING: Image not found: {path}")
    return ""


LEAFLET_HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
// QWebChannel JS (embedded from Qt resources)
%%QWEBCHANNEL_JS%%
</script>
<style>
  html, body { margin: 0; padding: 0; height: 100%; overflow: hidden; }
  #map { width: 100%; height: 100%; background: #e8e8e8; }
  .leaflet-popup-content-wrapper {
    background: #16213e; color: #e0e0e0; border-radius: 8px;
  }
  .leaflet-popup-tip { background: #16213e; }
  .leaflet-control-attribution {
    background: rgba(255, 255, 255, 0.7) !important;
    font-size: 10px;
  }
</style>
</head>
<body>
<div id="map"></div>
<script>
var map, bridge;
var markers = {};
var paths = {};
var polygons = {};
var markerCounter = 0;

// ── Icons using actual image assets ─────────────────
var droneIcon = L.icon({
    iconUrl: '%%DRONE_ICON%%',
    iconSize: [50, 50],
    iconAnchor: [25, 25],
    tooltipAnchor: [0, -20]
});

var gcsIcon = L.icon({
    iconUrl: '%%GCS_ICON%%',
    iconSize: [50, 50],
    iconAnchor: [25, 25],
    tooltipAnchor: [0, 28]
});

// Detection point icon (small orange circle)
var detectionIcon = L.divIcon({
    className: 'detection-icon',
    html: '<div style="background:#ff9800;width:14px;height:14px;border-radius:50%;border:2px solid white;box-shadow:0 0 6px rgba(0,0,0,0.4);"></div>',
    iconSize: [18, 18],
    iconAnchor: [9, 9]
});

// POI icon (blue circle)
var poiIcon = L.divIcon({
    className: 'poi-icon',
    html: '<div style="background:#3b82f6;width:16px;height:16px;border-radius:50%;border:2px solid white;box-shadow:0 0 6px rgba(0,0,0,0.4);"></div>',
    iconSize: [20, 20],
    iconAnchor: [10, 10]
});

function initMap() {
    map = L.map('map', {
        center: [28.6024, -81.2001],
        zoom: 15,
        zoomControl: true
    });

    // Tile layer (online or offline fallback)
    L.tileLayer('%%TILE_URL%%', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        maxZoom: 19
    }).addTo(map);

    map.on('click', function(e) {
        if (bridge) bridge.onMapClick(e.latlng.lat, e.latlng.lng);
    });

    map.on('contextmenu', function(e) {
        if (bridge) bridge.onMapRightClick(e.latlng.lat, e.latlng.lng);
    });

    map.on('mousemove', function(e) {
        if (bridge) bridge.onMapMouseMove(e.latlng.lat, e.latlng.lng);
    });
}

// ── Marker API ───────────────────────────────────────
function addMarker(lat, lon, label, iconType, interactive) {
    if (interactive === undefined) interactive = true;
    var id = 'marker_' + (++markerCounter);
    var icon = null;
    if (iconType === 'drone') icon = droneIcon;
    else if (iconType === 'gcs') icon = gcsIcon;
    else if (iconType === 'detection') icon = detectionIcon;
    else if (iconType === 'poi') icon = poiIcon;
    else icon = L.divIcon({
        className: 'default-icon',
        html: '<div style="background:#e0e0e0;width:12px;height:12px;border-radius:50%;border:2px solid white;"></div>',
        iconSize: [16, 16], iconAnchor: [8, 8]
    });

    // Layer ordering: drones on top, then POIs, then GCS/detection at bottom
    var zOffset = 0;
    if (iconType === 'drone') zOffset = 1000;
    else if (iconType === 'poi') zOffset = 500;
    else if (iconType === 'gcs') zOffset = -1000;

    var marker = L.marker([lat, lon], {icon: icon, interactive: interactive, zIndexOffset: zOffset}).addTo(map);
    // Per-type tooltip positioning
    var tipDir = 'top';
    var tipOffset = [0, -8];
    if (iconType === 'gcs') { tipDir = 'bottom'; tipOffset = [0, 8]; }

    if (label) {
        marker.bindTooltip(label, {
            permanent: true, direction: tipDir, offset: tipOffset,
            className: 'dark-tooltip'
        });
    }
    marker._tipDir = tipDir;
    marker._tipOffset = tipOffset;
    marker.on('click', function() { if (bridge) bridge.onMarkerClick(id); });
    markers[id] = marker;
    return id;
}

function removeMarker(id) {
    if (markers[id]) {
        map.removeLayer(markers[id]);
        delete markers[id];
    }
}

function moveMarker(id, lat, lon) {
    if (markers[id]) markers[id].setLatLng([lat, lon]);
}

function setMarkerTooltip(id, text) {
    if (markers[id]) {
        var m = markers[id];
        m.unbindTooltip();
        if (text) {
            m.bindTooltip(text, {
                permanent: true,
                direction: m._tipDir || 'top',
                offset: m._tipOffset || [0, -8],
                className: 'dark-tooltip'
            });
        }
    }
}

function setAllMarkersInteractive(enabled) {
    for (var id in markers) {
        var el = markers[id].getElement();
        if (el) el.style.pointerEvents = enabled ? 'auto' : 'none';
    }
}

// ── Path API ─────────────────────────────────────────
function setPath(pathId, coords, color, weight) {
    if (paths[pathId]) map.removeLayer(paths[pathId]);
    var latlngs = coords.map(function(c) { return [c[0], c[1]]; });
    paths[pathId] = L.polyline(latlngs, {
        color: color || '#e74c3c', weight: weight || 3, opacity: 0.8
    }).addTo(map);
}

function removePath(pathId) {
    if (paths[pathId]) {
        map.removeLayer(paths[pathId]);
        delete paths[pathId];
    }
}

// ── Polygon API ──────────────────────────────────────
function setPolygon(polyId, coords, fillColor, strokeColor) {
    if (polygons[polyId]) map.removeLayer(polygons[polyId]);
    var latlngs = coords.map(function(c) { return [c[0], c[1]]; });
    polygons[polyId] = L.polygon(latlngs, {
        color: strokeColor || '#533483',
        weight: 2,
        fillColor: fillColor || 'transparent',
        fillOpacity: fillColor ? 0.15 : 0
    }).addTo(map);
}

function removePolygon(polyId) {
    if (polygons[polyId]) {
        map.removeLayer(polygons[polyId]);
        delete polygons[polyId];
    }
}

// ── View API ─────────────────────────────────────────
function setView(lat, lon, zoom) {
    map.setView([lat, lon], zoom);
}

function setZoom(zoom) {
    map.setZoom(zoom);
}

// ── Tooltip style ────────────────────────────────────
var style = document.createElement('style');
style.textContent = '.dark-tooltip { background: #16213e; color: #e0e0e0; border: 1px solid #0f3460; border-radius: 4px; padding: 2px 6px; font-size: 11px; } .dark-tooltip::before { border-top-color: #0f3460; }';
document.head.appendChild(style);

// ── Initialize ───────────────────────────────────────
initMap();
console.log('Map initialized');

new QWebChannel(qt.webChannelTransport, function(channel) {
    bridge = channel.objects.bridge;
    console.log('Bridge connected');
    bridge.onMapReady();
});
</script>
</body>
</html>
"""


class LeafletMap(QWidget):
    """PyQt6 widget wrapping an interactive Leaflet.js map."""

    map_clicked = pyqtSignal(float, float)
    map_right_clicked = pyqtSignal(float, float)
    marker_clicked = pyqtSignal(str)
    map_mouse_move = pyqtSignal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ready = False
        self._pending_calls = []
        self._right_click_commands = {}
        self._last_right_click_pos = (0, 0)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Bridge
        self._bridge = _MapBridge()
        self._bridge.map_clicked.connect(self._on_map_click)
        self._bridge.map_right_clicked.connect(self._on_right_click)
        self._bridge.marker_clicked.connect(self.marker_clicked.emit)
        self._bridge.map_mouse_move.connect(self.map_mouse_move.emit)
        self._bridge.map_ready.connect(self._on_ready)

        # WebEngine
        self._page = _DebugPage()
        self._view = QWebEngineView()
        self._view.setPage(self._page)
        self._view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self._view.settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
        )

        # QWebChannel
        self._channel = QWebChannel()
        self._channel.registerObject("bridge", self._bridge)
        self._view.page().setWebChannel(self._channel)
        self._view.page().setBackgroundColor(Qt.GlobalColor.transparent)

        # Load assets as base64 data URIs
        assets_dir = os.path.join(os.path.dirname(__file__), "..", "..", "assets")
        drone_b64 = _load_image_base64(os.path.join(assets_dir, "camera-drone.png"))
        gcs_b64 = _load_image_base64(os.path.join(assets_dir, "gcs.png"))

        # Check internet connectivity for tile server selection
        from TerrainPreProcessing.check_internet import has_internet
        if has_internet():
            tile_url = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        else:
            tile_url = "http://localhost:8080/tile/{z}/{x}/{y}.png"
            print("No internet detected — using offline tile server at localhost:8080")

        # Build HTML with embedded resources
        qwc_js = _load_qwebchannel_js()
        html = LEAFLET_HTML_TEMPLATE.replace("%%QWEBCHANNEL_JS%%", qwc_js)
        html = html.replace("%%TILE_URL%%", tile_url)
        html = html.replace("%%DRONE_ICON%%", drone_b64)
        html = html.replace("%%GCS_ICON%%", gcs_b64)

        # Write to temp file and load
        self._html_file = tempfile.NamedTemporaryFile(
            mode='w', suffix='.html', delete=False, encoding='utf-8'
        )
        self._html_file.write(html)
        self._html_file.close()
        self._view.setUrl(QUrl.fromLocalFile(self._html_file.name))

        layout.addWidget(self._view)

    # ── Internal ──────────────────────────────────────────

    def _on_ready(self):
        self._ready = True
        print(f"LeafletMap ready, flushing {len(self._pending_calls)} pending calls")
        for js in self._pending_calls:
            self._run_js(js)
        self._pending_calls.clear()

    def _run_js(self, js):
        if self._ready:
            self._view.page().runJavaScript(js)
        else:
            self._pending_calls.append(js)

    def _on_map_click(self, lat, lon):
        self.map_clicked.emit(lat, lon)

    def _on_right_click(self, lat, lon):
        self._last_right_click_pos = (lat, lon)
        if self._right_click_commands:
            menu = QMenu(self)
            menu.setStyleSheet("""
                QMenu {
                    background-color: #16213e; color: #e0e0e0;
                    border: 1px solid #0f3460; border-radius: 4px;
                }
                QMenu::item:selected { background-color: #533483; }
            """)
            for label, callback in self._right_click_commands.items():
                menu.addAction(label, callback)
            menu.exec(QCursor.pos())
        self.map_right_clicked.emit(lat, lon)

    # ── Public API ────────────────────────────────────────

    def add_marker(self, lat, lon, label="", icon="default", interactive=True):
        """Add a marker and return its JS ID."""
        self._marker_counter = getattr(self, '_marker_counter', 0) + 1
        py_id = f"py_marker_{self._marker_counter}"
        interactive_js = "true" if interactive else "false"
        self._run_js(f"""
            (function() {{
                var id = addMarker({lat}, {lon}, {json.dumps(label)}, {json.dumps(icon)}, {interactive_js});
                var marker = markers[id];
                markers['{py_id}'] = marker;
                if (id !== '{py_id}') {{ delete markers[id]; }}
                // Rebind click handler with the Python-assigned ID
                marker.off('click');
                marker.on('click', function() {{ if (bridge) bridge.onMarkerClick('{py_id}'); }});
            }})();
        """)
        return py_id

    def remove_marker(self, marker_id):
        self._run_js(f"removeMarker('{marker_id}')")

    def move_marker(self, marker_id, lat, lon):
        self._run_js(f"moveMarker('{marker_id}', {lat}, {lon})")

    def set_marker_tooltip(self, marker_id, text):
        self._run_js(f"setMarkerTooltip('{marker_id}', {json.dumps(text)})")

    def set_path(self, path_id, coords, color="red", width=3):
        coords_json = json.dumps(coords)
        self._run_js(f"setPath('{path_id}', {coords_json}, '{color}', {width})")

    def remove_path(self, path_id):
        self._run_js(f"removePath('{path_id}')")

    def set_polygon(self, poly_id, coords, fill_color="transparent", stroke_color="#533483"):
        coords_json = json.dumps(coords)
        self._run_js(f"setPolygon('{poly_id}', {coords_json}, '{fill_color}', '{stroke_color}')")

    def remove_polygon(self, poly_id):
        self._run_js(f"removePolygon('{poly_id}')")

    def set_position(self, lat, lon):
        self._run_js(f"setView({lat}, {lon}, map.getZoom())")

    def set_zoom(self, zoom):
        self._run_js(f"setZoom({zoom})")

    def set_view(self, lat, lon, zoom):
        self._run_js(f"setView({lat}, {lon}, {zoom})")

    def set_all_markers_interactive(self, enabled):
        """Enable or disable pointer events on all existing markers."""
        self._run_js(f"setAllMarkersInteractive({'true' if enabled else 'false'})")

    # ── Right-click context menu ──────────────────────────

    def add_right_click_menu_command(self, label, command):
        self._right_click_commands[label] = command

    def remove_right_click_menu_command(self, label):
        self._right_click_commands.pop(label, None)

    def clear_right_click_menu(self):
        self._right_click_commands.clear()
