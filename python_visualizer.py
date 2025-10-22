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

# Global variables to store the latest angles
# We use a list to make it mutable so the thread can update it
latest_angles = [0.0, 0.0, 0.0] # Roll, Pitch, Yaw

# This function will run in a separate thread to read serial data
def serial_reader_thread(ser):
    global latest_angles
    while True:
        try:
            # Read a line from the serial port
            line = ser.readline().decode('utf-8').strip()
            
            # Split the line by commas
            parts = line.split(',')
            
            # If we get 3 parts, update the angles
            if len(parts) == 3:
                latest_angles[0] = float(parts[0]) # Roll
                latest_angles[1] = float(parts[1]) # Pitch
                latest_angles[2] = float(parts[2]) # Yaw
                # print(f"Roll: {latest_angles[0]:.2f}, Pitch: {latest_angles[1]:.2f}, Yaw: {latest_angles[2]:.2f}")

        except serial.SerialException as e:
            print(f"Serial error: {e}")
            ser.close()
            break # Exit thread
        except ValueError:
            # Incomplete line, just skip it
            pass
        except Exception as e:
            print(f"An error occurred: {e}")
            break

# This function is called by Ursina every frame
def update():
    # Apply the rotations to the 3D board
    # NOTE: The axis mapping might need to be tweaked!
    # Ursina: rotation_x (Pitch), rotation_y (Yaw), rotation_z (Roll)
    # Our data: Roll (Y-axis), Pitch (X-axis), Yaw (Z-axis)
    
    # This mapping seems to work for the ESP32 code provided:
    board.rotation_y = latest_angles[0] # Data 'Roll' (Y-axis rot) -> Ursina Y rotation
    board.rotation_x = latest_angles[1] # Data 'Pitch' (X-axis rot) -> Ursina X rotation
    board.rotation_z = -latest_angles[2] # Data 'Yaw' (Z-axis rot) -> Ursina Z rotation (negated)
    
    # --- Axis Troubleshooting ---
    # If the rotation seems wrong, try swapping the axes below:
    # board.rotation_x = latest_angles[0]
    # board.rotation_y = latest_angles[1]
    # board.rotation_z = latest_angles[2]
    #
    # Or try negating different axes:
    # board.rotation_x = -latest_angles[1] 
    # etc.

# --- Main script execution ---
def find_serial_port():
    """Tries to find the ESP32 serial port automatically."""
    ports_to_try = []
    if sys.platform.startswith('win'):
        ports_to_try = [f'COM{i}' for i in range(1, 10)]
    elif sys.platform.startswith('linux'):
        ports_to_try = [f'/dev/ttyUSB{i}' for i in range(10)] + [f'/dev/ttyACM{i}' for i in range(10)]
    elif sys.platform.startswith('darwin'):
        ports_to_try = [f'/dev/cu.usbserial-{i}' for i in range(10)] + [f'/dev/cu.SLAB_USBtoUART{i}' for i in range(10)]

    for port in ports_to_try:
        try:
            ser = serial.Serial(port, 115200, timeout=0.1)
            print(f"Connected to {port}!")
            return ser
        except serial.SerialException:
            pass # Port not found or in use
    
    print("\n--- ERROR ---")
    print("Could not find ESP32 serial port. Make sure it's plugged in.")
    print("If you know the port, add it to the 'ports_to_try' list in the script.")
    return None

# Find and open the serial port
ser = find_serial_port()

if ser:
    # Start the serial-reading thread
    # daemon=True means the thread will close when the main app closes
    thread = threading.Thread(target=serial_reader_thread, args=(ser,), daemon=True)
    thread.start()
    
    # Start the Ursina app
    app.run()
else:
    print("Exiting. No serial port found.")
