from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from .base import NodeBlock

# --- IO Nodes ---

class InputNode(NodeBlock):
    def __init__(self):
        super().__init__("Input")
        self.width = 100
        self.height = 60
        self.add_socket(0, 0, False) # Only Output

class OutputNode(NodeBlock):
    def __init__(self):
        super().__init__("Output")
        self.width = 100
        self.height = 60
        self.add_socket(0, 0, True) # Only Input

# --- Preprocessing Nodes ---

class ROINode(NodeBlock):
    def __init__(self):
        super().__init__("ROI")
        self.height = 180
        self.add_socket(0, 0, True)
        self.add_socket(0, 0, False)
        
        w = QWidget()
        l = QFormLayout(w)
        
        self.sb_ch_start = QSpinBox()
        self.sb_ch_start.setRange(0, 999999)
        self.sb_ch_start.setValue(0)
        
        self.sb_ch_end = QSpinBox()
        self.sb_ch_end.setRange(0, 999999)
        self.sb_ch_end.setValue(1000)
        
        self.sb_t_start = QSpinBox()
        self.sb_t_start.setRange(0, 999999)
        self.sb_t_start.setValue(0)
        
        self.sb_t_end = QSpinBox()
        self.sb_t_end.setRange(0, 999999)
        self.sb_t_end.setValue(1000)
        
        l.addRow("Ch Start:", self.sb_ch_start)
        l.addRow("Ch End:", self.sb_ch_end)
        l.addRow("Time Start:", self.sb_t_start)
        l.addRow("Time End:", self.sb_t_end)
        
        self.set_content(w)

    def get_config(self):
        return {
            "type": "ROI",
            "ch_start": self.sb_ch_start.value(),
            "ch_end": self.sb_ch_end.value(),
            "time_start": self.sb_t_start.value(),
            "time_end": self.sb_t_end.value()
        }

    def set_config(self, config):
        self.sb_ch_start.setValue(config.get("ch_start", 0))
        self.sb_ch_end.setValue(config.get("ch_end", 1000))
        self.sb_t_start.setValue(config.get("time_start", 0))
        self.sb_t_end.setValue(config.get("time_end", 1000))

class DownsampleNode(NodeBlock):
    def __init__(self):
        super().__init__("Downsample")
        self.height = 140
        self.add_socket(0, 0, True)
        self.add_socket(0, 0, False)
        
        w = QWidget()
        l = QFormLayout(w)
        
        self.sb_space = QSpinBox()
        self.sb_space.setRange(1, 100)
        self.sb_space.setValue(1)
        
        self.sb_time = QSpinBox()
        self.sb_time.setRange(1, 100)
        self.sb_time.setValue(1)
        
        l.addRow("Space Factor:", self.sb_space)
        l.addRow("Time Factor:", self.sb_time)
        
        self.set_content(w)

    def get_config(self):
        return {
            "type": "Downsample",
            "space": self.sb_space.value(),
            "time": self.sb_time.value()
        }

    def set_config(self, config):
        self.sb_space.setValue(config.get("space", 1))
        self.sb_time.setValue(config.get("time", 1))

class DetrendNode(NodeBlock):
    def __init__(self):
        super().__init__("Detrend")
        self.height = 100
        self.add_socket(0, 0, True)
        self.add_socket(0, 0, False)
        
        w = QWidget()
        l = QFormLayout(w)
        self.combo = QComboBox()
        self.combo.addItems(["Time Axis (1)", "Space Axis (0)"])
        l.addRow("Axis:", self.combo)
        
        self.set_content(w)

    def get_config(self):
        return {
            "type": "Detrend",
            "axis": 1 if self.combo.currentIndex() == 0 else 0
        }

    def set_config(self, config):
        idx = 0 if config.get("axis", 1) == 1 else 1
        self.combo.setCurrentIndex(idx)

class NormalizeNode(NodeBlock):
    def __init__(self):
        super().__init__("Normalize")
        self.height = 100
        self.add_socket(0, 0, True)
        self.add_socket(0, 0, False)
        
        w = QWidget()
        l = QFormLayout(w)
        self.combo = QComboBox()
        self.combo.addItems(["Global Z-Score", "Channel Z-Score", "Time Z-Score"])
        l.addRow("Mode:", self.combo)
        
        self.set_content(w)

    def get_config(self):
        return {
            "type": "Normalize",
            "mode": self.combo.currentText()
        }

    def set_config(self, config):
        text = config.get("mode", "Global Z-Score")
        idx = self.combo.findText(text)
        if idx >= 0: self.combo.setCurrentIndex(idx)

# --- Filter Nodes ---

