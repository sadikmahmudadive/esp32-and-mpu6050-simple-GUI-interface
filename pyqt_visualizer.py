"""
PyQt5 + pyqtgraph OpenGL visualizer for MPU6050 (ESP32)
- 3D plane (mesh) that rotates according to roll/pitch/yaw
- Numeric readouts and meters
- Serial and mock modes
- Simple smoothing and trail (history) visualization

Usage:
    python pyqt_visualizer.py --port COM3
    python pyqt_visualizer.py --mock

"""

import sys
import argparse
import math
import threading
import time
from collections import deque

import numpy as np
from pyqtgraph.Qt import QtWidgets, QtCore, QtGui
import pyqtgraph as pg
import pyqtgraph.opengl as gl
import serial


class SerialThread(QtCore.QThread):
    line_received = QtCore.pyqtSignal(str)

    def __init__(self, port, baud=115200, parent=None):
        super().__init__(parent)
        self.port = port
        self.baud = baud
        self._running = True

    def run(self):
        try:
            ser = serial.Serial(self.port, self.baud, timeout=0.1)
        except Exception as e:
            print('Serial open failed:', e)
            return
        buf = b''
        while self._running:
            try:
                data = ser.read(256)
                if data:
                    buf += data
                    while b'\n' in buf:
                        line, buf = buf.split(b'\n', 1)
                        try:
                            self.line_received.emit(line.decode('utf-8').strip())
                        except Exception:
                            pass
                else:
                    time.sleep(0.01)
            except Exception as e:
                print('Serial read error:', e)
                break
        try:
            ser.close()
        except Exception:
            pass

    def stop(self):
        self._running = False
        self.wait()


