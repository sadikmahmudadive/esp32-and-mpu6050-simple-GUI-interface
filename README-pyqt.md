# PyQt + pyqtgraph Visualizer

This is an alternate visualizer using PyQt5 and pyqtgraph's OpenGL to provide a clearer 3D view.

Requirements

- Install dependencies (recommended in a virtualenv):

```cmd
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements-pyqt.txt
```

Run

```cmd
python pyqt_visualizer.py --mock
python pyqt_visualizer.py --port COM3
```

Notes

- The app supports mock mode and real serial input (roll,pitch,yaw lines at 115200 baud).
- Trail history is shown as translucent meshes.
- If serial fails to open, check port names in Device Manager.
