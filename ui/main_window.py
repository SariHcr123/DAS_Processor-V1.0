import sys
import os
import json
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from matplotlib.widgets import SpanSelector, RectangleSelector
from matplotlib.patches import Rectangle
from scipy.fftpack import fft, fftshift, fft2, ifftshift
from scipy import signal

from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

from core.processor import DataProcessor
from ui.node_editor.editor import NodeEditorWidget
from ui.inversion_dialog import VelocityInversionDialog

class TDMSLoaderThread(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(object, object) # result, error
    
    def __init__(self, processor, path):
        super().__init__()
        self.processor = processor
        self.path = path
        
    def run(self):
        try:
            def cb(p):
                self.progress.emit(p)
                
            res = self.processor.load_tdms(self.path, progress_callback=cb)
            self.finished.emit(res, None)
        except Exception as e:
            self.finished.emit(None, e)

class PlotView(QWidget):
    clicked = pyqtSignal(int) # Emits view index when clicked

    def __init__(self, index, title, parent=None):
        super().__init__(parent)
        self.index = index
        self.title = title
        self.figure = Figure(figsize=(4, 3), dpi=100)
        self.canvas = FigureCanvas(self.figure)
        self.toolbar = NavigationToolbar(self.canvas, self)
        self.toolbar.hide() # Hidden by default
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)
        
        self.interaction_connected = False
        
        # Connect click event
        self.canvas.mpl_connect('button_press_event', self.on_click)
        
    def on_click(self, event):
        if event.inaxes is not None:
             self.clicked.emit(self.index)
             
    def clear(self):
        self.figure.clear()
        
    def draw(self):
        self.canvas.draw()

class SettingsDialog(QDialog):
    def __init__(self, current_params, parent=None):
        super().__init__(parent)
        self.params = current_params.copy()
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle("Settings")
        self.setWindowIcon(self.parent().windowIcon())
        self.resize(300, 200)
        
        layout = QVBoxLayout(self)
        form = QFormLayout()
        
        # Channel Spacing (dx)
        self.spin_dx = QDoubleSpinBox()
        self.spin_dx.setRange(0.01, 1000.0)
        self.spin_dx.setDecimals(2)
        self.spin_dx.setValue(self.params.get('dx', 4.0))
        self.spin_dx.setSuffix(" m")
        form.addRow("Channel Spacing (道间距):", self.spin_dx)
        
        # Sampling Frequency (fs) -> stored as dt = 1/fs
        self.spin_fs = QDoubleSpinBox()
        self.spin_fs.setRange(0.001, 100000.0)
        self.spin_fs.setDecimals(3)
        dt = self.params.get('dt', 0.1)
        fs = 1.0 / dt if dt > 0 else 10.0
        self.spin_fs.setValue(fs)
        self.spin_fs.setSuffix(" Hz")
        form.addRow("Sampling Rate (采样率):", self.spin_fs)
        
        # Gauge Length (gl)
        self.spin_gl = QDoubleSpinBox()
        self.spin_gl.setRange(0.1, 1000.0)
        self.spin_gl.setDecimals(2)
        self.spin_gl.setValue(self.params.get('gl', 10.0))
        self.spin_gl.setSuffix(" m")
        form.addRow("Gauge Length (标距):", self.spin_gl)
        
        layout.addLayout(form)
        
        # Buttons
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)
        
    def get_params(self):
        fs = self.spin_fs.value()
        return {
            'dx': self.spin_dx.value(),
            'dt': 1.0 / fs if fs > 0 else 0.1,
            'gl': self.spin_gl.value()
        }

class CrossCorrelationDialog(QDialog):
    def __init__(self, n_channels, total_duration, initial_params=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cross Correlation Analysis")
        self.n_channels = n_channels
        self.total_duration = total_duration
        self.initial_params = initial_params or {}
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()
        
        self.spin_ref = QSpinBox()
        self.spin_ref.setRange(0, self.n_channels - 1)
        ref_default = self.initial_params.get('ref_ch', self.n_channels // 2)
        if ref_default >= self.n_channels:
            ref_default = self.n_channels // 2
        self.spin_ref.setValue(ref_default)
        form.addRow("Reference Channel (参考道):", self.spin_ref)
        
        self.spin_max_lag = QDoubleSpinBox()
        self.spin_max_lag.setRange(0.01, self.total_duration / 2)
        self.spin_max_lag.setValue(self.initial_params.get('max_lag', 1.0))
        self.spin_max_lag.setSuffix(" s")
        form.addRow("Max Lag (最大时延):", self.spin_max_lag)
        
        self.spin_window = QDoubleSpinBox()
        self.spin_window.setRange(0.0, self.total_duration)
        self.spin_window.setValue(self.initial_params.get('window', 0.0))
        self.spin_window.setSuffix(" s")
        self.spin_window.setSpecialValueText("Full Duration (全长)")
        form.addRow("Stacking Window (叠加窗口):", self.spin_window)
        
        layout.addLayout(form)
        
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)
        
    def get_params(self):
        return {
            'ref_ch': self.spin_ref.value(),
            'max_lag': self.spin_max_lag.value(),
            'window': self.spin_window.value()
        }

class DispersionDialog(QDialog):
    def __init__(self, processor, initial_params=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dispersion Analysis")
        self.processor = processor
        self.initial_params = initial_params or {}
        self.resize(800, 600)
        self.result_data = None
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Controls
        ctrl_layout = QHBoxLayout()
        
        self.spin_vmin = QDoubleSpinBox()
        self.spin_vmin.setRange(10, 5000)
        self.spin_vmin.setValue(self.initial_params.get('vmin', 100.0))
        self.spin_vmin.setPrefix("Vmin: ")
        
        self.spin_vmax = QDoubleSpinBox()
        self.spin_vmax.setRange(10, 10000)
        self.spin_vmax.setValue(self.initial_params.get('vmax', 2000.0))
        self.spin_vmax.setPrefix("Vmax: ")
        
        self.spin_fmin = QDoubleSpinBox()
        self.spin_fmin.setRange(0.1, 1000)
        self.spin_fmin.setValue(self.initial_params.get('fmin', 1.0))
        self.spin_fmin.setPrefix("Fmin: ")
        
        self.spin_fmax = QDoubleSpinBox()
        self.spin_fmax.setRange(0.1, 5000)
        self.spin_fmax.setValue(self.initial_params.get('fmax', 100.0))
        self.spin_fmax.setPrefix("Fmax: ")
        
        btn_compute = QPushButton("Compute")
        btn_compute.clicked.connect(self.compute)
        
        btn_save = QPushButton("Save Curve")
        btn_save.clicked.connect(self.save_curve)
        
        # Add Close/Apply buttons to persist settings even if just closing?
        # Actually QDialog has accept/reject. 
        # Let's add standard buttons to allow "OK" to save settings
        self.btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Close)
        self.btn_box.accepted.connect(self.accept)
        self.btn_box.rejected.connect(self.reject)
        
        ctrl_layout.addWidget(self.spin_vmin)
        ctrl_layout.addWidget(self.spin_vmax)
        ctrl_layout.addWidget(self.spin_fmin)
        ctrl_layout.addWidget(self.spin_fmax)
        ctrl_layout.addWidget(btn_compute)
        ctrl_layout.addWidget(btn_save)
        
        layout.addLayout(ctrl_layout)
        
        # Plot
        self.figure = Figure(figsize=(8, 6), dpi=100)
        self.canvas = FigureCanvas(self.figure)
        self.toolbar = NavigationToolbar(self.canvas, self)
        
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)
        layout.addWidget(self.btn_box)
        
        self.f_axis = None
        self.v_curve = None
        
    def get_params(self):
        return {
            'vmin': self.spin_vmin.value(),
            'vmax': self.spin_vmax.value(),
            'fmin': self.spin_fmin.value(),
            'fmax': self.spin_fmax.value()
        }
        
    def compute(self):
        data = self.processor.processed_data
        if data is None:
            QMessageBox.warning(self, "Error", "No data loaded")
            return
            
        vmin = self.spin_vmin.value()
        vmax = self.spin_vmax.value()
        fmin = self.spin_fmin.value()
        fmax = self.spin_fmax.value()
        
        try:
            f, v, img, curve = self.processor.compute_dispersion(
                data, v_min=vmin, v_max=vmax, v_step=10.0, f_min=fmin, f_max=fmax
            )
            
            if f is None:
                QMessageBox.warning(self, "Error", "Computation failed (check params)")
                return
                
            self.f_axis = f
            self.v_curve = curve
            self.result_data = (f, v, img, curve)
            
            self.figure.clear()
            ax = self.figure.add_subplot(111)
            
            # Plot Image
            # Extent: [fmin, fmax, vmin, vmax]
            # Origin lower
            extent = [f[0], f[-1], v[0], v[-1]]
            im = ax.imshow(img, aspect='auto', cmap='jet', origin='lower', extent=extent)
            self.figure.colorbar(im, ax=ax, label='Energy')
            
            # Plot Curve
            ax.plot(f, curve, 'r-', linewidth=2, label='Extracted Curve')
            
            ax.set_xlabel("Frequency (Hz)")
            ax.set_ylabel("Phase Velocity (m/s)")
            ax.set_title("Dispersion Image")
            ax.legend()
            
            self.canvas.draw()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            import traceback
            traceback.print_exc()
            
    def save_curve(self):
        if self.f_axis is None or self.v_curve is None:
            return
            
        path, _ = QFileDialog.getSaveFileName(self, "Save Curve", "", "CSV Files (*.csv)")
        if path:
            try:
                data = np.column_stack((self.f_axis, self.v_curve))
                np.savetxt(path, data, delimiter=',', header='Frequency(Hz),Velocity(m/s)', comments='')
                QMessageBox.information(self, "Success", "Saved successfully")
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

