from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

# --- Graphics Items ---

class NodeSocket(QGraphicsItem):
    def __init__(self, node, socket_type, index, is_input=False):
        super().__init__(node)
        self.node = node
        self.socket_type = socket_type
        self.index = index
        self.is_input = is_input
        self.radius = 6.0
        self.outline_width = 1.0
        self.edges = []
        
        self.setAcceptHoverEvents(True)
        self.setZValue(100) # Ensure socket is above node body
        
        # Position calculation
        y = node.title_height + node.padding + index * 20 + 10
        if is_input:
            self.setPos(0, y)
        else:
            self.setPos(node.width, y)

    def boundingRect(self):
        return QRectF(-self.radius - self.outline_width, -self.radius - self.outline_width,
                      2 * (self.radius + self.outline_width), 2 * (self.radius + self.outline_width))

    def paint(self, painter, option, widget):
        painter.setBrush(QBrush(QColor("#FF7700" if self.socket_type else "#0077FF")))
        painter.setPen(QPen(Qt.black, self.outline_width))
        painter.drawEllipse(-self.radius, -self.radius, 2 * self.radius, 2 * self.radius)
        
    def get_scene_pos(self):
        return self.mapToScene(0, 0)

    def add_edge(self, edge):
        self.edges.append(edge)

    def remove_edge(self, edge):
        if edge in self.edges:
            self.edges.remove(edge)

class NodeEdge(QGraphicsPathItem):
    def __init__(self, scene, source_socket=None, dest_socket=None):
        super().__init__()
        self.scene_ref = scene
        self.source_socket = source_socket
        self.dest_socket = dest_socket
        
        self.setZValue(-1)
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.scene_ref.addItem(self)
        self.update_path()
        
        # Notify structure change if this is a complete connection
        if self.source_socket and self.dest_socket:
             if hasattr(self.scene_ref, "sig_structure_changed"):
                 self.scene_ref.sig_structure_changed.emit()

    def update_path(self):
        if not self.source_socket:
            return

        start_pos = self.source_socket.get_scene_pos()
        if self.dest_socket:
            end_pos = self.dest_socket.get_scene_pos()
        else:
            # Dragging
            end_pos = self.end_pos if hasattr(self, 'end_pos') else start_pos

        path = QPainterPath(start_pos)
        
        dx = end_pos.x() - start_pos.x()
        dy = end_pos.y() - start_pos.y()
        
        ctrl1 = start_pos + QPointF(dx * 0.5, 0)
        ctrl2 = end_pos - QPointF(dx * 0.5, 0)
        
        path.cubicTo(ctrl1, ctrl2, end_pos)
        self.setPath(path)
        
    def paint(self, painter, option, widget):
        color = QColor("#FFFFA637") if self.isSelected() else Qt.white
        pen = QPen(color, 3)
        painter.setPen(pen)
        painter.drawPath(self.path())

    def shape(self):
        path_stroker = QPainterPathStroker()
        path_stroker.setWidth(10)
        return path_stroker.createStroke(self.path())

    def remove(self):
        if self.source_socket:
            self.source_socket.remove_edge(self)
        if self.dest_socket:
            self.dest_socket.remove_edge(self)
        self.scene_ref.removeItem(self)
        
        if hasattr(self.scene_ref, "sig_structure_changed"):
             self.scene_ref.sig_structure_changed.emit()

