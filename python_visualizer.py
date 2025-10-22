from ursina import *
import serial
import threading
import sys

# --- Ursina App Setup ---
app = Ursina()

# Define the 3D model for our sensor
# We use a 'cube' model and scale it to look like a boardhttps://github.com/sadikmahmudadive/esp32-and-mpu6050-simple-GUI-interface
board = Entity(model='cube', scale=(3, 0.5, 1.5), color=color.azure)
# Add a red "pointer" to see the "front" of the board
pointer = Entity(model='cube', parent=board, scale=(0.1, 0.2, 0.5), position=(0, 0, 0.5), color=color.red)

# Set up the camera
EditorCamera()

# --- Serial Data Handling ---

from ursina import *
import serial
import threading
import sys
import argparse
import time
import math

# --- Arguments ---
parser = argparse.ArgumentParser(description='MPU6050 Ursina visualizer')
parser.add_argument('--port', '-p', help='Serial port to use (e.g. COM3)')
parser.add_argument('--mock', action='store_true', help='Use mock data instead of serial (for testing)')
args = parser.parse_args()

# --- Ursina App Setup ---
app = Ursina()

# Define the 3D model for our sensor - a flattened box
board = Entity(model='cube', scale=(3, 0.4, 1.6), color=color.azure, texture=None)

# Add a bigger red pointer to show the "front" direction
pointer = Entity(model='cube', parent=board, scale=(0.14, 0.25, 0.7), position=(0, 0, 0.85), color=color.red)

# Add three colored axis markers attached to the board to make orientation clearer
x_axis = Entity(parent=board, model='cube', scale=(1.0, 0.03, 0.03), position=(0.5, 0.21, 0), color=color.red)
y_axis = Entity(parent=board, model='cube', scale=(0.03, 1.0, 0.03), position=(0.0, -0.5, 0), color=color.green)
z_axis = Entity(parent=board, model='cube', scale=(0.03, 0.03, 1.0), position=(0, 0.21, 0.5), color=color.blue)

# Camera
EditorCamera()

# --- Serial / Data Handling ---
# Mutable shared state
latest_angles = [0.0, 0.0, 0.0]  # Roll, Pitch, Yaw (degrees)
smoothed_angles = [0.0, 0.0, 0.0]
alpha = 0.25  # smoothing factor (0..1), higher = less smoothing
serial_running = False
use_mock = args.mock or False
serial_port = args.port


def clamp(v, lo=-360, hi=360):
    return max(lo, min(hi, v))


def serial_reader_thread(ser):
    """Read lines from serial and update latest_angles."""
    global latest_angles, serial_running
    serial_running = True
    while serial_running:
        try:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            if not line:
                continue
            parts = line.split(',')
            if len(parts) == 3:
                try:
                    r = float(parts[0])
                    p = float(parts[1])
                    y = float(parts[2])
                    latest_angles[0] = clamp(r)
                    latest_angles[1] = clamp(p)
                    latest_angles[2] = clamp(y)
                except ValueError:
                    # skip malformed
                    pass

        except Exception as e:
            print('Serial reader error:', e)
            try:
                ser.close()
            except Exception:
                pass
            serial_running = False
            break


def find_serial_port(explicit_port=None):
    """Try the explicit port first, then common ports for the platform."""
    ports_to_try = []
    if explicit_port:
        ports_to_try.append(explicit_port)

    if sys.platform.startswith('win'):
        ports_to_try += [f'COM{i}' for i in range(1, 20)]
    elif sys.platform.startswith('linux'):
        ports_to_try += [f'/dev/ttyUSB{i}' for i in range(10)] + [f'/dev/ttyACM{i}' for i in range(10)]
    elif sys.platform.startswith('darwin'):
        ports_to_try += [f'/dev/cu.usbserial-{i}' for i in range(10)] + [f'/dev/cu.SLAB_USBtoUART{i}' for i in range(10)]

    for port in ports_to_try:
        try:
            ser = serial.Serial(port, 115200, timeout=0.1)
            print(f'Connected to {port}')
            return ser
        except Exception:
            continue

    return None


# --- UI elements ---
roll_text = Text(text='Roll: 0.00', origin=(0, 8), position=Vec2(-0.88, 0.42), scale=1.2, color=color.white)
pitch_text = Text(text='Pitch: 0.00', origin=(0, 8), position=Vec2(-0.88, 0.36), scale=1.0, color=color.white)
yaw_text = Text(text='Yaw: 0.00', origin=(0, 8), position=Vec2(-0.88, 0.30), scale=1.0, color=color.white)
status_text = Text(text='Status: starting...', origin=(0, 8), position=Vec2(-0.88, 0.22), scale=0.9, color=color.yellow)
instructions = Text(text="Space: pause/resume | M: toggle mock data | Esc: quit", origin=(0, 8), position=Vec2(-0.88, -0.45), scale=0.6, color=color.azure)


def update_ui():
    roll_text.text = f'Roll: {smoothed_angles[0]:.2f}°'
    pitch_text.text = f'Pitch: {smoothed_angles[1]:.2f}°'
    yaw_text.text = f'Yaw: {smoothed_angles[2]:.2f}°'


# --- Mock data generator (for testing without device) ---
def mock_update(dt):
    t = time.time()
    # slow, smooth rotations
    latest_angles[0] = math.sin(t * 0.8) * 40  # roll
    latest_angles[1] = math.sin(t * 0.6) * 30  # pitch
    latest_angles[2] = math.sin(t * 0.5) * 90  # yaw


# keyboard / input handling
paused = False


def input(key):
    global paused, use_mock, serial_running
    if key == 'space':
        paused = not paused
        status_text.text = 'Status: paused' if paused else 'Status: running'
    if key == 'm':
        use_mock = not use_mock
        status_text.text = 'Status: mock' if use_mock else 'Status: serial'
    if key == 'escape':
        application.quit()


def update():
    global smoothed_angles
    dt = time.dt
    # If using mock mode, drive angles from function
    if use_mock:
        mock_update(dt)

    if paused:
        return

    # smoothing (exponential moving average)
    for i in range(3):
        smoothed_angles[i] = alpha * latest_angles[i] + (1 - alpha) * smoothed_angles[i]

    # Apply rotations: mapping from incoming data to Ursina axes
    board.rotation_y = smoothed_angles[0]   # Roll -> yaw in Ursina
    board.rotation_x = smoothed_angles[1]   # Pitch -> x
    board.rotation_z = -smoothed_angles[2]  # Yaw -> negate for visual alignment

    update_ui()


# --- Start serial thread (if not mock) ---
ser = None
thread = None
if not use_mock:
    ser = find_serial_port(serial_port)
    if ser:
        try:
            thread = threading.Thread(target=serial_reader_thread, args=(ser,), daemon=True)
            thread.start()
            status_text.text = f'Status: connected ({ser.port})'
        except Exception as e:
            print('Could not start serial thread:', e)
            status_text.text = 'Status: serial error'
    else:
        status_text.text = 'Status: no serial found (press M for mock)'
else:
    status_text.text = 'Status: mock mode'


if __name__ == '__main__':
    app.run()