class PyQtVisualizer(QtWidgets.QWidget):
    def __init__(self, port=None, mock=False):
        super().__init__()
        self.setWindowTitle('MPU6050 PyQt Visualizer')
        self.resize(900, 600)

        # Layout
        h = QtWidgets.QHBoxLayout()
        self.setLayout(h)

        # 3D view
        self.view = gl.GLViewWidget()
        self.view.opts['distance'] = 8
        h.addWidget(self.view, 3)

        # Right-side controls
        right = QtWidgets.QVBoxLayout()
        h.addLayout(right, 1)

        # Readouts
        self.roll_label = QtWidgets.QLabel('Roll: 0.00')
        self.pitch_label = QtWidgets.QLabel('Pitch: 0.00')
        self.yaw_label = QtWidgets.QLabel('Yaw: 0.00')
        right.addWidget(self.roll_label)
        right.addWidget(self.pitch_label)
        right.addWidget(self.yaw_label)

        # Meters (progress bars)
        self.roll_meter = QtWidgets.QProgressBar(); self.roll_meter.setRange(-180, 180)
        self.pitch_meter = QtWidgets.QProgressBar(); self.pitch_meter.setRange(-180, 180)
        self.yaw_meter = QtWidgets.QProgressBar(); self.yaw_meter.setRange(-180, 180)
        right.addWidget(self.roll_meter)
        right.addWidget(self.pitch_meter)
        right.addWidget(self.yaw_meter)

        # Buttons
        self.mock_btn = QtWidgets.QPushButton('Toggle Mock')
        self.calib_btn = QtWidgets.QPushButton('Calibrate')
        right.addWidget(self.mock_btn)
        right.addWidget(self.calib_btn)

        # GL items: plane mesh
        verts, faces = self._make_plane_mesh()
        meshdata = gl.MeshData(vertexes=verts, faces=faces)
        self.plane = gl.GLMeshItem(meshdata=meshdata, smooth=True, shader='shaded', color=(0.2,0.6,1,1))
        self.view.addItem(self.plane)

        # axes
        gx = gl.GLGridItem(); gx.rotate(90, 0,1,0); gx.setSize(6,6); self.view.addItem(gx)
        gy = gl.GLGridItem(); gy.rotate(90, 1,0,0); gy.setSize(6,6); self.view.addItem(gy)

        # history trail as small translucent planes
        self.trail = deque(maxlen=40)

        # Data
        self.latest = [0.0,0.0,0.0]
        self.smoothed = [0.0,0.0,0.0]
        self.alpha = 0.25
        self.offsets = [0.0,0.0,0.0]

        # Serial
        self.serial_thread = None
        self.mock = mock
        self.port = port
        if not mock and port:
            self.start_serial(port)

        # connections
        self.mock_btn.clicked.connect(self.toggle_mock)
        self.calib_btn.clicked.connect(self.calibrate)

        # Timer
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_visual)
        self.timer.start(16)

        # Mock generator timer
        self.mock_timer = 0.0

    def _make_plane_mesh(self):
        # Create a simple low-poly airplane-like plane centered at origin
        verts = np.array([
            [-1.1, 0.0,  0.3],  # left nose
            [ 1.1, 0.0,  0.3],  # right nose
            [-0.6, 0.0, -0.4],  # left tail
            [ 0.6, 0.0, -0.4],  # right tail
            [ 0.0, 0.2, -0.8],  # vertical tail top
        ], dtype=float)
        faces = np.array([
            [0,1,2], [1,3,2],  # main quad
            [2,3,4]  # tail
        ], dtype=int)
        return verts, faces

    def start_serial(self, port):
        if self.serial_thread:
            self.serial_thread.stop()
        self.serial_thread = SerialThread(port)
        self.serial_thread.line_received.connect(self.on_line)
        self.serial_thread.start()

    def stop_serial(self):
        if self.serial_thread:
            self.serial_thread.stop()
            self.serial_thread = None

    def on_line(self, line):
        parts = line.split(',')
        if len(parts) == 3:
            try:
                r = float(parts[0]); p = float(parts[1]); y = float(parts[2])
                self.latest = [r,p,y]
            except ValueError:
                pass

    def toggle_mock(self):
        self.mock = not self.mock
        if self.mock:
            self.stop_serial()

    def calibrate(self):
        self.offsets = self.smoothed.copy()

    def update_visual(self):
        # mock data
        if self.mock:
            t = time.time(); self.latest[0] = math.sin(t*0.8)*45; self.latest[1] = math.sin(t*0.6)*35; self.latest[2] = math.sin(t*0.5)*90

        # smoothing
        for i in range(3):
            self.smoothed[i] = self.alpha * self.latest[i] + (1-self.alpha) * self.smoothed[i]
            val = self.smoothed[i] - self.offsets[i]

        # apply rotation to plane: note pyqtgraph GL uses right-handed coordinates
        rx = np.deg2rad(self.smoothed[1])
        ry = np.deg2rad(self.smoothed[0])
        rz = np.deg2rad(self.smoothed[2])
        # build rotation matrix (ZYX)
        Rz = np.array([[math.cos(rz), -math.sin(rz), 0],[math.sin(rz), math.cos(rz),0],[0,0,1]])
        Ry = np.array([[math.cos(ry),0,math.sin(ry)],[0,1,0],[-math.sin(ry),0,math.cos(ry)]])
        Rx = np.array([[1,0,0],[0,math.cos(rx),-math.sin(rx)],[0,math.sin(rx),math.cos(rx)]])
        R = Rz.dot(Ry).dot(Rx)
        verts, faces = self._make_plane_mesh()
        verts = verts.dot(R.T)
        self.plane.setMeshData(vertexes=verts, faces=faces)

        # update trail
        if not self.mock:
            # append a translucent copy
            md = gl.MeshData(vertexes=verts.copy(), faces=faces)
            item = gl.GLMeshItem(meshdata=md, smooth=True, color=(0.2,0.6,1,0.25))
            self.view.addItem(item)
            self.trail.append(item)
            if len(self.trail) > 40:
                old = self.trail.popleft()
                self.view.removeItem(old)

        # update readouts
        self.roll_label.setText(f'Roll: {self.smoothed[0]:.2f}')
        self.pitch_label.setText(f'Pitch: {self.smoothed[1]:.2f}')
        self.yaw_label.setText(f'Yaw: {self.smoothed[2]:.2f}')
        self.roll_meter.setValue(int(self.smoothed[0]))
        self.pitch_meter.setValue(int(self.smoothed[1]))
        self.yaw_meter.setValue(int(self.smoothed[2]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port','-p',help='Serial port (COM3)')
    parser.add_argument('--mock',action='store_true')
    args = parser.parse_args()

    app = QtWidgets.QApplication(sys.argv)
    w = PyQtVisualizer(port=args.port, mock=args.mock)
    w.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