class NodeBlock(QGraphicsObject):
    sig_parameter_changed = pyqtSignal()

    def __init__(self, title="Node", parent=None):
        super().__init__(parent)
        self.title = title
        self.width = 180
        self.height = 100
        self.title_height = 24
        self.padding = 10
        
        self.inputs = []
        self.outputs = []
        
        self.content_widget = None
        self.proxy_widget = None
        
        # Flags
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)
        
        # UI Setup
        self.init_ui()

    def init_ui(self):
        self._title_color = Qt.white
        self._title_font = QFont("Ubuntu", 10)
        self._pen_default = QPen(QColor("#7F000000"))
        self._pen_selected = QPen(QColor("#FFFFA637"))
        self._brush_title = QBrush(QColor("#FF313131"))
        self._brush_background = QBrush(QColor("#E3212121"))

    def boundingRect(self):
        return QRectF(0, 0, self.width, self.height)

    def paint(self, painter, option, widget):
        # Title
        path_title = QPainterPath()
        path_title.setFillRule(Qt.WindingFill)
        path_title.addRoundedRect(0, 0, self.width, self.title_height, 5, 5)
        path_title.addRect(0, self.title_height - 5, self.width, 5)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._brush_title)
        painter.drawPath(path_title.simplified())
        
        # Content
        path_content = QPainterPath()
        path_content.setFillRule(Qt.WindingFill)
        path_content.addRoundedRect(0, self.title_height, self.width, self.height - self.title_height, 5, 5)
        path_content.addRect(0, self.title_height, self.width, 5)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._brush_background)
        painter.drawPath(path_content.simplified())
        
        # Outline
        path_outline = QPainterPath()
        path_outline.addRoundedRect(0, 0, self.width, self.height, 5, 5)
        painter.setPen(self._pen_selected if self.isSelected() else self._pen_default)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path_outline.simplified())
        
        # Title Text
        painter.setPen(self._title_color)
        painter.setFont(self._title_font)
        painter.drawText(QRectF(0, 0, self.width, self.title_height), Qt.AlignCenter, self.title)

    def add_socket(self, socket_type, index, is_input):
        socket = NodeSocket(self, socket_type, index, is_input)
        if is_input:
            self.inputs.append(socket)
        else:
            self.outputs.append(socket)
        return socket

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            for s in self.inputs + self.outputs:
                for e in s.edges:
                    e.update_path()
        return super().itemChange(change, value)
        
    def get_config(self):
        """Return dict of current parameters. Override in subclasses."""
        return {"type": self.title}

    def set_config(self, config):
        """Restore parameters from dict. Override in subclasses."""
        pass

    def serialize(self):
        """Return full state for serialization"""
        return {
            "type": self.title,
            "x": self.pos().x(),
            "y": self.pos().y(),
            "config": self.get_config()
        }

    def remove(self):
        """Remove node and all connected edges"""
        for socket in self.inputs + self.outputs:
            while socket.edges:
                edge = socket.edges[0]
                edge.remove()
        
        scene = self.scene()
        if scene:
            scene.removeItem(self)
            if hasattr(scene, "sig_structure_changed"):
                scene.sig_structure_changed.emit()
            
    def set_content(self, widget):
        self.content_widget = widget
        self.content_widget.setStyleSheet("background: transparent; color: white;")
        self.proxy_widget = QGraphicsProxyWidget(self)
        self.proxy_widget.setWidget(self.content_widget)
        self.proxy_widget.setPos(10, self.title_height + 10)
        self.proxy_widget.resize(self.width - 20, self.height - self.title_height - 20)
        
        # Auto-connect signals
        self._connect_signals_recursive(widget)

    def _connect_signals_recursive(self, widget):
        # Connect specific widget types to parameter change signal
        widgets = widget.findChildren(QWidget) + [widget]
        for child in widgets:
            if isinstance(child, (QSpinBox, QDoubleSpinBox)):
                child.valueChanged.connect(self._on_param_changed)
            elif isinstance(child, QComboBox):
                child.currentIndexChanged.connect(self._on_param_changed)
            elif isinstance(child, QCheckBox):
                child.stateChanged.connect(self._on_param_changed)
            elif isinstance(child, QLineEdit):
                child.textChanged.connect(self._on_param_changed)

    def _on_param_changed(self, *args):
        self.sig_parameter_changed.emit()