class BandpassNode(NodeBlock):
    def __init__(self):
        super().__init__("Bandpass")
        self.height = 220
        self.add_socket(0, 0, True)
        self.add_socket(0, 0, False)
        
        w = QWidget()
        l = QFormLayout(w)
        self.sb_low = QDoubleSpinBox()
        self.sb_low.setRange(0, 20000)
        self.sb_low.setSingleStep(1.0)
        self.sb_low.setValue(10.0)
        
        self.sb_high = QDoubleSpinBox()
        self.sb_high.setRange(0, 20000)
        self.sb_high.setSingleStep(1.0)
        self.sb_high.setValue(100.0)
        
        self.combo_type = QComboBox()
        self.combo_type.addItems(["Butterworth", "Chebyshev I", "Chebyshev II", "Elliptic", "Bessel"])
        
        self.sb_order = QSpinBox()
        self.sb_order.setRange(1, 20)
        self.sb_order.setValue(4)
        
        l.addRow("Low (Hz):", self.sb_low)
        l.addRow("High (Hz):", self.sb_high)
        l.addRow("Type:", self.combo_type)
        l.addRow("Order:", self.sb_order)
        self.set_content(w)

    def get_config(self):
        return {
            "type": "Bandpass",
            "low": self.sb_low.value(),
            "high": self.sb_high.value(),
            "filter_type": self.combo_type.currentText(),
            "order": self.sb_order.value()
        }

    def set_config(self, config):
        self.sb_low.setValue(config.get("low", 10.0))
        self.sb_high.setValue(config.get("high", 100.0))
        self.combo_type.setCurrentText(config.get("filter_type", "Butterworth"))
        self.sb_order.setValue(config.get("order", 4))

class LowpassNode(NodeBlock):
    def __init__(self):
        super().__init__("Lowpass")
        self.height = 180
        self.add_socket(0, 0, True)
        self.add_socket(0, 0, False)
        
        w = QWidget()
        l = QFormLayout(w)
        self.sb_cutoff = QDoubleSpinBox()
        self.sb_cutoff.setRange(0, 20000)
        self.sb_cutoff.setSingleStep(1.0)
        self.sb_cutoff.setValue(50.0)
        
        self.combo_type = QComboBox()
        self.combo_type.addItems(["Butterworth", "Chebyshev I", "Chebyshev II", "Elliptic", "Bessel"])
        
        self.sb_order = QSpinBox()
        self.sb_order.setRange(1, 20)
        self.sb_order.setValue(4)
        
        l.addRow("Cutoff (Hz):", self.sb_cutoff)
        l.addRow("Type:", self.combo_type)
        l.addRow("Order:", self.sb_order)
        self.set_content(w)

    def get_config(self):
        return {
            "type": "Lowpass",
            "cutoff": self.sb_cutoff.value(),
            "filter_type": self.combo_type.currentText(),
            "order": self.sb_order.value()
        }

    def set_config(self, config):
        self.sb_cutoff.setValue(config.get("cutoff", 50.0))
        self.combo_type.setCurrentText(config.get("filter_type", "Butterworth"))
        self.sb_order.setValue(config.get("order", 4))

class HighpassNode(NodeBlock):
    def __init__(self):
        super().__init__("Highpass")
        self.height = 180
        self.add_socket(0, 0, True)
        self.add_socket(0, 0, False)
        
        w = QWidget()
        l = QFormLayout(w)
        self.sb_cutoff = QDoubleSpinBox()
        self.sb_cutoff.setRange(0, 20000)
        self.sb_cutoff.setSingleStep(1.0)
        self.sb_cutoff.setValue(50.0)
        
        self.combo_type = QComboBox()
        self.combo_type.addItems(["Butterworth", "Chebyshev I", "Chebyshev II", "Elliptic", "Bessel"])
        
        self.sb_order = QSpinBox()
        self.sb_order.setRange(1, 20)
        self.sb_order.setValue(4)
        
        l.addRow("Cutoff (Hz):", self.sb_cutoff)
        l.addRow("Type:", self.combo_type)
        l.addRow("Order:", self.sb_order)
        self.set_content(w)

    def get_config(self):
        return {
            "type": "Highpass",
            "cutoff": self.sb_cutoff.value(),
            "filter_type": self.combo_type.currentText(),
            "order": self.sb_order.value()
        }

    def set_config(self, config):
        self.sb_cutoff.setValue(config.get("cutoff", 50.0))
        self.combo_type.setCurrentText(config.get("filter_type", "Butterworth"))
        self.sb_order.setValue(config.get("order", 4))

