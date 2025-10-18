from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt, QSize, QPoint, QPointF
from PyQt5.QtGui import QPainter, QPixmap, QColor, QTransform

class PDFPreviewWidget(QWidget):
    """Widget for displaying PDF previews with zoom and pan functionality."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap = None
        self._borderless = False
        
        # Zoom and pan properties
        self._zoom_factor = 1.0
        self._min_zoom = 0.5
        self._max_zoom = 5.0
        self._pan_offset = QPointF(0, 0)
        self._last_pan_point = QPoint()
        self._is_panning = False
        
        # Touch/mouse tracking
        self.setMouseTracking(True)
        
        self.setStyleSheet("""
            PDFPreviewWidget {
                background-color: #c4c4c4;
                border: 1px solid #ddd;
                border-radius: 4px;
            }
        """)

    def setPixmap(self, pixmap):
        """Sets the pixmap to display."""
        self._pixmap = pixmap
        # Reset zoom and pan when new pixmap is set
        self._zoom_factor = 1.0
        self._pan_offset = QPointF(0, 0)
        self.update()

    def clear(self):
        """Clears the current pixmap."""
        self._pixmap = None
        self._zoom_factor = 1.0
        self._pan_offset = QPointF(0, 0)
        self.update()

    def setBorderless(self, borderless=True):
        """Enable/disable borderless mode for maximum content area."""
        self._borderless = borderless
        if borderless:
            self.setStyleSheet("""
                PDFPreviewWidget {
                    background-color: #c4c4c4;
                    border: none;
                }
            """)
        else:
            self.setStyleSheet("""
                PDFPreviewWidget {
                    background-color: #c4c4c4;
                    border: 1px solid #ddd;
                    border-radius: 4px;
                }
            """)

    def zoomIn(self):
        """Zooms in by 25%."""
        self._zoom_factor = min(self._zoom_factor * 1.25, self._max_zoom)
        self.update()

    def zoomOut(self):
        """Zooms out by 25%."""
        self._zoom_factor = max(self._zoom_factor / 1.25, self._min_zoom)
        self.update()

    def resetZoom(self):
        """Resets zoom to 100%."""
        self._zoom_factor = 1.0
        self._pan_offset = QPointF(0, 0)
        self.update()

    def wheelEvent(self, event):
        """Handles mouse wheel events for zooming."""
        if event.angleDelta().y() > 0:
            self.zoomIn()
        else:
            self.zoomOut()
        event.accept()

    def mousePressEvent(self, event):
        """Handles mouse press events for panning."""
        # Disable panning: do nothing special on mouse press
        self.setCursor(Qt.ArrowCursor)

    def mouseMoveEvent(self, event):
        """Handles mouse move events for panning."""
        # Disable panning: ignore drag and keep cursor default
        self.setCursor(Qt.ArrowCursor)

    def mouseReleaseEvent(self, event):
        """Handles mouse release events."""
        if event.button() == Qt.LeftButton:
            self._is_panning = False
            self.setCursor(Qt.ArrowCursor)

    def paintEvent(self, event):
        """Paints the widget with the current pixmap."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Fill background with container tint so page edges are visible
        painter.fillRect(self.rect(), QColor(196, 196, 196))
        
        if self._pixmap is None:
            return
        
        # Calculate scaled pixmap size: fit entire page to widget by default
        pixmap_size = self._pixmap.size()
        widget_rect = self.rect()
        if self._zoom_factor == 1.0:
            # Fit-to-widget behavior at default zoom
            scale_w = widget_rect.width() / max(1, pixmap_size.width())
            scale_h = widget_rect.height() / max(1, pixmap_size.height())
            fit_scale = min(scale_w, scale_h)
            scaled_size = QSize(
                int(pixmap_size.width() * fit_scale),
                int(pixmap_size.height() * fit_scale)
            )
        else:
            scaled_size = QSize(
                int(pixmap_size.width() * self._zoom_factor),
                int(pixmap_size.height() * self._zoom_factor)
            )
        
        # Calculate position to center the pixmap
        # Center image without panning
        x = (widget_rect.width() - scaled_size.width()) // 2
        y = (widget_rect.height() - scaled_size.height()) // 2
        
        # Draw the pixmap
        painter.drawPixmap(x, y, scaled_size.width(), scaled_size.height(), self._pixmap)

    def getZoomFactor(self):
        """Returns the current zoom factor."""
        return self._zoom_factor

    def sizeHint(self):
        """Returns the preferred size of the widget."""
        if self._pixmap:
            return self._pixmap.size()
        # Encourage tall previews so items fill the preview container height
        return QSize(360, 800)