class BeamformingDialog(QDialog):
    def __init__(self, processor, initial_params=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Beamforming Analysis")
        self.processor = processor
        self.initial_params = initial_params or {}
        self.resize(800, 600)
        self.result_data = None
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Controls
        ctrl_layout = QFormLayout()
        
        self.spin_angle_min = QDoubleSpinBox()
        self.spin_angle_min.setRange(-180, 180)
        self.spin_angle_min.setValue(self.initial_params.get('angle_min', -90.0))
        
        self.spin_angle_max = QDoubleSpinBox()
        self.spin_angle_max.setRange(-180, 180)
        self.spin_angle_max.setValue(self.initial_params.get('angle_max', 90.0))
        
        self.spin_fmin = QDoubleSpinBox()
        self.spin_fmin.setRange(0.1, 1000)
        self.spin_fmin.setValue(self.initial_params.get('fmin', 1.0))
        
        self.spin_fmax = QDoubleSpinBox()
        self.spin_fmax.setRange(0.1, 5000)
        self.spin_fmax.setValue(self.initial_params.get('fmax', 100.0))
        
        self.spin_vsound = QDoubleSpinBox()
        self.spin_vsound.setRange(100, 5000)
        self.spin_vsound.setValue(self.initial_params.get('v_sound', 1500.0))
        
        self.spin_window = QDoubleSpinBox()
        self.spin_window.setRange(0.01, 1000)
        self.spin_window.setValue(self.initial_params.get('window_sec', 1.0))
        
        self.spin_step = QDoubleSpinBox()
        self.spin_step.setRange(0.01, 1000)
        self.spin_step.setValue(self.initial_params.get('step_sec', 0.5))
        
        ctrl_layout.addRow("Angle Min (deg):", self.spin_angle_min)
        ctrl_layout.addRow("Angle Max (deg):", self.spin_angle_max)
        ctrl_layout.addRow("Freq Min (Hz):", self.spin_fmin)
        ctrl_layout.addRow("Freq Max (Hz):", self.spin_fmax)
        ctrl_layout.addRow("Sound Velocity (m/s):", self.spin_vsound)
        ctrl_layout.addRow("Window Size (s):", self.spin_window)
        ctrl_layout.addRow("Step Size (s):", self.spin_step)
        
        btn_compute = QPushButton("Compute")
        btn_compute.clicked.connect(self.compute)
        
        self.btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Close)
        self.btn_box.accepted.connect(self.accept)
        self.btn_box.rejected.connect(self.reject)
        
        layout.addLayout(ctrl_layout)
        layout.addWidget(btn_compute)
        
        # Plot
        self.figure = Figure(figsize=(8, 6), dpi=100)
        self.canvas = FigureCanvas(self.figure)
        self.toolbar = NavigationToolbar(self.canvas, self)
        
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)
        layout.addWidget(self.btn_box)
        
    def get_params(self):
        return {
            'angle_min': self.spin_angle_min.value(),
            'angle_max': self.spin_angle_max.value(),
            'fmin': self.spin_fmin.value(),
            'fmax': self.spin_fmax.value(),
            'v_sound': self.spin_vsound.value(),
            'window_sec': self.spin_window.value(),
            'step_sec': self.spin_step.value()
        }
        
    def compute(self):
        data = self.processor.processed_data
        if data is None:
            QMessageBox.warning(self, "Error", "No data loaded")
            return
            
        params = self.get_params()
        
        try:
            t_axis, angles, energy_map = self.processor.compute_beamforming(
                data, 
                params['angle_min'], params['angle_max'], 1.0,
                params['fmin'], params['fmax'],
                params['v_sound'],
                params['window_sec'], params['step_sec']
            )
            
            if t_axis is None:
                QMessageBox.warning(self, "Error", "Computation failed")
                return
                
            self.result_data = (t_axis, angles, energy_map)
            
            self.figure.clear()
            ax = self.figure.add_subplot(111)
            
            # Angle-Time Plot
            # X: Angle, Y: Time
            # extent=[angle_min, angle_max, time_min, time_max]
            # Origin lower? Time usually increases downwards or upwards?
            # User asked for Time as vertical. Usually time starts from 0 at top?
            # Let's put 0 at top (origin='upper') if we want waterfall style.
            # But standard plot 0 is bottom.
            # Let's assume standard t axis increasing upwards for now, or match user preference.
            # "Target localization azimuth map... horizontal is angle, vertical is time"
            
            extent = [angles[0], angles[-1], t_axis[0], t_axis[-1]]
            
            im = ax.imshow(energy_map, aspect='auto', cmap='jet', origin='lower', extent=extent)
            self.figure.colorbar(im, ax=ax, label='Normalized Energy')
            
            ax.set_xlabel("Angle (deg)")
            ax.set_ylabel("Time (s)")
            ax.set_title(f"Beamforming (Angle-Time) {params['fmin']}-{params['fmax']} Hz")
            
            self.canvas.draw()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            import traceback
            traceback.print_exc()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.processor = DataProcessor()
        self.pipeline_state = None
        
        # Default Parameters
        self.default_params = {
            'dx': 4.0, 'dt': 0.1, 'gl': 10.0,
            'ch_start': 0, 'ch_end': 1000,
            'time_start': 0, 'time_end': 1000,
            'K': 4, 'alpha': 2000,
            'ccf_max_lag': 1.0,
            'ccf_window': 0.0,
            'ccf_ref_ch': 0,
            'disp_vmin': 100.0, 'disp_vmax': 2000.0,
            'disp_fmin': 1.0, 'disp_fmax': 100.0,
            'bf_angle_min': -90.0, 'bf_angle_max': 90.0,
            'bf_fmin': 1.0, 'bf_fmax': 100.0,
            'bf_v_sound': 1500.0,
            'bf_window': 1.0, 'bf_step': 0.5
        }
        
        # Load Settings
        self.config_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config.json')
        self.load_settings()

        # Apply settings to processor
        self.processor.base_dx = self.default_params.get('dx', 4.0)
        self.processor.base_dt = self.default_params.get('dt', 0.1)
        self.processor.dx = self.processor.base_dx
        self.processor.dt = self.processor.base_dt
        self.processor.gauge_length = self.default_params.get('gl', 10.0)
        
        self.views = []
        self.active_view_idx = 0
        self.dispersion_result = None
        self.beamforming_result = None
        self.velocity_result = None
        self.clim = None
        self.span_selector = None
        self.hist_ax = None
        self.data_ax = None
        self.fk_text = None
        
        # Playback & Selection
        self.rect_selector = None
        self.play_timer = QTimer()
        self.play_timer.timeout.connect(self.advance_playback)
        self.play_interval = 50 # ms
        self.playback_range = None # (start_idx, end_idx)
        self.playback_active = False
        
        # Dispersion View State (0: Raw, 1: Raw+Curve, 2: Smooth+Curve, 3: Smooth, 4: Back to 0)
        self.dispersion_view_mode = 0
        
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle("DAS Processor")
        self.resize(1200, 800)
        
        # Toolbar
        toolbar = QToolBar()
        self.addToolBar(toolbar)
        
        action_load = QAction("Load Image", self)
        action_load.triggered.connect(self.load_image)
        toolbar.addAction(action_load)
        
        action_load_tdms = QAction("Load TDMS", self)
        action_load_tdms.triggered.connect(self.load_tdms)
        toolbar.addAction(action_load_tdms)
        
        toolbar.addSeparator()
        
        action_editor = QAction("Pipeline Editor", self)
        action_editor.triggered.connect(self.open_editor)
        toolbar.addAction(action_editor)

        toolbar.addSeparator()

        action_settings = QAction("Settings", self)
        action_settings.triggered.connect(self.open_settings)
        toolbar.addAction(action_settings)
        
        toolbar.addSeparator()
        
        action_ccf = QAction("Cross Correlation", self)
        action_ccf.triggered.connect(self.open_ccf_dialog)
        toolbar.addAction(action_ccf)
        
        action_disp = QAction("Dispersion", self)
        action_disp.triggered.connect(self.open_dispersion_dialog)
        toolbar.addAction(action_disp)
        
        action_beam = QAction("Beamforming", self)
        action_beam.triggered.connect(self.open_beamforming_dialog)
        toolbar.addAction(action_beam)
        
        action_vel = QAction("Velocity Analysis", self)
        action_vel.triggered.connect(self.open_velocity_dialog)
        toolbar.addAction(action_vel)
        
        # Main Layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        
        # Splitter
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)
        
        # --- Left Panel: Controls (Placeholder for future controls) ---
        self.left_panel = QWidget()
        self.left_layout = QVBoxLayout(self.left_panel)
        # self.left_panel.setFixedWidth(300) # Optional: Set fixed width if needed
        
        # Placeholder for other controls (e.g. Node Editor Properties, Filter settings)
        # For now, we leave it empty or add a label as the user only asked to revert Data Loading UI
        self.left_layout.addStretch()
        
        splitter.addWidget(self.left_panel)
        
        # --- Right Panel: Plots ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        splitter.addWidget(right_panel)
        
        # Data Mode Selector
        view_ctrl_layout = QHBoxLayout()
        view_ctrl_layout.addWidget(QLabel("Data Mode:"))
        self.combo_view = QComboBox()
        self.combo_view.addItem("Processed Data")
        self.combo_view.addItem("Cross Correlation")
        self.combo_view.currentTextChanged.connect(self.on_view_change)
        view_ctrl_layout.addWidget(self.combo_view)
        
        # Analysis Mode Selector
        view_ctrl_layout.addWidget(QLabel("Analysis:"))
        self.combo_analysis = QComboBox()
        self.combo_analysis.addItem("Standard View")
        self.combo_analysis.addItem("Dispersion Analysis")
        self.combo_analysis.addItem("Beamforming")
        self.combo_analysis.addItem("Velocity Analysis")
        self.combo_analysis.currentTextChanged.connect(self.on_analysis_change)
        view_ctrl_layout.addWidget(self.combo_analysis)
        
        view_ctrl_layout.addStretch()
        right_layout.addLayout(view_ctrl_layout)
        
        # Top Panel: Thumbnails
        self.top_panel = QWidget()
        self.top_layout = QHBoxLayout(self.top_panel)
        self.top_panel.setFixedHeight(200)
        right_layout.addWidget(self.top_panel)
        
        # Bottom Panel: Active View
        self.bottom_panel = QWidget()
        self.bottom_layout = QVBoxLayout(self.bottom_panel)
        right_layout.addWidget(self.bottom_panel)
        
        # Initialize Views
        view_titles = ["Space-Time", "Time-Frequency", "Spectrum", "FK Spectrum"]
        self.views = []
        for i, title in enumerate(view_titles):
            view = PlotView(i, title)
            view.clicked.connect(self.on_view_clicked)
            self.views.append(view)
            
        self.update_view_layout()
        
        # Set splitter proportions (1:2)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        
        # Node Editor Widget (Persistent)
        self.editor_widget = NodeEditorWidget()
        self.editor_widget.pipeline_changed.connect(self.run_pipeline)
        self.editor_widget.state_changed.connect(self.save_pipeline_state)
        self.editor_window = None

        # Status Bar
        self.status_bar = self.statusBar()
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(300)
        self.progress_bar.setVisible(False)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setVisible(False)
        
        self.status_bar.addPermanentWidget(self.progress_bar)
        self.status_bar.addPermanentWidget(self.cancel_btn)

        # Set Application Icon
        self.setWindowIcon(self.create_app_icon())

    def create_app_icon(self):
        """Creates a programmatic VMD-themed icon."""
        size = 128
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Background circle
        painter.setBrush(QBrush(QColor("#2d2d2d")))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(0, 0, size, size)
        
        # Draw stylized waves (VMD modes)
        center_y = size / 2
        width = size
        
        # Mode 1: Low frequency (Cyan)
        path1 = QPainterPath()
        path1.moveTo(0, center_y)
        for x in range(width + 1):
            y = center_y + 20 * np.sin(x * 0.05)
            path1.lineTo(x, y)
        
        painter.setPen(QPen(QColor("#00FFFF"), 4))
        painter.drawPath(path1)
        
        # Mode 2: High frequency (Magenta)
        path2 = QPainterPath()
        path2.moveTo(0, center_y)
        for x in range(width + 1):
            y = center_y + 15 * np.sin(x * 0.15)
            path2.lineTo(x, y)
            
        painter.setPen(QPen(QColor("#FF00FF"), 3))
        painter.drawPath(path2)
        
        # Mode 3: Envelope/Trend (Yellow dashed)
        path3 = QPainterPath()
        path3.moveTo(0, center_y)
        for x in range(width + 1):
            y = center_y + 30 * np.sin(x * 0.02 + 1.0)
            path3.lineTo(x, y)
            
        painter.setPen(QPen(QColor("#FFFF00"), 2, Qt.DashLine))
        painter.drawPath(path3)
        
        painter.end()
        return QIcon(pixmap)

    def load_settings(self):
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    saved_params = json.load(f)
                    self.default_params.update(saved_params)
            else:
                # If config file doesn't exist, use default values
                pass
        except Exception as e:
            print(f"Error loading settings: {e}")

    def save_settings(self):
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            with open(self.config_file, 'w') as f:
                json.dump(self.default_params, f, indent=4)
        except Exception as e:
            print(f"Error saving settings: {e}")

    def update_view_layout(self):
        # Clear layouts (detach widgets)
        for i in reversed(range(self.top_layout.count())):
            item = self.top_layout.itemAt(i)
            if item.widget():
                item.widget().setParent(None)
                
        for i in reversed(range(self.bottom_layout.count())):
            item = self.bottom_layout.itemAt(i)
            if item.widget():
                item.widget().setParent(None)
                
        # Add Active View to Bottom
        active_view = self.views[self.active_view_idx]
        active_view.show()
        self.bottom_layout.addWidget(active_view)
        active_view.toolbar.show()
        
        # Connect interaction if not already
        if not active_view.interaction_connected:
             active_view.canvas.mpl_connect('button_press_event', self.on_active_view_interact)
             active_view.interaction_connected = True
             
        # Add Others to Top
        for i, view in enumerate(self.views):
            if i != self.active_view_idx:
                self.top_layout.addWidget(view)
                view.show()
                view.toolbar.hide()

    def on_view_clicked(self, index):
        if index != self.active_view_idx:
            self.active_view_idx = index
            self.update_view_layout()
            self.plot_all_views()

    def on_view_change(self, text):
        self.plot_all_views()
        
    def on_analysis_change(self, text):
        self.plot_all_views()

    def open_ccf_dialog(self):
        data = self.processor.processed_data
        if data is None:
            QMessageBox.warning(self, "Warning", "No data loaded!")
            return
            
        rows, cols = data.shape
        dt = self.processor.dt if self.processor.dt > 0 else 1.0
        total_duration = cols * dt
        
        # Prepare initial params
        initial_params = {
            'ref_ch': self.default_params.get('ccf_ref_ch', rows // 2),
            'max_lag': self.default_params.get('ccf_max_lag', 1.0),
            'window': self.default_params.get('ccf_window', 0.0)
        }
        
        dlg = CrossCorrelationDialog(rows, total_duration, initial_params, self)
        if dlg.exec_() == QDialog.Accepted:
            params = dlg.get_params()
            
            # Save to default_params
            self.default_params['ccf_ref_ch'] = params['ref_ch']
            self.default_params['ccf_max_lag'] = params['max_lag']
            self.default_params['ccf_window'] = params['window']
            self.save_settings()
            
            # Show progress
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0) # Indeterminate
            QApplication.processEvents()
            
            try:
                ccf, lags = self.processor.compute_cross_correlation(
                    data, 
                    params['ref_ch'], 
                    params['max_lag'], 
                    params['window']
                )
                
                if ccf is not None:
                    # Switch to CCF view
                    idx = self.combo_view.findText("Cross Correlation")
                    if idx >= 0:
                        self.combo_view.setCurrentIndex(idx)
                        
                    self.plot_all_views()
                    QMessageBox.information(self, "Success", "Cross Correlation Analysis Completed!")
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))
            finally:
                self.progress_bar.setVisible(False)

    def open_dispersion_dialog(self):
        if self.processor.processed_data is None:
            QMessageBox.warning(self, "Warning", "No data loaded!")
            return
            
        # Prepare initial params from default_params
        initial_params = {
            'vmin': self.default_params.get('disp_vmin', 100.0),
            'vmax': self.default_params.get('disp_vmax', 2000.0),
            'fmin': self.default_params.get('disp_fmin', 1.0),
            'fmax': self.default_params.get('disp_fmax', 100.0)
        }
        
        dlg = DispersionDialog(self.processor, initial_params, self)
        dlg.exec_()
        
        # Save params after dialog closes (if compute was successful, values are updated in dialog)
        # However, DispersionDialog is modal, so we can get values from it if we modify it to return params
        # Better: Pass default_params reference or update it inside dialog
        # Let's update DispersionDialog to accept initial_params and return last used params
        if dlg.result() == QDialog.Accepted:
            params = dlg.get_params()
            self.default_params['disp_vmin'] = params['vmin']
            self.default_params['disp_vmax'] = params['vmax']
            self.default_params['disp_fmin'] = params['fmin']
            self.default_params['disp_fmax'] = params['fmax']
            self.save_settings()
            
            # Capture result if available
            if dlg.result_data is not None:
                self.dispersion_result = dlg.result_data
                # Switch to Dispersion Analysis View
                idx = self.combo_analysis.findText("Dispersion Analysis")
                if idx >= 0:
                    self.combo_analysis.setCurrentIndex(idx)
                self.plot_all_views()
        
    def open_beamforming_dialog(self):
        if self.processor.processed_data is None:
            QMessageBox.warning(self, "Warning", "No data loaded!")
            return
            
        initial_params = {
            'angle_min': self.default_params.get('bf_angle_min', -90.0),
            'angle_max': self.default_params.get('bf_angle_max', 90.0),
            'fmin': self.default_params.get('bf_fmin', 1.0),
            'fmax': self.default_params.get('bf_fmax', 100.0),
            'v_sound': self.default_params.get('bf_v_sound', 1500.0)
        }
        
        dlg = BeamformingDialog(self.processor, initial_params, self)
        if dlg.exec_() == QDialog.Accepted:
            params = dlg.get_params()
            self.default_params['bf_angle_min'] = params['angle_min']
            self.default_params['bf_angle_max'] = params['angle_max']
            self.default_params['bf_fmin'] = params['fmin']
            self.default_params['bf_fmax'] = params['fmax']
            self.default_params['bf_v_sound'] = params['v_sound']
            self.save_settings()
            
            # Capture result
            if dlg.result_data is not None:
                self.beamforming_result = dlg.result_data
                # Switch to Beamforming View
                idx = self.combo_analysis.findText("Beamforming")
                if idx >= 0:
                    self.combo_analysis.setCurrentIndex(idx)
                self.plot_all_views()

    def open_velocity_dialog(self):
        if self.dispersion_result is None:
            QMessageBox.warning(self, "Warning", "No dispersion analysis result available! Run Dispersion Analysis first.")
            return
            
        dlg = VelocityInversionDialog(self.processor, self.dispersion_result, self)
        if dlg.exec_() == QDialog.Accepted:
            if dlg.result_data is not None:
                self.velocity_result = dlg.result_data
                # Switch to Velocity View
                idx = self.combo_analysis.findText("Velocity Analysis")
                if idx >= 0:
                    self.combo_analysis.setCurrentIndex(idx)
                self.plot_all_views()

    def plot_all_views(self):
        data = self.processor.processed_data
        if data is None:
            return
            
        # Plot Active View First to respond quickly
        self.plot_view(self.views[self.active_view_idx], self.active_view_idx, data)
        QApplication.processEvents()
        
        # Plot others
        for i, view in enumerate(self.views):
            if i != self.active_view_idx:
                self.plot_view(view, i, data)
            
    def plot_view(self, view, index, data):
        # Cleanup SpanSelector/RectangleSelector if updating Space-Time view
        if index == 0:
            if self.span_selector:
                try: self.span_selector.disconnect_events()
                except: pass
                self.span_selector = None
            if self.rect_selector:
                try: self.rect_selector.disconnect_events()
                except: pass
                self.rect_selector = None
            self.play_timer.stop()
            self.playback_active = False

        view.clear()
        
        # Analysis Views
        analysis_mode = self.combo_analysis.currentText()
        if analysis_mode == "Dispersion Analysis":
            if index == 0:
                if self.dispersion_result:
                    f, v, img, curve = self.dispersion_result
                    ax = view.figure.add_subplot(111)
                    extent = [f[0], f[-1], v[0], v[-1]]
                    
                    # Mode Logic
                    # 0: Raw Image, No Curve
                    # 1: Raw Image, With Curve
                    # 2: Smooth Image, With Curve
                    # 3: Smooth Image, No Curve
                    
                    use_smooth = (self.dispersion_view_mode == 2 or self.dispersion_view_mode == 3)
                    show_curve = (self.dispersion_view_mode == 1 or self.dispersion_view_mode == 2)
                    
                    interp = 'bilinear' if use_smooth else None
                    im = ax.imshow(img, aspect='auto', cmap='jet', origin='lower', extent=extent, interpolation=interp)
                    view.figure.colorbar(im, ax=ax, label='Energy')
                    
                    if show_curve and curve is not None:
                        self.dispersion_curve_line, = ax.plot(f, curve, 'r-', linewidth=2)
                    else:
                        self.dispersion_curve_line = None
                        
                    ax.set_xlabel("Frequency (Hz)")
                    ax.set_ylabel("Phase Velocity (m/s)")
                    
                    mode_desc = ["Raw", "Raw + Curve", "Smooth + Curve", "Smooth"][self.dispersion_view_mode]
                    ax.set_title(f"Dispersion Image ({mode_desc}) - Click to Cycle")
                else:
                    view.figure.text(0.5, 0.5, "No Dispersion Data\nRun Analysis via Toolbar", ha='center', va='center')
                view.draw()
            else:
                view.draw()
            return
            
        elif analysis_mode == "Beamforming":
            if index == 0:
                if self.beamforming_result:
                    t_axis, angles, energy_map = self.beamforming_result
                    ax = view.figure.add_subplot(111)
                    extent = [angles[0], angles[-1], t_axis[0], t_axis[-1]]
                    # Use bilinear interpolation for smooth look as requested
                    im = ax.imshow(energy_map, aspect='auto', cmap='jet', origin='lower', extent=extent, interpolation='bilinear')
                    view.figure.colorbar(im, ax=ax, label='Energy')
                    ax.set_xlabel("Angle (deg)")
                    ax.set_ylabel("Time (s)")
                    ax.set_title("Beamforming")
                else:
                    view.figure.text(0.5, 0.5, "No Beamforming Data\nRun Analysis via Toolbar", ha='center', va='center')
                view.draw()
            else:
                view.draw()
            return
            
        elif analysis_mode == "Velocity Analysis":
            if index == 0:
                if self.velocity_result:
                    depths, vs_vals, f_obs, v_obs, v_calc = self.velocity_result
                    
                    # 2 Subplots
                    ax1 = view.figure.add_subplot(121)
                    ax1.plot(f_obs, v_obs, 'k.', label='Observed')
                    
                    if len(v_calc) == len(f_obs):
                        ax1.plot(f_obs, v_calc, 'r-', linewidth=2, label='Modeled')
                    else:
                        f_calc = np.linspace(f_obs[0], f_obs[-1], len(v_calc))
                        ax1.plot(f_calc, v_calc, 'r-', linewidth=2, label='Modeled')
                        
                    ax1.set_xlabel("Frequency (Hz)")
                    ax1.set_ylabel("Phase Velocity (m/s)")
                    ax1.legend()
                    ax1.set_title("Dispersion Fit")
                    ax1.grid(True)
                    
                    ax2 = view.figure.add_subplot(122)
                    ax2.step(vs_vals, depths, where='post', color='blue', linewidth=2)
                    ax2.invert_yaxis()
                    ax2.set_xlabel("Vs (m/s)")
                    ax2.set_ylabel("Depth (m)")
                    ax2.set_title("Inverted Vs Profile")
                    ax2.grid(True)
                else:
                     view.figure.text(0.5, 0.5, "No Velocity Inversion Result\nRun Velocity Analysis via Toolbar", ha='center', va='center')
                view.draw()
            else:
                view.draw()
            return
        
        is_active = (index == self.active_view_idx)
        view_text = self.combo_view.currentText()
        is_ccf = (view_text == "Cross Correlation")
        
        if is_ccf:
            if self.processor.ccf_data is not None:
                data = self.processor.ccf_data
            else:
                if index == 0: 
                    view.figure.text(0.5, 0.5, "No Cross-Correlation Data\nRun Analysis via Toolbar", 
                                   ha='center', va='center')
                    view.draw()
                    return
                # For other views, if no data, just return
                view.draw()
                return
        
        # Optimization: Downsample data for display if too large
        rows, cols = data.shape
        MAX_DIM = 2048 # Max dimension for plotting
        
        # Common parameters
        dt = self.processor.dt if self.processor.dt > 0 else 1.0
        dx = self.processor.dx if self.processor.dx > 0 else 1.0
        
        if index == 0: # Space-Time
            # Layout: 
            # Top: Time Profile (1 row)
            # Left: Channel Profile (1 col)
            # Center: Waterfall (Main)
            # Right: Colorbar + Hist
            
            # Use stored clim if available, else auto
            vmin, vmax = None, None
            if self.clim:
                vmin, vmax = self.clim
            else:
                # Approximate min/max from subsample if huge
                if data.size > 1000000:
                    sub = data[::10, ::10]
                    abs_max = np.max(np.abs(sub))
                else:
                    abs_max = np.max(np.abs(data))
                vmin, vmax = -abs_max, abs_max
            
            # Physical Extents
            start_distance = self.processor.start_distance
            dist_start = start_distance
            dist_end = dist_start + rows * dx
            
            if is_ccf and self.processor.ccf_lags is not None:
                lags = self.processor.ccf_lags
                t_min = lags[0]
                t_max = lags[-1]
                extent = [t_min, t_max, dist_end, dist_start]
                xlabel = "Lag Time (s)"
            else:
                t_max = cols * dt
                extent = [0, t_max, dist_end, dist_start]
                xlabel = "Time (s)"
            
            # Waterfall Extent
            # extent defined above
            
            # Downsample for imshow
            step_r = max(1, rows // MAX_DIM)
            step_c = max(1, cols // MAX_DIM)
            
            if step_r > 1 or step_c > 1:
                display_data = data[::step_r, ::step_c]
            else:
                display_data = data
            
            if is_active:
                gs = view.figure.add_gridspec(3, 3, 
                                            width_ratios=[1, 4, 1],
                                            height_ratios=[1, 4, 0.1],
                                            wspace=0.1, hspace=0.1)
                ax_time_profile = view.figure.add_subplot(gs[0, 1])
                ax_channel_profile = view.figure.add_subplot(gs[1, 0])
                ax_waterfall = view.figure.add_subplot(gs[1, 1])
                ax_hist = view.figure.add_subplot(gs[1, 2])
                
                # Store axes for efficient updates
                self.ax_waterfall = ax_waterfall
                self.ax_time = ax_time_profile
                self.ax_channel = ax_channel_profile
                
                im = ax_waterfall.imshow(display_data, aspect='auto', cmap='seismic', vmin=vmin, vmax=vmax, extent=extent)
                ax_waterfall.set_xlabel(xlabel)
                ax_waterfall.set_ylabel("Distance (m)")
                
                # Interactive State
                if not hasattr(self, 'current_time_idx'): self.current_time_idx = cols // 2
                if not hasattr(self, 'current_channel_idx'): self.current_channel_idx = rows // 2
                
                self.current_time_idx = np.clip(self.current_time_idx, 0, cols-1)
                self.current_channel_idx = np.clip(self.current_channel_idx, 0, rows-1)
                
                if is_ccf and self.processor.ccf_lags is not None:
                    curr_t_val = self.processor.ccf_lags[self.current_time_idx]
                else:
                    curr_t_val = self.current_time_idx * dt
                    
                curr_d_val = dist_start + self.current_channel_idx * dx
                
                # Crosshairs
                self.vline = ax_waterfall.axvline(curr_t_val, color='blue', linestyle='--', alpha=0.5)
                self.hline = ax_waterfall.axhline(curr_d_val, color='red', linestyle='--', alpha=0.5)
                
                # Time Profile (Top)
                time_data = data[self.current_channel_idx, :]
                if is_ccf and self.processor.ccf_lags is not None:
                    t_axis = self.processor.ccf_lags
                else:
                    t_axis = np.arange(cols) * dt
                    
                if len(time_data) > MAX_DIM * 2:
                    s = len(time_data) // (MAX_DIM * 2)
                    self.line_time, = ax_time_profile.plot(t_axis[::s], time_data[::s], color='red')
                else:
                    self.line_time, = ax_time_profile.plot(t_axis, time_data, color='red')
                    
                ax_time_profile.set_xlim(extent[0], extent[1])
                ax_time_profile.set_xticklabels([])
                ax_time_profile.set_ylabel("Amp")
                ax_time_profile.grid(True, alpha=0.3)
                self.vline_time = ax_time_profile.axvline(curr_t_val, color='blue', linestyle='--', alpha=0.5)
                
                # Highlight Rect for Time Profile
                self.rect_highlight_time = Rectangle((0,0), 1, 1, alpha=0.3, color='yellow')
                ax_time_profile.add_patch(self.rect_highlight_time)
                self.rect_highlight_time.set_visible(False)
                
                # Channel Profile (Left)
                channel_data = data[:, self.current_time_idx]
                d_axis = dist_start + np.arange(rows) * dx
                if len(channel_data) > MAX_DIM * 2:
                    s = len(channel_data) // (MAX_DIM * 2)
                    self.line_channel, = ax_channel_profile.plot(channel_data[::s], d_axis[::s], color='blue')
                else:
                    self.line_channel, = ax_channel_profile.plot(channel_data, d_axis, color='blue')
                    
                ax_channel_profile.set_ylim(dist_end, dist_start)
                ax_channel_profile.set_xlabel("Amp")
                ax_channel_profile.grid(True, alpha=0.3)
                self.hline_channel = ax_channel_profile.axhline(curr_d_val, color='red', linestyle='--', alpha=0.5)
                
                # Highlight Rect for Channel Profile
                self.rect_highlight_channel = Rectangle((0,0), 1, 1, alpha=0.3, color='yellow')
                ax_channel_profile.add_patch(self.rect_highlight_channel)
                self.rect_highlight_channel.set_visible(False)
                
                # Histogram (Right)
                if data.size > 10000:
                    flat_data = np.random.choice(data.flatten(), 10000)
                else:
                    flat_data = data.flatten()
                    
                valid_mask = np.isfinite(flat_data)
                if np.any(valid_mask):
                    flat_data = flat_data[valid_mask]
                    dmin, dmax = np.min(flat_data), np.max(flat_data)
                    if dmin == dmax: dmin -= 1e-9; dmax += 1e-9
                    ax_hist.hist(flat_data, bins=100, orientation='horizontal', color='gray', alpha=0.7)
                else:
                    dmin, dmax = 0, 1
                    
                ax_hist.axis('on')
                ax_hist.set_xticks([])
                ax_hist.yaxis.tick_right()
                
                # Histogram Span Selector
                self.hist_ax = ax_hist
                self.data_ax = ax_waterfall
                
                def on_select(vmin_new, vmax_new):
                    self.clim = (vmin_new, vmax_new)
                    im.set_clim(vmin_new, vmax_new)
                    view.draw()
                    
                self.span_selector = SpanSelector(
                    ax_hist, on_select, 'vertical', useblit=True,
                    props=dict(alpha=0.3, facecolor='blue'),
                    interactive=True, drag_from_anywhere=True
                )
                ax_hist.set_ylim(dmin, dmax)
                
                # Box Selector for Playback
                self.rect_selector = RectangleSelector(
                    ax_waterfall, self.on_rect_select,
                    useblit=True,
                    props=dict(alpha=0.2, facecolor='green', edgecolor='green'),
                    button=[1], # Left click
                    minspanx=5, minspany=5,
                    spancoords='pixels',
                    interactive=True,
                    drag_from_anywhere=True
                )
                
            else:
                # Thumbnail View: Just Waterfall
                ax = view.figure.add_subplot(111)
                ax.imshow(display_data, aspect='auto', cmap='seismic', vmin=vmin, vmax=vmax, extent=extent)
                ax.set_title(view.title, fontsize=8)
                ax.axis('on')
                ax.tick_params(labelsize=6)
            
        elif index == 1: # Time-Frequency
            ax = view.figure.add_subplot(111)
            # Use average trace
            trace = np.mean(data, axis=0)
            fs = 1.0 / dt
            # If trace is too long, downsample or limit nperseg
            f, t, Zxx = signal.stft(trace, fs=fs, nperseg=min(256, len(trace)))
            im = ax.pcolormesh(t, f, np.abs(Zxx), shading='gouraud', cmap='viridis')
            if is_active:
                ax.set_title(f"Time-Frequency (STFT): {view_text}")
                ax.set_ylabel("Frequency (Hz)")
                ax.set_xlabel("Time (s)")
                view.figure.colorbar(im, ax=ax)
            else:
                ax.set_title(view.title, fontsize=8)
                ax.tick_params(labelsize=6)
            
        elif index == 2: # Spectrum
            ax = view.figure.add_subplot(111)
            # Optimization: Use subset of channels (e.g., every 50th)
            step = max(1, rows // 50)
            subset = data[::step, :]
            spectrum = np.mean(np.abs(fft(subset, axis=1)), axis=0)
            freqs = np.fft.fftfreq(len(spectrum), d=dt)
            pos_mask = freqs >= 0
            
            # Downsample spectrum for plotting if huge
            freqs_pos = freqs[pos_mask]
            spec_pos = spectrum[pos_mask]
            if len(freqs_pos) > MAX_DIM:
                s = len(freqs_pos) // MAX_DIM
                ax.plot(freqs_pos[::s], spec_pos[::s])
            else:
                ax.plot(freqs_pos, spec_pos)
                
            if is_active:
                ax.set_title(f"Frequency Spectrum: {view_text}")
                ax.set_xlabel("Frequency (Hz)")
                ax.set_ylabel("Amplitude")
                ax.grid(True)
            else:
                ax.set_title(view.title, fontsize=8)
                ax.tick_params(labelsize=6)
                ax.grid(False)
            
        elif index == 3: # FK Spectrum
            ax = view.figure.add_subplot(111)
            
            # Optimization: Resize data before FFT2
            # Target ~1024x1024 max for speed
            FK_DIM = 1024
            step_r = max(1, rows // FK_DIM)
            step_c = max(1, cols // FK_DIM)
            
            if step_r > 1 or step_c > 1:
                small_data = data[::step_r, ::step_c]
            else:
                small_data = data
                
            f_k = fftshift(fft2(small_data))
            mag = np.abs(f_k)
            mag = np.log1p(mag)
            
            # Adjust axes for extent
            # New effective dt and dx
            eff_dt = dt * step_c
            eff_dx = dx * step_r
            
            s_rows, s_cols = small_data.shape
            freqs = fftshift(np.fft.fftfreq(s_cols, d=eff_dt))
            k_wavenumbers = fftshift(np.fft.fftfreq(s_rows, d=eff_dx))
            
            im = ax.imshow(mag, aspect='auto', cmap='inferno', 
                           extent=[freqs[0], freqs[-1], k_wavenumbers[0], k_wavenumbers[-1]],
                           origin='lower')
                           
            if is_active:
                ax.set_title(f"FK Spectrum (Log): {view_text}")
                ax.set_xlabel("Frequency (Hz)")
                ax.set_ylabel("Wavenumber (1/m)")
                view.figure.colorbar(im, ax=ax)
            else:
                ax.set_title(view.title, fontsize=8)
                ax.tick_params(labelsize=6)
            
        view.draw()

    def on_active_view_interact(self, event):
        if event.inaxes is None:
            return
            
        index = self.active_view_idx
        
        # Check for Analysis Views Interaction
        analysis_mode = self.combo_analysis.currentText()
        if analysis_mode == "Dispersion Analysis" and index == 0:
            # Cycle through modes: 0 -> 1 -> 2 -> 3 -> 0
            self.dispersion_view_mode = (self.dispersion_view_mode + 1) % 4
            self.plot_all_views() # Redraw with new mode
            return
        elif analysis_mode == "Beamforming" and index == 0:
            return
        
        view_text = self.combo_view.currentText()
        is_ccf = (view_text == "Cross Correlation")
        
        if is_ccf:
            if self.processor.ccf_data is None: return
            data = self.processor.ccf_data
        else:
            data = self.processor.processed_data
            
        if data is None:
            return
            
        dt = self.processor.dt if self.processor.dt > 0 else 1.0
        dx = self.processor.dx if self.processor.dx > 0 else 1.0
        start_distance = self.processor.start_distance
        
        if index == 0: # Space-Time
            if hasattr(self, 'data_ax') and event.inaxes == self.data_ax:
                # Stop playback on manual click
                if hasattr(self, 'play_timer'): self.play_timer.stop()
                self.playback_active = False
                
                # Hide highlights
                if hasattr(self, 'rect_highlight_time'): self.rect_highlight_time.set_visible(False)
                if hasattr(self, 'rect_highlight_channel'): self.rect_highlight_channel.set_visible(False)

                if is_ccf and self.processor.ccf_lags is not None:
                     # xdata is lag. find closest index
                     lags = self.processor.ccf_lags
                     # assume lags are uniform
                     lag_start = lags[0]
                     self.current_time_idx = int((event.xdata - lag_start) / dt)
                else:
                    if dt > 0:
                        self.current_time_idx = int(event.xdata / dt)
                    else:
                        self.current_time_idx = int(event.xdata)
                    
                if dx > 0:
                    self.current_channel_idx = int((event.ydata - start_distance) / dx)
                else:
                    self.current_channel_idx = int(event.ydata)
                    
                # Clamp
                rows, cols = data.shape
                self.current_time_idx = np.clip(self.current_time_idx, 0, cols-1)
                self.current_channel_idx = np.clip(self.current_channel_idx, 0, rows-1)

                # Efficient Update
                if is_ccf and self.processor.ccf_lags is not None:
                     curr_t_val = self.processor.ccf_lags[self.current_time_idx]
                else:
                     curr_t_val = self.current_time_idx * dt
                     
                curr_d_val = start_distance + self.current_channel_idx * dx
                
                # Update Crosshairs
                if hasattr(self, 'vline'): self.vline.set_xdata([curr_t_val, curr_t_val])
                if hasattr(self, 'hline'): self.hline.set_ydata([curr_d_val, curr_d_val])
                if hasattr(self, 'vline_time'): self.vline_time.set_xdata([curr_t_val, curr_t_val])
                if hasattr(self, 'hline_channel'): self.hline_channel.set_ydata([curr_d_val, curr_d_val])
                
                # Update Profiles
                MAX_DIM = 2048
                
                # Time Profile (Top) - Fixed Channel, Varying Time
                time_data = data[self.current_channel_idx, :]
                if is_ccf and self.processor.ccf_lags is not None:
                    t_axis = self.processor.ccf_lags
                else:
                    t_axis = np.arange(cols) * dt
                    
                if len(time_data) > MAX_DIM * 2:
                    s = len(time_data) // (MAX_DIM * 2)
                    self.line_time.set_data(t_axis[::s], time_data[::s])
                else:
                    self.line_time.set_data(t_axis, time_data)
                    
                # Channel Profile (Left) - Fixed Time, Varying Channel
                channel_data = data[:, self.current_time_idx]
                d_axis = start_distance + np.arange(rows) * dx
                if len(channel_data) > MAX_DIM * 2:
                    s = len(channel_data) // (MAX_DIM * 2)
                    self.line_channel.set_data(channel_data[::s], d_axis[::s])
                else:
                    self.line_channel.set_data(channel_data, d_axis)
                
                view = self.views[self.active_view_idx]
                view.canvas.draw()
                
        elif index == 3: # FK Spectrum
            f = event.xdata
            k = event.ydata
            if k != 0:
                v = f / k
            else:
                v = float('inf')
                
            if hasattr(self, 'fk_text') and self.fk_text:
                try:
                    self.fk_text.remove()
                except:
                    pass
            
            ax = event.inaxes
            self.fk_text = ax.text(f, k, f"  v={v:.2f} m/s\n  f={f:.2f} Hz\n  k={k:.4f} 1/m", 
                                   color='white', fontweight='bold',
                                   bbox=dict(facecolor='black', alpha=0.5))
            active_view = self.views[self.active_view_idx]
            active_view.canvas.draw_idle()

    def load_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Image", "", "Images (*.png *.jpg *.tif *.bmp)")
        if path:
            try:
                self.processor.load_image(path)
                
                # Restore settings from config (load_image resets them to 1.0)
                self.processor.base_dx = self.default_params.get('dx', 4.0)
                self.processor.base_dt = self.default_params.get('dt', 0.1)
                self.processor.dx = self.processor.base_dx
                self.processor.dt = self.processor.base_dt
                self.processor.gauge_length = self.default_params.get('gl', 10.0)
                
                self.run_pipeline([]) 
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def load_tdms(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open TDMS", "", "TDMS Files (*.tdms)")
        if path:
            # Setup Status Bar Progress
            self.progress_bar.setValue(0)
            self.progress_bar.setVisible(True)
            self.cancel_btn.setVisible(True)
            self.status_bar.showMessage(f"Loading: {os.path.basename(path)}...")
            
            # Create Thread
            self.loader_thread = TDMSLoaderThread(self.processor, path)
            self.loader_thread.progress.connect(self.progress_bar.setValue)
            
            def on_finished(result, error):
                self.progress_bar.setVisible(False)
                self.cancel_btn.setVisible(False)
                
                if error:
                    self.status_bar.showMessage(f"Error loading file: {str(error)}")
                    QMessageBox.critical(self, "Error", str(error))
                elif result is None:
                     self.status_bar.showMessage("Loading cancelled or failed.")
                else:
                    self.status_bar.showMessage("TDMS Loaded Successfully.", 5000)
                    self.run_pipeline([])
                    
            self.loader_thread.finished.connect(on_finished)
            
            # Handle Cancel
            # Disconnect previous if exists to avoid multiple connections
            try: self.cancel_btn.clicked.disconnect()
            except: pass
            
            self.cancel_btn.clicked.connect(self.loader_thread.terminate)
            
            self.loader_thread.start()

    def open_editor(self):
        if not self.editor_window:
            self.editor_window = QMainWindow()
            self.editor_window.setWindowTitle("Pipeline Editor")
            self.editor_window.setCentralWidget(self.editor_widget)
            self.editor_window.resize(800, 600)
        self.editor_window.show()
        
    def run_pipeline(self, pipeline):
        # Update pipeline state
        self.pipeline_state = pipeline
        
        # Execute
        try:
            self.processor.execute_pipeline(pipeline)
            
            # If current view is Cross Correlation, auto-update it
            if self.combo_view.currentText() == "Cross Correlation":
                self.auto_update_ccf()
            
            self.plot_all_views()
        except Exception as e:
            # QMessageBox.warning(self, "Processing Error", str(e))
            print(f"Processing Error: {e}")
            
    def auto_update_ccf(self):
        """Auto re-run CCF if active view is CCF and params exist"""
        # Check if we have CCF params saved
        ref_ch = self.default_params.get('ccf_ref_ch', None)
        max_lag = self.default_params.get('ccf_max_lag', None)
        window = self.default_params.get('ccf_window', None)
        
        if ref_ch is None or max_lag is None:
            return
            
        data = self.processor.processed_data
        if data is None: return
        
        try:
            self.processor.compute_cross_correlation(data, ref_ch, max_lag, window)
        except Exception as e:
            print(f"Auto CCF Error: {e}")

    def save_pipeline_state(self, pipeline):
        self.pipeline_state = pipeline

    def open_settings(self):
        # Current params from default_params (config)
        # We ensure we start with what's in the config/defaults, not necessarily what's in processor
        # (though they should be synced)
        current_params = self.default_params.copy()
        
        dialog = SettingsDialog(current_params, self)
        if dialog.exec_() == QDialog.Accepted:
            new_params = dialog.get_params()
            
            # Update Processor Base Params
            self.processor.base_dx = new_params['dx']
            self.processor.base_dt = new_params['dt']
            self.processor.gauge_length = new_params['gl']
            
            # Update effective params
            self.processor.dx = new_params['dx']
            self.processor.dt = new_params['dt']
            
            # Update default params
            self.default_params.update(new_params)
            
            # Save settings
            self.save_settings()
            
            # Re-run pipeline to ensure consistency
            if self.pipeline_state:
                self.run_pipeline(self.pipeline_state)
            else:
                self.plot_all_views()

    def on_rect_select(self, eclick, erelease):
        if not hasattr(self.processor, 'processed_data') or self.processor.processed_data is None:
            return
            
        x1, y1 = eclick.xdata, eclick.ydata
        x2, y2 = erelease.xdata, erelease.ydata
        
        # Determine range indices
        dt = self.processor.dt if self.processor.dt > 0 else 1.0
        dx = self.processor.dx if self.processor.dx > 0 else 1.0
        start_dist = self.processor.start_distance
        
        t_min, t_max = min(x1, x2), max(x1, x2)
        d_min, d_max = min(y1, y2), max(y1, y2)
        
        cols = self.processor.processed_data.shape[1]
        rows = self.processor.processed_data.shape[0]
        
        t_idx_start = int(t_min / dt)
        t_idx_end = int(t_max / dt)
        t_idx_start = np.clip(t_idx_start, 0, cols-1)
        t_idx_end = np.clip(t_idx_end, 0, cols-1)
        
        d_idx_start = int((d_min - start_dist) / dx)
        d_idx_end = int((d_max - start_dist) / dx)
        d_idx_start = np.clip(d_idx_start, 0, rows-1)
        d_idx_end = np.clip(d_idx_end, 0, rows-1)
        
        if t_idx_start >= t_idx_end: return
        
        self.playback_range = (t_idx_start, t_idx_end)
        
        # Highlight on profiles
        # Time Profile Highlight (Time range)
        ylim_time = self.ax_time.get_ylim()
        self.rect_highlight_time.set_xy((t_min, ylim_time[0]))
        self.rect_highlight_time.set_width(t_max - t_min)
        self.rect_highlight_time.set_height(ylim_time[1] - ylim_time[0])
        self.rect_highlight_time.set_visible(True)
        
        # Channel Profile Highlight (Distance range)
        xlim_channel = self.ax_channel.get_xlim()
        self.rect_highlight_channel.set_xy((xlim_channel[0], d_min))
        self.rect_highlight_channel.set_width(xlim_channel[1] - xlim_channel[0])
        self.rect_highlight_channel.set_height(d_max - d_min)
        self.rect_highlight_channel.set_visible(True)
        
        # Start Playback
        self.current_time_idx = t_idx_start
        self.play_timer.start(self.play_interval)
        self.playback_active = True

    def advance_playback(self):
        if not self.playback_active or not self.playback_range:
            self.play_timer.stop()
            return
            
        start, end = self.playback_range
        self.current_time_idx += 1
        if self.current_time_idx > end:
            self.current_time_idx = start
            
        # Update plots
        dt = self.processor.dt if self.processor.dt > 0 else 1.0
        curr_t_val = self.current_time_idx * dt
        
        # Update Vertical Lines
        if hasattr(self, 'vline'): self.vline.set_xdata([curr_t_val, curr_t_val])
        if hasattr(self, 'vline_time'): self.vline_time.set_xdata([curr_t_val, curr_t_val])
        
        # Update Channel Profile
        full_data = self.processor.processed_data
        channel_data = full_data[:, self.current_time_idx]
        
        rows = len(channel_data)
        MAX_DIM = 2048
        dx = self.processor.dx if self.processor.dx > 0 else 1.0
        start_dist = self.processor.start_distance
        d_axis = start_dist + np.arange(rows) * dx
        
        if rows > MAX_DIM * 2:
            s = rows // (MAX_DIM * 2)
            self.line_channel.set_data(channel_data[::s], d_axis[::s])
        else:
            self.line_channel.set_data(channel_data, d_axis)
            
        self.views[self.active_view_idx].canvas.draw()
