# pyright: basic

import asyncio
import struct
import threading
import tkinter as tk

from bleak import BleakClient, BleakScanner
from pythonosc import udp_client

DEVICE_NAME = "Nx Tracker 2"
START_UUID = "0000a011-5761-7665-7341-7564696f4c74"
STREAM_UUID = "0000a015-5761-7665-7341-7564696f4c74"
BATTERY_UUID = "00002a19-0000-1000-8000-00805f9b34fb"
RESET = "0000a011-5761-7665-7341-7564696f4c74"

# OSC target (any OSC server listening here will get the /quat messages)
OSC_IP = "127.0.0.1"
OSC_PORT = 9000


def parse_packet(data: bytes):
    q0, q1, q2, q3, _ = struct.unpack("<5h", data)
    scale = float(1 << 14)
    return [q0 / scale, q1 / scale, q2 / scale, q3 / scale]


async def get_nx_tracker() -> str:
    scanner = BleakScanner()
    devices = await scanner.discover()
    # get matching devices
    nxs = [dev for dev in devices if dev.name == DEVICE_NAME]
    if len(nxs) == 0:
        raise RuntimeError("No Nx Tracker 2 devices were found!")
    if n := len(nxs) > 1:
        print(f"WARNING: Multiple Nx Tracker 2 devices were found! ({n=})")

    return nxs[0].address


class BleakRunner(threading.Thread):
    def __init__(self, address, update_cb, update_batt):
        super().__init__(daemon=True)
        self.loop = asyncio.new_event_loop()
        self.address = address
        self._update = update_cb
        self._batt_update = update_batt
        self._running = False
        self.client: BleakClient

        # set up your OSC client once, reuse on every packet
        self.osc_client = udp_client.SimpleUDPClient(OSC_IP, OSC_PORT)

    def reset(self):
        async def _reset():
            await self.client.write_gatt_char(RESET, b"\x32\x00\x00\x00\x00")
            await self.client.write_gatt_char(RESET, b"\x32\x00\x00\x00\x01")

        asyncio.run_coroutine_threadsafe(_reset(), self.loop)

    def run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def start_stream(self):
        if self._running:
            return
        self._running = True

        async def _go():
            if not self.address:
                self.address = await get_nx_tracker()

            self.client = BleakClient(self.address, loop=self.loop)

            await self.client.connect()
            # tell device “start streaming”
            await self.client.write_gatt_char(START_UUID, b"\xff")

            # register BLE notification handler
            def _on_notify(_handle, data):
                quat = parse_packet(data)

                # 1) update the Tk label
                self._update(quat)

                # 2) broadcast OSC message to /quat
                #    payload is four floats
                self.osc_client.send_message("/quat", quat)

            def _batt_notify(_handle, data):
                batt = int.from_bytes(data)
                self._batt_update(batt)

            await self.client.start_notify(STREAM_UUID, _on_notify)
            await self.client.start_notify(BATTERY_UUID, _batt_notify)

            # battery level notification rate is very low, so we get the initial value
            # manually, without waiting for next update. otherwise it stays empty for a few
            # seconds after connection
            self._batt_update(
                int.from_bytes(await self.client.read_gatt_char(BATTERY_UUID))
            )

        asyncio.run_coroutine_threadsafe(_go(), self.loop)

    def stop_stream(self):
        if not self._running:
            return
        self._running = False

        async def _stop():
            # tell device “stop streaming”
            await self.client.write_gatt_char(START_UUID, b"\x00")
            await self.client.stop_notify(STREAM_UUID)
            await self.client.disconnect()

        asyncio.run_coroutine_threadsafe(_stop(), self.loop)

    def shutdown(self):
        self.stop_stream()
        self.loop.call_soon_threadsafe(self.loop.stop)


class Window(tk.Tk):
    def __init__(self, address):
        super().__init__()
        self.title("BLE→OSC Quaternion")
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.lbl = tk.Label(self, text="quat=[----, ----, ----, ----]")
        self.lbl.pack(padx=20, pady=10)

        self.lbl2 = tk.Label(self, text="----")
        self.lbl2.pack(padx=20, pady=10)

        self.btn = tk.Button(self, text="Start", command=self.toggle_stream)
        self.btn.pack(padx=20, pady=5)

        self.btn2 = tk.Button(self, text="Reset", command=self.reset)
        self.btn2.pack(padx=20, pady=5)

        self.ble = BleakRunner(address, self.update_quat, self.update_batt)
        self.ble.start()

        self._streaming = False

    def reset(self):
        self.ble.reset()

    def toggle_stream(self):
        if not self._streaming:
            self.ble.start_stream()
            self.btn.config(text="Stop")
            self._streaming = True
        else:
            self.ble.stop_stream()
            self.btn.config(text="Start")
            self._streaming = False

    def update_batt(self, batt):
        self.after(0, lambda: self.lbl2.config(text=f"{batt}%"))

    def update_quat(self, quat):
        # BLE thread → Tk thread
        text = "quat=[" + ", ".join(f"{x:.2f}" for x in quat) + "]"
        # this way of updating label text is necessary, persumably due to some async/thread shenanigans
        self.after(0, lambda: self.lbl.config(text=text))

    def on_close(self):
        self.ble.shutdown()
        self.destroy()


if __name__ == "__main__":
    win = Window("")
    win.mainloop()
