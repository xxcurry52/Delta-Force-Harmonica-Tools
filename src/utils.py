from PySide6.QtCore import QRectF
from PySide6.QtGui import QPainterPath


def square_plate_corner(path, w, h, corner, r=12.0):
    x = 0.5 if "l" in corner else w - 0.5 - r
    y = 0.5 if "t" in corner else h - 0.5 - r
    notch = QPainterPath()
    notch.addRect(QRectF(x, y, r, r))
    return path.united(notch.subtracted(path))
