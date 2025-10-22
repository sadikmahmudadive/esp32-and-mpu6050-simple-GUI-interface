import sys
import importlib
import traceback

print('Python executable:', sys.executable)
print('sys.path (first 10 entries):')
for p in sys.path[:10]:
    print('  ', p)

try:
    import serial
    print('\nImported module serial:')
    print('  repr:', repr(serial))
    print('  file:', getattr(serial, '__file__', '(built-in or namespace package)'))
    print('  has Serial:', hasattr(serial, 'Serial'))
    print('  has SerialException:', hasattr(serial, 'SerialException'))

    # Try to import a known pyserial submodule
    try:
        import serial.tools.list_ports as list_ports
        print('  serial.tools.list_ports imported OK')
    except Exception as e:
        print('  could not import serial.tools.list_ports:', e)

except Exception as e:
    print('Error importing serial:')
    traceback.print_exc()

# Check package metadata for pyserial if possible
try:
    from importlib import metadata
    try:
        ver = metadata.version('pyserial')
        print('\npyserial version reported by importlib.metadata:', ver)
    except Exception as e:
        print('\npyserial not found via importlib.metadata:', e)
except Exception:
    pass

print('\nDone.')
