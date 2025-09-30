import asyncio
import struct
from typing import Callable, NamedTuple

from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice

DEVICE_NAME = "Nx Tracker 2"
START_UUID = "0000a011-5761-7665-7341-7564696f4c74"
STREAM_UUID = "0000a015-5761-7665-7341-7564696f4c74"


class Quaternion(NamedTuple):
    w: float
    x: float
    y: float
    z: float


def parse_packet(data: bytearray) -> Quaternion:
    # normalization constant to get float16 from bytes
    scale = float(1 << 14)

    # 5th item is almost always constant and I don't know what it means.
    unpacked_data: tuple[float, ...] = struct.unpack("<5h", data)

    # first 4 are quaternion's components
    quat = Quaternion(*(q / scale for q in unpacked_data[:4]))

    # They seem to bee shuffled like this. I am sure I am wrong.
    # They are probably in reverse order or something like that.
    # -quat[3], x = quat[0], y = -quat[2], z = -quat[1];
    return quat


async def discover_nx_trackers() -> list[BLEDevice]:
    scanner = BleakScanner()
    devices = await scanner.discover()
    # get matching devices
    nxs = [dev for dev in devices if dev.name == DEVICE_NAME]

    return nxs


class NxTracker:
    def __init__(
        self,
        address_or_device: str | BLEDevice,
        on_update: Callable[[Quaternion], None],
        on_disconnect: Callable[[BleakClient], None] | None = None,
    ):
        self._update: Callable[[Quaternion], None] = on_update
        self._running: bool = False
        self.client: BleakClient = BleakClient(address_or_device, on_disconnect)

    async def start_stream(self, rate: int = 255):
        if self._running:
            return
        self._running = True

        await self.client.connect()
        # write refresh rate to this gatt characteristic
        await self.client.write_gatt_char(START_UUID, rate.to_bytes(1))

        # register notification handler
        def _on_notify(_handle: BleakGATTCharacteristic, data: bytearray):
            quat = parse_packet(data)
            self._update(quat)

        await self.client.start_notify(STREAM_UUID, _on_notify)

    async def stop_stream(self):
        if not self._running:
            return
        self._running = False

        await self.client.write_gatt_char(START_UUID, b"\x00")
        await self.client.stop_notify(STREAM_UUID)
        await self.client.disconnect()

    async def shutdown(self):
        await self.stop_stream()
        await self.client.disconnect()


# ======= below code is for testing. will be removed =======


def on_stream(q: Quaternion):
    print(q)


async def main():
    print("discovering nx trackers")
    devices = await discover_nx_trackers()
    nx = NxTracker(devices[0], on_stream)
    print("created nx")
    await nx.start_stream(1)
    print("started stream")
    await asyncio.sleep(3)
    print("waited 3 seconds")
    await nx.stop_stream()
    print("stopped stream")
    await nx.shutdown()
    print("shutdown nx")


if __name__ == "__main__":
    asyncio.run(main())