class NodeScene(QGraphicsScene):
    sig_structure_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setBackgroundBrush(QBrush(QColor("#212121")))
        self.grid_size = 20
        self.setSceneRect(-5000, -5000, 10000, 10000)

    def drawBackground(self, painter, rect):
        super().drawBackground(painter, rect)
        
        # Grid
        left = int(rect.left()) - (int(rect.left()) % self.grid_size)
        top = int(rect.top()) - (int(rect.top()) % self.grid_size)
        
        lines = []
        for x in range(left, int(rect.right()), self.grid_size):
            lines.append(QLineF(x, rect.top(), x, rect.bottom()))
        for y in range(top, int(rect.bottom()), self.grid_size):
            lines.append(QLineF(rect.left(), y, rect.right(), y))
            
        painter.setPen(QPen(QColor("#2f2f2f")))
        painter.drawLines(lines)

    def keyPressEvent(self, event):
        # Avoid deleting node when editing text in spinbox
        if self.focusItem() and isinstance(self.focusItem(), QGraphicsProxyWidget):
            super().keyPressEvent(event)
            return
            
        if event.key() == Qt.Key_Delete or event.key() == Qt.Key_Backspace:
            for item in self.selectedItems():
                if isinstance(item, NodeEdge):
                    item.remove()
                elif isinstance(item, NodeBlock):
                    # We might want to prevent deleting Input/Output nodes in the editor logic, 
                    # but base class shouldn't know about specific types if possible.
                    # Checking title is one way.
                    if item.title in ["Input", "Output"]:
                        continue
                    item.remove()
        super().keyPressEvent(event)

