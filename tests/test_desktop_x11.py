"""Opt-in compositor regression: HARUNIWA_X11_TESTS=1 python -m unittest tests.test_desktop_x11."""
import os
from pathlib import Path
import subprocess
import sys
import unittest


@unittest.skipUnless(os.environ.get('HARUNIWA_X11_TESTS') == '1' and os.environ.get('DISPLAY'),
                     'requires an explicit real X11 desktop integration run')
class DesktopX11Tests(unittest.TestCase):
    def test_managed_wallpaper_preserves_application_and_panel(self):
        code = r'''
import ctypes as C, ctypes.util, subprocess, tempfile
from pathlib import Path
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QApplication, QWidget
from garden.window import PondWindow
app=QApplication([])
app.setQuitOnLastWindowClosed(False)
x=C.CDLL(ctypes.util.find_library('X11'))
x.XOpenDisplay.argtypes=[C.c_char_p]; x.XOpenDisplay.restype=C.c_void_p
x.XFree.argtypes=[C.c_void_p]; x.XCloseDisplay.argtypes=[C.c_void_p]
shape=C.CDLL(ctypes.util.find_library('Xext'))
shape.XShapeGetRectangles.argtypes=[C.c_void_p,C.c_ulong,C.c_int,C.POINTER(C.c_int),C.POINTER(C.c_int)]
shape.XShapeGetRectangles.restype=C.c_void_p
d=x.XOpenDisplay(None)
failures=[]
screen=app.primaryScreen(); geom=screen.geometry(); available=screen.availableGeometry()
# A distinct solid canvas ensures the regression cannot pass by coincidence.
class TestWallpaper(PondWindow):
    def paintEvent(self, event):
        painter=QPainter(self); painter.fillRect(self.rect(),QColor('#df189a'))
probe=QWidget(); probe.setWindowTitle('Haruniwa temporary compositor test')
probe.setStyleSheet('background: #17bb63;'); probe.setGeometry(available.x()+100,available.y()+120,240,100)
probe.show()
window=None
baseline=None
panel_height=max(0,available.top()-geom.top())
def screenshot():
    return screen.grabWindow(0,geom.x(),geom.y(),geom.width(),geom.height()).toImage()
with tempfile.TemporaryDirectory() as directory:
    def launch():
        global window, baseline
        baseline=screenshot()
        window=TestWallpaper(Path(directory)/'state.json')
        window.show_layers()
        window.show_note()
        window.note.editor.setPlainText('临时原生便签')
    def check():
        try:
            wid=str(int(window.winId()))
            info=subprocess.check_output(['xwininfo','-id',wid],text=True)
            assert 'Override Redirect State: no' in info, info
            props=subprocess.check_output(['xprop','-id',wid,'_NET_WM_WINDOW_TYPE','_NET_WM_STATE'],text=True)
            assert '_NET_WM_WINDOW_TYPE_DESKTOP' in props, props
            assert '_NET_WM_STATE_BELOW' in props, props
            stacking=subprocess.check_output(['xprop','-root','_NET_CLIENT_LIST_STACKING'],text=True)
            ids=[int(item.strip(),16) for item in stacking.split('#',1)[1].split(',')]
            assert ids.index(int(window.winId())) < ids.index(int(probe.winId())), stacking
            # Read composed pixels, not the XQueryTree order that missed the bug.
            actual=screenshot(); ratio=actual.devicePixelRatio()
            center=probe.mapToGlobal(probe.rect().center())-geom.topLeft()
            color=actual.pixelColor(int(center.x()*ratio),int(center.y()*ratio))
            assert color.name() == '#17bb63', 'application covered: '+color.name()
            if panel_height:
                width=actual.width(); height=int(panel_height*ratio)
                unchanged=sum(actual.pixel(x,y)==baseline.pixel(x,y)
                              for y in range(height) for x in range(width))
                assert unchanged/(width*height) > .90, 'top panel was covered'
            count=C.c_int(); ordering=C.c_int()
            rectangles=shape.XShapeGetRectangles(d,int(window.winId()),2,C.byref(count),C.byref(ordering))
            if rectangles: x.XFree(rectangles)
            assert count.value == 0, 'wallpaper intercepts desktop clicks'
            assert window.note.isVisible()
        except BaseException as error:
            failures.append(repr(error))
        finally:
            window.request_exit()
    QTimer.singleShot(700,launch)
    QTimer.singleShot(3000,check)  # Includes the periodic layer-maintenance pass.
    QTimer.singleShot(7000,lambda: app.exit(91))
    result=app.exec()
    assert result == 0 and not failures, failures
    assert not window.isVisible() and not window.note.isVisible()
    assert not window.layer_timer.isActive()
    print(f'Managed desktop; application pixels visible; panel comparison height={panel_height}; empty input region; clean exit')
x.XCloseDisplay(d)
'''
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run([sys.executable, '-c', code], cwd=root,
                                env={**os.environ, 'QT_QPA_PLATFORM': 'xcb'},
                                capture_output=True, text=True, timeout=12)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