class KalmanFilterNode(NodeBlock):
    def __init__(self):
        super().__init__("Kalman Filter")
        self.height = 150
        self.width = 220
        self.add_socket(0, 0, True)
        self.add_socket(0, 0, False)
        
        w = QWidget()
        l = QFormLayout(w)
        
        self.sb_q = QDoubleSpinBox()
        self.sb_q.setRange(1e-9, 1000.0)
        self.sb_q.setDecimals(6)
        self.sb_q.setValue(1e-5)
        
        self.sb_r = QDoubleSpinBox()
        self.sb_r.setRange(1e-9, 1000.0)
        self.sb_r.setDecimals(6)
        self.sb_r.setValue(1e-2)
        
        l.addRow("Process Noise (Q):", self.sb_q)
        l.addRow("Meas. Noise (R):", self.sb_r)
        
        self.set_content(w)

    def get_config(self):
        return {
            "type": "Kalman Filter",
            "Q": self.sb_q.value(),
            "R": self.sb_r.value()
        }

    def set_config(self, config):
        self.sb_q.setValue(config.get("Q", 1e-5))
        self.sb_r.setValue(config.get("R", 1e-2))

class FKNode(NodeBlock):
    def __init__(self):
        super().__init__("FK Filter")
        self.height = 160
        self.add_socket(0, 0, True)
        self.add_socket(0, 0, False)
        
        w = QWidget()
        l = QFormLayout(w)
        
        self.sb_v_min = QDoubleSpinBox()
        self.sb_v_min.setRange(-999999, 999999)
        self.sb_v_min.setValue(-3000)
        
        self.sb_v_max = QDoubleSpinBox()
        self.sb_v_max.setRange(-999999, 999999)
        self.sb_v_max.setValue(3000)
        
        l.addRow("Min Vel (m/s):", self.sb_v_min)
        l.addRow("Max Vel (m/s):", self.sb_v_max)
        self.set_content(w)

    def get_config(self):
        return {
            "type": "FK Filter",
            "min_velocity": self.sb_v_min.value(),
            "max_velocity": self.sb_v_max.value()
        }

    def set_config(self, config):
        self.sb_v_min.setValue(config.get("min_velocity", -3000))
        self.sb_v_max.setValue(config.get("max_velocity", 3000))

class FKMagNode(NodeBlock):
    def __init__(self):
        super().__init__("FK Mag Threshold")
        self.height = 120
        self.add_socket(0, 0, True)
        self.add_socket(0, 0, False)
        
        w = QWidget()
        l = QFormLayout(w)
        self.sb_thresh = QDoubleSpinBox()
        self.sb_thresh.setRange(0, 1)
        self.sb_thresh.setValue(0.5)
        
        l.addRow("Threshold:", self.sb_thresh)
        self.set_content(w)

    def get_config(self):
        return {
            "type": "FK Mag Threshold",
            "threshold": self.sb_thresh.value()
        }

    def set_config(self, config):
        self.sb_thresh.setValue(config.get("threshold", 0.5))

class TimeThreshNode(NodeBlock):
    def __init__(self):
        super().__init__("Time Threshold")
        self.height = 120
        self.add_socket(0, 0, True)
        self.add_socket(0, 0, False)
        
        w = QWidget()
        l = QFormLayout(w)
        self.sb_thresh = QDoubleSpinBox()
        self.sb_thresh.setRange(0, 1)
        self.sb_thresh.setValue(0.1)
        
        l.addRow("Threshold:", self.sb_thresh)
        self.set_content(w)

    def get_config(self):
        return {
            "type": "Time Threshold",
            "threshold": self.sb_thresh.value()
        }

    def set_config(self, config):
        self.sb_thresh.setValue(config.get("threshold", 0.1))

class EnvelopeNode(NodeBlock):
    def __init__(self):
        super().__init__("Envelope")
        self.height = 80
        self.add_socket(0, 0, True)
        self.add_socket(0, 0, False)
        
        w = QWidget()
        self.set_content(w)

    def get_config(self):
        return {
            "type": "Envelope"
        }

    def set_config(self, config):
        pass

class FreqThreshNode(NodeBlock):
    def __init__(self):
        super().__init__("Freq Threshold")
        self.height = 120
        self.add_socket(0, 0, True)
        self.add_socket(0, 0, False)
        
        w = QWidget()
        l = QFormLayout(w)
        self.sb_thresh = QDoubleSpinBox()
        self.sb_thresh.setRange(0, 1)
        self.sb_thresh.setValue(0.1)
        
        l.addRow("Threshold:", self.sb_thresh)
        self.set_content(w)

    def get_config(self):
        return {
            "type": "Freq Threshold",
            "threshold": self.sb_thresh.value()
        }

    def set_config(self, config):
        self.sb_thresh.setValue(config.get("threshold", 0.1))
