# ESP32 + MPU6050 Simple GUI Interface

A small Python GUI (Ursina) that visualizes roll, pitch, and yaw sent by an ESP32 running an MPU6050 DMP-based sketch.

## Features

- Reads comma-separated Roll,Pitch,Yaw from serial (115200)
- Visualizes orientation with a 3D board model using Ursina

## Requirements

- Python 3.8+ (tested with 3.10)
- Packages: ursina, pyserial

Install dependencies:

```bat
python -m pip install ursina pyserial
```

## Usage

1. Upload the provided Arduino sketch to your ESP32 (uses MPU6050_tockn library).
2. Plug in the ESP32 and note the serial port.
3. Run the visualizer:

```bat
cd /d "d:\Code\Arduino\ESP32\MPU6050 with GUI"
python -u "d:\Code\Arduino\ESP32\MPU6050 with GUI\python_visualizer.py"
```

If the script can't find the serial port automatically, edit `find_serial_port()` in `python_visualizer.py` and add your COM port to `ports_to_try`.

## Troubleshooting

- If you see `AttributeError: module 'serial' has no attribute 'Serial'`, uninstall any wrongly-named `serial` package and install `pyserial`:

```bat
python -m pip uninstall serial -y
python -m pip install pyserial
```

- Ensure the Arduino sketch prints `roll,pitch,yaw\n` at 115200 baud.

## Notes

- `debug_serial.py` is a small helper to diagnose which `serial` package is imported. Remove it if you prefer.