class NodeView(QGraphicsView):
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.HighQualityAntialiasing)
        self.setRenderHint(QPainter.TextAntialiasing)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        
        self.editing_edge = None
        self.zoom = 1.0

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            zoom_factor = 1.25 if event.angleDelta().y() > 0 else 0.8
            self.scale(zoom_factor, zoom_factor)
            self.zoom *= zoom_factor
        elif event.modifiers() & Qt.ShiftModifier:
            # Shift + Wheel = Horizontal Scroll (Panning)
            delta = event.angleDelta().y()
            # Scroll horizontally
            h_bar = self.horizontalScrollBar()
            v_bar = self.verticalScrollBar()
            if h_bar:
                h_bar.setValue(h_bar.value() - delta)
            # If we want 2D panning with wheel, we can't really do both with one wheel.
            # But usually Shift+Wheel is Horizontal.
            event.accept()
        else:
            super().wheelEvent(event)
            
    def mousePressEvent(self, event):
        item = self.itemAt(event.pos())
        
        # If clicking on a widget (ProxyWidget), disable RubberBandDrag to allow interaction
        if isinstance(item, QGraphicsProxyWidget) or (item and item.parentItem() and isinstance(item.parentItem(), QGraphicsProxyWidget)):
            self.setDragMode(QGraphicsView.NoDrag)
            # Ensure focus
            if isinstance(item, QGraphicsProxyWidget):
                 item.widget().setFocus()
            elif item and item.parentItem() and isinstance(item.parentItem(), QGraphicsProxyWidget):
                 item.parentItem().widget().setFocus()
            super().mousePressEvent(event)
            return

        if item is None:
             self.setDragMode(QGraphicsView.RubberBandDrag)
        else:
             self.setDragMode(QGraphicsView.NoDrag)
             
        if isinstance(item, NodeSocket):
            if not item.is_input:
                # Start dragging edge
                self.editing_edge = NodeEdge(self.scene(), item, None)
                self.editing_edge.end_pos = self.mapToScene(event.pos())
                self.editing_edge.update_path()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.editing_edge:
            self.editing_edge.end_pos = self.mapToScene(event.pos())
            self.editing_edge.update_path()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.editing_edge:
            item = self.itemAt(event.pos())
            if isinstance(item, NodeSocket) and item.is_input:
                # Complete connection
                self.editing_edge.dest_socket = item
                self.editing_edge.update_path()
                item.add_edge(self.editing_edge)
                self.editing_edge.source_socket.add_edge(self.editing_edge)
            else:
                self.editing_edge.remove()
            self.editing_edge = None
            
            # Notify structure change
            if hasattr(self.scene(), "sig_structure_changed"):
                self.scene().sig_structure_changed.emit()
        
        super().mouseReleaseEvent(event)
        
        # Auto-connect/Insert logic after drop
        # Check selected nodes
        for item in self.scene().selectedItems():
            if isinstance(item, NodeBlock):
                # Try socket-to-socket auto-connect first
                connected = self.check_auto_connect(item)
                # If no direct connection, try auto-insert into edge
                if not connected:
                    self.check_auto_insert(item)

    def check_auto_connect(self, node):
        # Search radius for auto-connect
        SEARCH_RADIUS = 20.0
        did_connect = False
        
        for socket in node.inputs + node.outputs:
            socket_pos = socket.get_scene_pos()
            
            # Find nearby items
            candidates = []
            for item in self.scene().items():
                if isinstance(item, NodeSocket) and item != socket and item.node != node:
                    dist = (item.get_scene_pos() - socket_pos).manhattanLength()
                    if dist < SEARCH_RADIUS:
                        candidates.append(item)
            
            for other in candidates:
                # Check compatibility (one input, one output)
                if socket.is_input != other.is_input:
                    # Identify source and dest
                    src = other if not other.is_input else socket
                    dest = socket if socket.is_input else other
                    
                    # Avoid duplicate connections
                    already_connected = False
                    for edge in src.edges:
                        if edge.dest_socket == dest:
                            already_connected = True
                            break
                    
                    if not already_connected:
                        # Create new edge
                        edge = NodeEdge(self.scene(), src, dest)
                        src.add_edge(edge)
                        dest.add_edge(edge)
                        did_connect = True
                        # Only connect to one valid candidate per socket
                        break
        return did_connect

    def check_auto_insert(self, node):
        """
        Check if the node is dropped onto an existing edge.
        If so, insert the node into the edge.
        """
        # Node must have at least one input and one output to be inserted
        if not node.inputs or not node.outputs:
            return False
            
        # Find colliding edges
        colliding_items = self.scene().collidingItems(node)
        edges = [item for item in colliding_items if isinstance(item, NodeEdge)]
        
        if not edges:
            return False
            
        target_edge = None
        
        # Heuristic: Find the best edge to insert into
        # We prefer an edge that the node is "visually crossing"
        # For now, we take the first edge that isn't connected to the node itself
        for edge in edges:
            if edge.source_socket.node == node or edge.dest_socket.node == node:
                continue
            if edge.source_socket and edge.dest_socket:
                target_edge = edge
                break
        
        if target_edge:
            # Perform insertion
            src_socket = target_edge.source_socket
            dest_socket = target_edge.dest_socket
            
            # Use first input and first output
            node_input = node.inputs[0]
            node_output = node.outputs[0]
            
            # Remove old edge
            target_edge.remove()
            
            # Create Source -> Node Input
            edge1 = NodeEdge(self.scene(), src_socket, node_input)
            src_socket.add_edge(edge1)
            node_input.add_edge(edge1)
            
            # Create Node Output -> Dest
            edge2 = NodeEdge(self.scene(), node_output, dest_socket)
            node_output.add_edge(edge2)
            dest_socket.add_edge(edge2)
            
            return True
            
        return False


class MinimapView(QGraphicsView):
    def __init__(self, scene, main_view, parent=None):
        super().__init__(scene, parent)
        self.main_view = main_view
        self.setInteractive(True)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFixedSize(200, 200)
        self.setStyleSheet("border: 1px solid #555;")
        
        # Scale to fit scene
        self.fitInView(scene.sceneRect(), Qt.KeepAspectRatio)
        
    def drawForeground(self, painter, rect):
        if not self.main_view: return
        
        # Calculate viewport rect in scene coords
        viewport_rect = self.main_view.mapToScene(self.main_view.viewport().rect()).boundingRect()
        
        painter.save()
        painter.setPen(QPen(Qt.red, 0)) # Cosmetic pen
        painter.setPen(QPen(Qt.red, 50)) 
        painter.setBrush(QColor(255, 0, 0, 50))
        painter.drawRect(viewport_rect)
        painter.restore()
        
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            scene_pos = self.mapToScene(event.pos())
            self.main_view.centerOn(scene_pos)
            self.scene().update() # Redraw to show updated rect
        super().mousePressEvent(event)
        
    def update_view(self):
        self.scene().update()
