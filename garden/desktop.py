"""A wallpaper must remain managed by the desktop's window manager.

In particular, override-redirect + XLowerWindow only changes the X server
stack. Mutter can still composite that window above applications and panels.
"""
from __future__ import annotations
from PySide6.QtCore import Qt


class DesktopLayer:
    def flags(self):
        return (Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnBottomHint |
                Qt.WindowDoesNotAcceptFocus | Qt.WindowTransparentForInput)

    def lower(self, window):
        if window.isVisible():
            # Let Qt send the stacking request to the window manager. Never
            # bypass it, even when a desktop-icons window refuses to restack.
            window.lower()

    def close(self):
        # Kept as a lifecycle hook; there is no separate native connection.
        pass
