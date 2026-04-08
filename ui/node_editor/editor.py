import json
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

from .base import NodeScene, NodeView, MinimapView, NodeEdge, NodeBlock
from .nodes import (
    InputNode, OutputNode, 
    ROINode, DownsampleNode, DetrendNode, NormalizeNode,
    BandpassNode, LowpassNode, HighpassNode, 
    FKNode, FKMagNode, TimeThreshNode, FreqThreshNode,
    EnvelopeNode, KalmanFilterNode
)

class NodeEditorWidget(QWidget):
    pipeline_changed = pyqtSignal(list) # Emits pipeline list
    state_changed = pyqtSignal(dict)    # Emits full graph state

    def __init__(self, parent=None, initial_graph_state=None):
        super().__init__(parent)
        self.initial_graph_state = initial_graph_state
        
        self.scene = NodeScene()
        self.view = NodeView(self.scene)
        
        layout = QHBoxLayout(self)
        
        # Left Palette
        palette_layout = QVBoxLayout()
        
        # File Operations
        palette_layout.addWidget(QLabel("<b>File</b>"))
        file_layout = QHBoxLayout()
        self.btn_new = QPushButton("New")
        self.btn_load = QPushButton("Load")
        self.btn_save = QPushButton("Save")
        
        self.btn_new.clicked.connect(self.on_new)
        self.btn_load.clicked.connect(self.on_load)
        self.btn_save.clicked.connect(self.on_save)
        
        file_layout.addWidget(self.btn_new)
        file_layout.addWidget(self.btn_load)
        file_layout.addWidget(self.btn_save)
        palette_layout.addLayout(file_layout)
        
        # Node Selection
        palette_layout.addWidget(QLabel("<b>Nodes</b>"))
        node_ctrl_layout = QHBoxLayout()
        
        self.node_combo = QComboBox()
        self.node_combo.addItems([
            "ROI", "Downsample", "Detrend", "Normalize",
            "Bandpass", "Lowpass", "Highpass", "Kalman Filter",
            "FK Filter", "FK Mag Threshold",
            "Time Threshold", "Freq Threshold",
            "Envelope"
        ])
        
        self.btn_add_node = QPushButton("Add Node")
        self.btn_add_node.clicked.connect(self.on_add_node_clicked)
        
        node_ctrl_layout.addWidget(self.node_combo)
        node_ctrl_layout.addWidget(self.btn_add_node)
        palette_layout.addLayout(node_ctrl_layout)
        
        palette_layout.addStretch()

        # Minimap
        palette_layout.addWidget(QLabel("<b>Global View</b>"))
        self.minimap = MinimapView(self.scene, self.view)
        palette_layout.addWidget(self.minimap)
        
        # Connect scrollbars
        self.view.horizontalScrollBar().valueChanged.connect(lambda: self.minimap.update_view())
        self.view.verticalScrollBar().valueChanged.connect(lambda: self.minimap.update_view())
        
        self.btn_apply = QPushButton("Apply Pipeline")
        self.btn_apply.setStyleSheet("background-color: #4CAF50; color: white; padding: 10px;")
        self.btn_apply.clicked.connect(self.on_apply)
        
        self.cb_auto_apply = QCheckBox("Auto Apply")
        
        palette_layout.addWidget(self.btn_apply)
        palette_layout.addWidget(self.cb_auto_apply)
        
        layout.addLayout(palette_layout)
        layout.addWidget(self.view)
        
        self.input_node = None
        self.output_node = None
        
        # Auto Apply Timer
        self.auto_apply_timer = QTimer()
        self.auto_apply_timer.setSingleShot(True)
        self.auto_apply_timer.timeout.connect(self.on_apply)
        
        # Connect Scene Structure Change
        self.scene.sig_structure_changed.connect(self.on_auto_apply_trigger)
        
        self.init_graph()
        
    def on_new(self):
        self.scene.clear()
        self.input_node = None
        self.output_node = None
        self.init_graph()
        
    def on_save(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Pipeline", "", "JSON Files (*.json)")
        if path:
            state = self.get_graph_state()
            try:
                with open(path, 'w') as f:
                    json.dump(state, f, indent=4)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to save file: {e}")

    def on_load(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load Pipeline", "", "JSON Files (*.json)")
        if path:
            try:
                with open(path, 'r') as f:
                    state = json.load(f)
                self.load_graph_state(state)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to load file: {e}")
        
    def init_graph(self):
        if self.initial_graph_state:
            self.load_graph_state(self.initial_graph_state)
            return

        self.input_node = InputNode()
        self.input_node.setPos(-200, 0)
        self.scene.addItem(self.input_node)
        
        self.output_node = OutputNode()
        self.output_node.setPos(600, 0)
        self.scene.addItem(self.output_node)
        
        self.connect_nodes(self.input_node, self.output_node)

    def on_auto_apply_trigger(self):
        if self.cb_auto_apply.isChecked():
            self.auto_apply_timer.start(100)

    def on_add_node_clicked(self):
        node_type = self.node_combo.currentText()
        self.add_node(node_type)

    def add_node(self, node_type, x=0, y=0):
        node = None
        if node_type == "ROI": node = ROINode()
        elif node_type == "Downsample": node = DownsampleNode()
        elif node_type == "Detrend": node = DetrendNode()
        elif node_type == "Normalize": node = NormalizeNode()
        elif node_type == "Bandpass": node = BandpassNode()
        elif node_type == "Lowpass": node = LowpassNode()
        elif node_type == "Highpass": node = HighpassNode()
        elif node_type == "Kalman Filter": node = KalmanFilterNode()
        elif node_type == "FK Filter": node = FKNode()
        elif node_type == "FK Mag Threshold": node = FKMagNode()
        elif node_type == "Time Threshold": node = TimeThreshNode()
        elif node_type == "Freq Threshold": node = FreqThreshNode()
        elif node_type == "Envelope": node = EnvelopeNode()
        
        if node:
            node.setPos(x, y)
            self.scene.addItem(node)
            
            # Connect parameter change
            node.sig_parameter_changed.connect(self.on_auto_apply_trigger)
            
            # Notify structure change
            self.on_auto_apply_trigger()
            
        return node

    def connect_nodes(self, node1, node2):
        if not node1.outputs or not node2.inputs:
            return
        
        socket1 = node1.outputs[0]
        socket2 = node2.inputs[0]
        
        edge = NodeEdge(self.scene, socket1, socket2)
        socket1.add_edge(edge)
        socket2.add_edge(edge)

    def on_apply(self):
        pipeline = self.get_pipeline()
        state = self.get_graph_state()
        self.pipeline_changed.emit(pipeline)
        self.state_changed.emit(state)

    def get_pipeline(self):
        pipeline = []
        
        # Find Input Node
        if not self.input_node:
            # Try to find it in scene items
            for item in self.scene.items():
                if isinstance(item, InputNode):
                    self.input_node = item
                    break
            if not self.input_node: return []
            
        if not self.input_node.outputs:
            return []
            
        current_socket = self.input_node.outputs[0]
        
        max_steps = 50
        steps = 0
        
        while steps < max_steps:
            if not current_socket.edges:
                break
                
            edge = current_socket.edges[0]
            next_socket = edge.dest_socket
            if not next_socket:
                break
                
            next_node = next_socket.node
            
            if isinstance(next_node, OutputNode):
                break
                
            config = next_node.get_config()
            pipeline.append(config)
            
            if next_node.outputs:
                current_socket = next_node.outputs[0]
            else:
                break
            
            steps += 1
            
        return pipeline

    def get_graph_state(self):
        nodes = []
        node_map = {} 
        
        for i, item in enumerate(self.scene.items()):
            if isinstance(item, NodeBlock):
                node_data = item.serialize()
                node_data['id'] = len(nodes)
                nodes.append(node_data)
                node_map[item] = len(nodes) - 1
                
        edges = []
        for item in self.scene.items():
            if isinstance(item, NodeEdge):
                if item.source_socket and item.dest_socket:
                    src_node_idx = node_map.get(item.source_socket.node)
                    dest_node_idx = node_map.get(item.dest_socket.node)
                    
                    if src_node_idx is not None and dest_node_idx is not None:
                        edges.append({
                            "source": src_node_idx,
                            "src_socket": item.source_socket.index,
                            "dest": dest_node_idx,
                            "dest_socket": item.dest_socket.index
                        })
                        
        return {"nodes": nodes, "edges": edges}

    def load_graph_state(self, state):
        self.scene.clear()
        
        nodes_data = state.get("nodes", [])
        edges_data = state.get("edges", [])
        
        created_nodes = {}
        
        for n_data in nodes_data:
            ntype = n_data["type"]
            x = n_data["x"]
            y = n_data["y"]
            
            node = None
            if ntype == "Input":
                node = InputNode()
                self.input_node = node
            elif ntype == "Output":
                node = OutputNode()
                self.output_node = node
            else:
                node = self.add_node(ntype)
            
            if node:
                node.setPos(x, y)
                if "config" in n_data:
                    node.set_config(n_data["config"])
                self.scene.addItem(node)
                created_nodes[n_data["id"]] = node
                
        for e_data in edges_data:
            src_node = created_nodes.get(e_data["source"])
            dest_node = created_nodes.get(e_data["dest"])
            
            if src_node and dest_node:
                src_sock_idx = e_data["src_socket"]
                dest_sock_idx = e_data["dest_socket"]
                
                src_socket = None
                for s in src_node.outputs:
                    if s.index == src_sock_idx:
                        src_socket = s
                        break
                        
                dest_socket = None
                for s in dest_node.inputs:
                    if s.index == dest_sock_idx:
                        dest_socket = s
                        break
                        
                if src_socket and dest_socket:
                    edge = NodeEdge(self.scene, src_socket, dest_socket)
                    src_socket.add_edge(edge)
                    dest_socket.add_edge(edge)

    def keyPressEvent(self, event):
        # Forward key events to scene for delete/copy/paste
        self.scene.keyPressEvent(event)
        super().keyPressEvent(event)
