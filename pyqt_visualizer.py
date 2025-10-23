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

import os
import numpy as np

# Reduce noisy Qt font warnings (must be set before importing Qt modules)
os.environ.setdefault('QT_LOGGING_RULES', 'qt.qpa.fonts.warning=false;qt.qpa.fonts.info=false')

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
        # Serial port chooser
        self.port_box = QtWidgets.QComboBox()
        self.refresh_btn = QtWidgets.QPushButton('Refresh Ports')
        self.connect_btn = QtWidgets.QPushButton('Connect')
        self.disconnect_btn = QtWidgets.QPushButton('Disconnect')
        right.addWidget(self.port_box)
        right.addWidget(self.refresh_btn)
        right.addWidget(self.connect_btn)
        right.addWidget(self.disconnect_btn)
        # Launcher button for Ursina visualizer
        self.launch_ursina_btn = QtWidgets.QPushButton('Run Ursina visualizer')
        right.addWidget(self.launch_ursina_btn)
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
        # quaternion for smooth rotation (w, x, y, z)
        self.current_quat = np.array([1.0, 0.0, 0.0, 0.0])

        # Serial
        self.serial_thread = None
        self.mock = mock
        self.port = port
        if not mock and port:
            self.start_serial(port)

        # connections
        self.mock_btn.clicked.connect(self.toggle_mock)
        self.calib_btn.clicked.connect(self.calibrate)
        self.refresh_btn.clicked.connect(self.refresh_ports)
        self.connect_btn.clicked.connect(self.ui_connect)
        self.disconnect_btn.clicked.connect(self.ui_disconnect)
        self.launch_ursina_btn.clicked.connect(self.launch_ursina)

        # initial port list
        self.refresh_ports()

        # Timer
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_visual)
        self.timer.start(16)

        # Mock generator timer
        self.mock_timer = 0.0

    # --- Quaternion helpers for smooth rotation ---
    def _quat_from_euler(self, roll, pitch, yaw):
        # roll (x), pitch (y), yaw (z) in radians
        cr = math.cos(roll/2)
        sr = math.sin(roll/2)
        cp = math.cos(pitch/2)
        sp = math.sin(pitch/2)
        cy = math.cos(yaw/2)
        sy = math.sin(yaw/2)
        # ZYX order
        w = cy*cp*cr + sy*sp*sr
        x = cy*cp*sr - sy*sp*cr
        y = cy*sp*cr + sy*cp*sr
        z = sy*cp*cr - cy*sp*sr
        return np.array([w, x, y, z])

    def _quat_slerp(self, q0, q1, t):
        # Spherical linear interpolation
        dot = np.dot(q0, q1)
        if dot < 0.0:
            q1 = -q1
            dot = -dot
        DOT_THRESHOLD = 0.9995
        if dot > DOT_THRESHOLD:
            # linear fallback
            result = q0 + t*(q1 - q0)
            return result/np.linalg.norm(result)
        theta_0 = math.acos(dot)
        theta = theta_0 * t
        q2 = q1 - q0*dot
        q2 = q2 / np.linalg.norm(q2)
        return q0*math.cos(theta) + q2*math.sin(theta)

    def _quat_to_matrix(self, q):
        # convert quaternion to 3x3 rotation matrix
        w,x,y,z = q
        return np.array([
            [1-2*(y*y+z*z), 2*(x*y - z*w), 2*(x*z + y*w)],
            [2*(x*y + z*w), 1-2*(x*x+z*z), 2*(y*z - x*w)],
            [2*(x*z - y*w), 2*(y*z + x*w), 1-2*(x*x+y*y)]
        ])

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
        self.port = port
        self.connect_btn.setEnabled(False)
        self.disconnect_btn.setEnabled(True)

    def stop_serial(self):
        if self.serial_thread:
            self.serial_thread.stop()
            self.serial_thread = None
        self.connect_btn.setEnabled(True)
        self.disconnect_btn.setEnabled(False)

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
        self.mock_btn.setText('Toggle Mock (On)' if self.mock else 'Toggle Mock')

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

        # apply rotation to plane using quaternion slerp for smoothness
        roll_rad = math.radians(self.smoothed[0])
        pitch_rad = math.radians(self.smoothed[1])
        yaw_rad = math.radians(self.smoothed[2])
        target_q = self._quat_from_euler(roll_rad, pitch_rad, yaw_rad)
        # slerp factor (use alpha to control responsiveness)
        slerp_t = max(0.02, 1.0 - self.alpha)
        new_q = self._quat_slerp(self.current_quat, target_q, slerp_t)
        new_q = new_q / np.linalg.norm(new_q)
        self.current_quat = new_q
        R = self._quat_to_matrix(self.current_quat)
        verts, faces = self._make_plane_mesh()
        verts = verts.dot(R.T)
        # update mesh with rotated vertices
        self.plane.setMeshData(vertexes=verts, faces=faces)

        # update trail
        if not self.mock:
            md = gl.MeshData(vertexes=verts.copy(), faces=faces)
            alpha_val = 0.35
            item = gl.GLMeshItem(meshdata=md, smooth=True, color=(0.2,0.6,1,alpha_val))
            item.setGLOptions('translucent')
            self.view.addItem(item)
            self.trail.append(item)
            # fade trail items progressively
            n = len(self.trail)
            for idx, it in enumerate(self.trail):
                frac = (idx+1)/n
                try:
                    it.opts['color'] = (0.2, 0.6, 1.0, alpha_val*(1-frac))
                except Exception:
                    pass
            if len(self.trail) > self.trail.maxlen:
                old = self.trail.popleft()
                try:
                    self.view.removeItem(old)
                except Exception:
                    pass

        # update readouts
        self.roll_label.setText(f'Roll: {self.smoothed[0]:.2f}')
        self.pitch_label.setText(f'Pitch: {self.smoothed[1]:.2f}')
        self.yaw_label.setText(f'Yaw: {self.smoothed[2]:.2f}')
        self.roll_meter.setValue(int(self.smoothed[0]))
        self.pitch_meter.setValue(int(self.smoothed[1]))
        self.yaw_meter.setValue(int(self.smoothed[2]))

    def refresh_ports(self):
        # List available serial ports
        try:
            from serial.tools import list_ports
            ports = [p.device for p in list_ports.comports()]
        except Exception:
            ports = []
        self.port_box.clear()
        self.port_box.addItems(ports)

    def ui_connect(self):
        port = self.port_box.currentText()
        if port:
            self.mock = False
            self.start_serial(port)

    def ui_disconnect(self):
        self.stop_serial()

    def launch_ursina(self):
        # Launch the existing python_visualizer.py as a subprocess
        import subprocess
        script = r"d:\Code\Arduino\ESP32\MPU6050 with GUI\python_visualizer.py"
        args = [sys.executable, script]
        if self.mock:
            args.append('--mock')
        else:
            port = self.port_box.currentText()
            if port:
                args += ["--port", port]
        try:
            subprocess.Popen(args, creationflags=0)
            QtWidgets.QMessageBox.information(self, 'Launched', 'Ursina visualizer launched.')
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, 'Error', f'Failed to launch: {e}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port','-p',help='Serial port (COM3)')
    parser.add_argument('--mock',action='store_true')
    args = parser.parse_args()

    app = QtWidgets.QApplication(sys.argv)
    # Set a safe default system font to avoid missing-font warnings
    try:
        app.setFont(QtGui.QFont("Segoe UI", 9))
    except Exception:
        pass
    w = PyQtVisualizer(port=args.port, mock=args.mock)
    w.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
