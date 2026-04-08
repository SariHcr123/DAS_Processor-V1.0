
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
import numpy as np
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

class VelocityInversionDialog(QDialog):
    def __init__(self, processor, dispersion_data, parent=None):
        super().__init__(parent)
        self.processor = processor
        self.dispersion_data = dispersion_data # (f, v, img, curve)
        self.result_data = None
        self.setWindowTitle("Velocity Analysis (Scholte Wave)")
        self.resize(1000, 600)
        self.init_ui()
        
    def init_ui(self):
        layout = QHBoxLayout(self)
        
        # Left: Controls
        ctrl_panel = QWidget()
        ctrl_layout = QVBoxLayout(ctrl_panel)
        ctrl_panel.setFixedWidth(300)
        
        # Water Params
        grp_water = QGroupBox("Water Properties")
        form_water = QFormLayout(grp_water)
        self.spin_vp_water = QDoubleSpinBox()
        self.spin_vp_water.setRange(1000, 2000)
        self.spin_vp_water.setValue(1500)
        form_water.addRow("Vp Water (m/s):", self.spin_vp_water)
        ctrl_layout.addWidget(grp_water)
        
        # Sediment Search Bounds
        grp_sed = QGroupBox("Sediment Search Bounds")
        form_sed = QFormLayout(grp_sed)
        
        self.spin_vs_sed_min = QDoubleSpinBox()
        self.spin_vs_sed_min.setRange(10, 2000)
        self.spin_vs_sed_min.setValue(20)
        self.spin_vs_sed_max = QDoubleSpinBox()
        self.spin_vs_sed_max.setRange(10, 2000)
        self.spin_vs_sed_max.setValue(500)
        form_sed.addRow("Vs Sed Min:", self.spin_vs_sed_min)
        form_sed.addRow("Vs Sed Max:", self.spin_vs_sed_max)
        
        self.spin_h_min = QDoubleSpinBox()
        self.spin_h_min.setRange(0.1, 200)
        self.spin_h_min.setValue(1.0)
        self.spin_h_max = QDoubleSpinBox()
        self.spin_h_max.setRange(0.1, 200)
        self.spin_h_max.setValue(50.0)
        form_sed.addRow("Thickness Min (m):", self.spin_h_min)
        form_sed.addRow("Thickness Max (m):", self.spin_h_max)
        
        ctrl_layout.addWidget(grp_sed)
        
        # Substrate
        grp_sub = QGroupBox("Substrate Bounds")
        form_sub = QFormLayout(grp_sub)
        self.spin_vs_sub_min = QDoubleSpinBox()
        self.spin_vs_sub_min.setRange(100, 5000)
        self.spin_vs_sub_min.setValue(200)
        self.spin_vs_sub_max = QDoubleSpinBox()
        self.spin_vs_sub_max.setRange(100, 5000)
        self.spin_vs_sub_max.setValue(2000)
        form_sub.addRow("Vs Sub Min:", self.spin_vs_sub_min)
        form_sub.addRow("Vs Sub Max:", self.spin_vs_sub_max)
        ctrl_layout.addWidget(grp_sub)
        
        self.btn_invert = QPushButton("Invert Profile")
        self.btn_invert.clicked.connect(self.run_inversion)
        ctrl_layout.addWidget(self.btn_invert)
        
        self.lbl_result = QLabel("Result: N/A")
        self.lbl_result.setWordWrap(True)
        ctrl_layout.addWidget(self.lbl_result)
        
        ctrl_layout.addStretch()
        
        # Dialog Buttons
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        ctrl_layout.addWidget(btns)
        
        layout.addWidget(ctrl_panel)
        
        # Right: Plot
        self.figure = Figure()
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(self.canvas)
        
        # Plot Initial Data
        self.plot_initial()
        
    def plot_initial(self):
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        if self.dispersion_data and self.dispersion_data[3] is not None:
            f, v, img, curve = self.dispersion_data
            ax.plot(f, curve, 'k.', label='Observed Data')
            ax.set_xlabel("Frequency (Hz)")
            ax.set_ylabel("Phase Velocity (m/s)")
            ax.legend()
        else:
            ax.text(0.5, 0.5, "No Dispersion Curve Data", ha='center')
        self.canvas.draw()
        
    def run_inversion(self):
        if not self.dispersion_data or self.dispersion_data[3] is None:
            QMessageBox.warning(self, "Error", "No dispersion curve data available.")
            return
            
        f_obs = self.dispersion_data[0]
        v_obs = self.dispersion_data[3]
        
        # Filter NaNs
        valid = np.isfinite(v_obs)
        if np.sum(valid) < 5:
            QMessageBox.warning(self, "Error", "Not enough valid points in dispersion curve.")
            return
            
        f_obs = f_obs[valid]
        v_obs = v_obs[valid]
        
        # Bounds
        bounds = [
            (self.spin_vs_sed_min.value(), self.spin_vs_sed_max.value()),
            (self.spin_h_min.value(), self.spin_h_max.value()),
            (self.spin_vs_sub_min.value(), self.spin_vs_sub_max.value())
        ]
        
        # Run
        try:
            res_x, error = self.processor.invert_scholte_profile(f_obs, v_obs, bounds)
            
            vs1, h, vs2 = res_x
            self.lbl_result.setText(f"Vs Sed: {vs1:.1f} m/s\nThickness: {h:.1f} m\nVs Sub: {vs2:.1f} m/s\nRMSE: {error:.2f}")
            
            # Compute Calc Curve
            f_calc, v_calc = self.processor.compute_scholte_dispersion_curve(
                vs1, h, vs2, vp_water=self.spin_vp_water.value(), 
                f_min=f_obs[0], f_max=f_obs[-1], df=(f_obs[1]-f_obs[0])
            )
            
            # Plot Result
            self.figure.clear()
            
            # 1. Dispersion Fit
            ax1 = self.figure.add_subplot(121)
            ax1.plot(f_obs, v_obs, 'k.', label='Observed')
            ax1.plot(f_calc, v_calc, 'r-', linewidth=2, label='Calculated')
            ax1.set_xlabel("Frequency (Hz)")
            ax1.set_ylabel("Phase Velocity (m/s)")
            ax1.set_title("Dispersion Fit")
            ax1.legend()
            
            # 2. Vs Profile
            ax2 = self.figure.add_subplot(122)
            # Visualize profile
            # Depth 0-H: Vs1
            # Depth H-2H: Vs2
            depths = [0, h, h, h*3] 
            vs_vals = [vs1, vs1, vs2, vs2]
            
            ax2.plot(vs_vals, depths, 'b-', linewidth=2)
            ax2.invert_yaxis()
            ax2.set_xlabel("Vs (m/s)")
            ax2.set_ylabel("Depth (m)")
            ax2.set_title("Inverted Vs Profile")
            ax2.grid(True)
            
            self.canvas.draw()
            
            self.result_data = (depths, vs_vals, f_obs, v_obs, v_calc)
            
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
