# Agent_A/Communication/USBConnection.py

"""
USBConnection manages serial communication with drone flight controller.
Supports MAVLink protocol for telemetry and commands.
Can be tested with USB loopback or computer USB ports.
"""

import serial
import serial.tools.list_ports
import time
from typing import Optional, List, Callable, Dict, Any
from threading import Thread, Event
import queue


class USBConnection:
    """
    Manages USB serial connection to drone flight controller.
    Implements MAVLink communication protocol.
    """
    
    def __init__(
        self,
        port: Optional[str] = None,
        baudrate: int = 57600,
        timeout: float = 1.0,
        auto_connect: bool = False
    ):
        """
        Initialize USB connection.
        
        Args:
            port: Serial port (e.g., '/dev/ttyUSB0', 'COM3'). None for auto-detect.
            baudrate: Communication speed (57600 for most flight controllers)
            timeout: Read timeout in seconds
            auto_connect: Automatically connect on initialization
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        
        self.serial_conn: Optional[serial.Serial] = None
        self.is_connected = False
        
        # Threading for async read
        self.read_thread: Optional[Thread] = None
        self.stop_event = Event()
        self.message_queue = queue.Queue()
        
        # Callbacks
        self.message_callbacks: List[Callable[[bytes], None]] = []
        
        print(f"USBConnection initialized (port={port or 'auto'}, baud={baudrate})")
        
        if auto_connect:
            self.connect()
    
    @staticmethod
    def list_available_ports() -> List[Dict[str, str]]:
        """
        List all available serial ports.
        
        Returns:
            List of dicts with 'port', 'description', 'hwid'
        """
        ports = []
        for port in serial.tools.list_ports.comports():
            ports.append({
                'port': port.device,
                'description': port.description,
                'hwid': port.hwid
            })
        return ports
    
    @staticmethod
    def detect_flight_controller() -> Optional[str]:
        """
        Auto-detect flight controller port.
        Looks for common flight controller USB VID/PID.
        
        Returns:
            Port name if found, None otherwise
        """
        # Common flight controller identifiers
        FC_IDENTIFIERS = [
            'Pixhawk',
            'PX4',
            'ArduPilot', 
            'FTDI',  # Common USB-serial chip
            'CP210',  # Silicon Labs chip
            'CH340',  # Common Chinese USB-serial
        ]
        
        for port in serial.tools.list_ports.comports():
            desc = port.description.upper()
            hwid = port.hwid.upper()
            
            for identifier in FC_IDENTIFIERS:
                if identifier.upper() in desc or identifier.upper() in hwid:
                    print(f"✓ Detected flight controller: {port.device} ({port.description})")
                    return port.device
        
        return None
    
    def connect(self, port: Optional[str] = None) -> bool:
        """
        Establish serial connection.
        
        Args:
            port: Optional port override
        
        Returns:
            True if connected successfully
        """
        if self.is_connected:
            print("⚠ Already connected")
            return True
        
        # Use provided port or try auto-detect
        target_port = port or self.port
        
        if not target_port:
            print("Auto-detecting flight controller...")
            target_port = self.detect_flight_controller()
            
            if not target_port:
                print("✗ No flight controller detected. Available ports:")
                for p in self.list_available_ports():
                    print(f"  - {p['port']}: {p['description']}")
                return False
        
        try:
            print(f"Connecting to {target_port} @ {self.baudrate} baud...")
            
            self.serial_conn = serial.Serial(
                port=target_port,
                baudrate=self.baudrate,
                timeout=self.timeout,
                write_timeout=self.timeout
            )
            
            time.sleep(2)  # Wait for connection to stabilize
            
            self.is_connected = True
            self.port = target_port
            
            # Start read thread
            self._start_read_thread()
            
            print(f"✓ Connected to {target_port}")
            return True
            
        except serial.SerialException as e:
            print(f"✗ Connection failed: {e}")
            return False
    
    def disconnect(self):
        """Close serial connection and stop threads"""
        if not self.is_connected:
            return
        
        print("Disconnecting...")
        
        # Stop read thread
        self.stop_event.set()
        if self.read_thread and self.read_thread.is_alive():
            self.read_thread.join(timeout=2)
        
        # Close serial port
        if self.serial_conn:
            self.serial_conn.close()
        
        self.is_connected = False
        print("✓ Disconnected")
    
    def _start_read_thread(self):
        """Start background thread for reading data"""
        self.stop_event.clear()
        self.read_thread = Thread(target=self._read_loop, daemon=True)
        self.read_thread.start()
    
    def _read_loop(self):
        """Background loop to read incoming data"""
        while not self.stop_event.is_set() and self.is_connected:
            try:
                if self.serial_conn and self.serial_conn.in_waiting > 0:
                    data = self.serial_conn.read(self.serial_conn.in_waiting)
                    
                    # Queue message
                    self.message_queue.put(data)
                    
                    # Trigger callbacks
                    for callback in self.message_callbacks:
                        try:
                            callback(data)
                        except Exception as e:
                            print(f"⚠ Callback error: {e}")
                else:
                    time.sleep(0.01)  # Prevent busy-wait
                    
            except Exception as e:
                if self.is_connected:  # Only log if not intentionally disconnected
                    print(f"⚠ Read error: {e}")
                    time.sleep(0.1)
    
    def write(self, data: bytes) -> bool:
        """
        Write data to serial port.
        
        Args:
            data: Bytes to write
        
        Returns:
            True if successful
        """
        if not self.is_connected or not self.serial_conn:
            print("✗ Not connected")
            return False
        
        try:
            self.serial_conn.write(data)
            return True
        except Exception as e:
            print(f"✗ Write error: {e}")
            return False
    
    def read_message(self, timeout: Optional[float] = None) -> Optional[bytes]:
        """
        Read next message from queue.
        
        Args:
            timeout: Max time to wait for message
        
        Returns:
            Message bytes or None if timeout
        """
        try:
            return self.message_queue.get(timeout=timeout)
        except queue.Empty:
            return None
    
    def register_callback(self, callback: Callable[[bytes], None]):
        """Register callback for incoming messages"""
        self.message_callbacks.append(callback)
    
    def send_heartbeat(self) -> bool:
        """
        Send MAVLink heartbeat message.
        This is a simplified version - full MAVLink implementation needed for production.
        
        Returns:
            True if sent successfully
        """
        # MAVLink 1.0 HEARTBEAT (message ID 0)
        # Header: STX(0xFE) + LEN + SEQ + SYSID + COMPID + MSGID
        # Payload: type + autopilot + base_mode + custom_mode + system_status + mavlink_version
        # Footer: CRC16
        
        # Simplified heartbeat for testing
        heartbeat = bytes([
            0xFE,  # STX (MAVLink 1.0)
            0x09,  # Payload length
            0x00,  # Sequence
            0xFF,  # System ID (GCS)
            0xBE,  # Component ID (companion computer)
            0x00,  # Message ID (HEARTBEAT)
            # Payload (9 bytes)
            0x06,  # Type: GCS
            0x08,  # Autopilot: INVALID
            0x00,  # Base mode
            0x00, 0x00, 0x00, 0x00,  # Custom mode
            0x04,  # System status: ACTIVE
            0x03,  # MAVLink version
        ])
        
        # Add CRC (simplified - proper CRC calculation needed)
        crc = bytes([0x00, 0x00])  # Placeholder
        
        return self.write(heartbeat + crc)
    
    def get_status(self) -> Dict[str, Any]:
        """Return connection status"""
        return {
            'connected': self.is_connected,
            'port': self.port,
            'baudrate': self.baudrate,
            'queued_messages': self.message_queue.qsize(),
            'callbacks_registered': len(self.message_callbacks)
        }
    
    def __enter__(self):
        """Context manager support"""
        if not self.is_connected:
            self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager cleanup"""
        self.disconnect()


# Example usage and testing
if __name__ == "__main__":
    print("USB Connection Test")
    print("=" * 80)
    
    # List available ports
    print("\nAvailable serial ports:")
    for port in USBConnection.list_available_ports():
        print(f"  {port['port']}: {port['description']}")
    
    # Test with auto-detection
    print("\n" + "=" * 80)
    print("Testing auto-connection...")
    
    usb = USBConnection(auto_connect=True)
    
    if usb.is_connected:
        print(f"\nStatus: {usb.get_status()}")
        
        # Register callback
        def on_message(data: bytes):
            print(f"Received: {data.hex()}")
        
        usb.register_callback(on_message)
        
        # Send test heartbeat
        print("\nSending heartbeat...")
        usb.send_heartbeat()
        
        # Wait for responses
        time.sleep(2)
        
        # Check for messages
        msg = usb.read_message(timeout=0.5)
        if msg:
            print(f"Message from queue: {msg.hex()}")
        else:
            print("No messages in queue")
        
        # Disconnect
        usb.disconnect()
    else:
        print("\nℹ Could not connect. For testing without hardware:")
        print("  1. Use virtual serial ports (socat on Linux)")
        print("  2. Connect USB-to-USB cable with proper drivers")
        print("  3. Use USB loopback adapter")