

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

# Camera and environment tweaks
EditorCamera()
window.color = color.rgb(18, 26, 34)  # darker background

# Lighting
DirectionalLight(y=2, z=3, shadows=False)
AmbientLight(color=color.rgba(50, 50, 60, 0.6))

# UI toggles
show_trail = True
show_axes = True

# Trail (ghost boards) to show recent orientations
max_trail_capacity = 30
trail_length = 12  # current visible length (can be changed at runtime)
trail = []  # list of ghost Entities (max capacity)

def create_ghost():
    g = Entity(model='cube', scale=board.scale, color=color.rgba(150, 170, 255, 40), visible=False)
    # pointer child
    p = Entity(model='cube', parent=g, scale=(0.14, 0.25, 0.7), position=(0, 0, 0.85), color=color.rgba(255, 80, 80, 180))
    # axes children
    Entity(parent=g, model='cube', scale=(1.0, 0.03, 0.03), position=(0.5, 0.21, 0), color=color.rgba(255, 50, 50, 200))
    Entity(parent=g, model='cube', scale=(0.03, 1.0, 0.03), position=(0.0, -0.5, 0), color=color.rgba(50, 255, 50, 200))
    Entity(parent=g, model='cube', scale=(0.03, 0.03, 1.0), position=(0, 0.21, 0.5), color=color.rgba(50, 100, 255, 200))
    return g

for i in range(max_trail_capacity):
    trail.append(create_ghost())

# Simple bar meters for roll/pitch/yaw
meter_roll = Entity(parent=camera.ui, model='quad', scale=(0.25, 0.02), position=Vec2(-0.6, 0.45), color=color.red)
meter_pitch = Entity(parent=camera.ui, model='quad', scale=(0.25, 0.02), position=Vec2(-0.6, 0.40), color=color.green)
meter_yaw = Entity(parent=camera.ui, model='quad', scale=(0.25, 0.02), position=Vec2(-0.6, 0.35), color=color.blue)
meter_bg = Entity(parent=camera.ui, model='quad', scale=(0.26, 0.1), position=Vec2(-0.6, 0.38), color=color.rgba(255,255,255,8))

# smoothing (defined early so labels can reference it)
alpha = 0.25  # smoothing factor (0..1), higher = less smoothing

# Control panel labels (updated in code when values change)
alpha_label = Text(text=f'Smooth: {alpha:.2f}', parent=camera.ui, position=Vec2(0.48, 0.45), scale=0.7, color=color.white)
trail_label = Text(text=f'Trail: {trail_length}', parent=camera.ui, position=Vec2(0.48, 0.38), scale=0.7, color=color.white)

# calibration offsets
offsets = [0.0, 0.0, 0.0]

# sample data for playback (simple synthetic waveform)
sample_data = [(math.sin(i/10)*40, math.sin(i/12)*30, math.sin(i/15)*90) for i in range(0, 720)]
playback_mode = False
playback_index = 0
playback_timer = 0.0
playback_rate = 60.0  # frames per second

# --- Control callbacks and buttons ---
def set_alpha(d):
    global alpha
    alpha = max(0.0, min(0.95, alpha + d))
    alpha_label.text = f'Smooth: {alpha:.2f}'

def set_trail(d):
    global trail_length
    trail_length = max(0, min(max_trail_capacity, trail_length + d))
    trail_label.text = f'Trail: {trail_length}'

def calibrate():
    # set current smoothed_angles as zero offsets
    global offsets
    offsets = smoothed_angles.copy()
    status_text.text = 'Calibrated'

def toggle_playback():
    global playback_mode, playback_index
    playback_mode = not playback_mode
    playback_index = 0
    status_text.text = 'Playback on' if playback_mode else 'Playback off'

# Buttons
btn_alpha_minus = Button(text='- Smooth', parent=camera.ui, position=Vec2(0.40, 0.45), scale=0.06)
btn_alpha_plus = Button(text='+ Smooth', parent=camera.ui, position=Vec2(0.56, 0.45), scale=0.06)
btn_trail_minus = Button(text='- Trail', parent=camera.ui, position=Vec2(0.40, 0.38), scale=0.06)
btn_trail_plus = Button(text='+ Trail', parent=camera.ui, position=Vec2(0.56, 0.38), scale=0.06)
btn_cal = Button(text='Calibrate (C)', parent=camera.ui, position=Vec2(0.48, 0.31), scale=0.08)
btn_play = Button(text='Playback (P)', parent=camera.ui, position=Vec2(0.48, 0.24), scale=0.08)

btn_alpha_minus.on_click = lambda: set_alpha(-0.05)
btn_alpha_plus.on_click = lambda: set_alpha(0.05)
btn_trail_minus.on_click = lambda: set_trail(-1)
btn_trail_plus.on_click = lambda: set_trail(1)
btn_cal.on_click = calibrate
btn_play.on_click = toggle_playback

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
    if key == 't':
        global show_trail
        show_trail = not show_trail
        status_text.text = 'Trail: on' if show_trail else 'Trail: off'
    if key == 'a':
        global show_axes
        show_axes = not show_axes
        x_axis.visible = show_axes
        y_axis.visible = show_axes
        z_axis.visible = show_axes
        status_text.text = 'Axes: on' if show_axes else 'Axes: off'
    if key == 'c':
        calibrate()
    if key == 'p':
        toggle_playback()
    if key == '+':
        set_alpha(0.05)
    if key == '-':
        set_alpha(-0.05)
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

    # update trail ghosts
    if show_trail:
        # shift previous
        for i in range(trail_length - 1, 0, -1):
            trail[i].rotation = trail[i - 1].rotation
            trail[i].visible = True
            # fade alpha with index
            alpha_val = int(180 * (1 - i / trail_length))
            trail[i].color = color.rgba(120, 170, 255, alpha_val)
        # front ghost = current board
        trail[0].rotation = board.rotation
        trail[0].position = board.position
        trail[0].visible = True
    else:
        for g in trail:
            g.visible = False

    # update meters (map angle to 0..1)
    def norm_angle(a):
        return (a + 180) / 360

    meter_roll.scale_x = 0.25 * norm_angle(smoothed_angles[0])
    meter_pitch.scale_x = 0.25 * norm_angle(smoothed_angles[1])
    meter_yaw.scale_x = 0.25 * norm_angle(smoothed_angles[2])


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
