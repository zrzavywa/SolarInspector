import json
import socket
import sqlite3
import struct
import tempfile
import threading
import unittest
from datetime import date
from pathlib import Path

import pytest
import solarinspector as si
from modbus_solakon import SolakonOneReader

pytestmark = pytest.mark.integration



def encode_string(text: str, count: int) -> list[int]:
    raw = text.encode("ascii")[: count * 2].ljust(count * 2, b"\x00")
    return [int.from_bytes(raw[i:i + 2], "big") for i in range(0, len(raw), 2)]


def put_i32(mapping: dict[int, int], address: int, value: int) -> None:
    value &= 0xFFFFFFFF
    mapping[address] = (value >> 16) & 0xFFFF
    mapping[address + 1] = value & 0xFFFF


def put_u32(mapping: dict[int, int], address: int, value: int) -> None:
    put_i32(mapping, address, value)


class FakeModbusServer:
    def __init__(self, registers: dict[int, int]):
        self.registers = registers
        self.requests: list[tuple[int, int, int]] = []
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.port = self.sock.getsockname()[1]
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    @staticmethod
    def _recv_exact(conn: socket.socket, length: int) -> bytes:
        data = b""
        while len(data) < length:
            chunk = conn.recv(length - len(data))
            if not chunk:
                return b""
            data += chunk
        return data

    def _serve(self) -> None:
        try:
            conn, _ = self.sock.accept()
            with conn:
                while True:
                    header = self._recv_exact(conn, 7)
                    if not header:
                        break
                    transaction, protocol, length, unit = struct.unpack(">HHHB", header)
                    pdu = self._recv_exact(conn, length - 1)
                    if len(pdu) != 5:
                        break
                    function, address, count = struct.unpack(">BHH", pdu)
                    self.requests.append((function, address, count))
                    if function != 3:
                        response_pdu = bytes([function | 0x80, 1])
                    else:
                        values = [self.registers.get(address + i, 0) for i in range(count)]
                        payload = struct.pack(">" + "H" * count, *values)
                        response_pdu = bytes([3, len(payload)]) + payload
                    response = struct.pack(">HHHB", transaction, protocol, len(response_pdu) + 1, unit) + response_pdu
                    conn.sendall(response)
        finally:
            self.sock.close()

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass
        self.thread.join(timeout=2)


class SolarInspectorTests(unittest.TestCase):
    def test_config_validation(self):
        config = si.deep_merge(si.DEFAULT_CONFIG, {
            "general": {
                "poll_interval_seconds": 0,
                "port": 99999,
                "solar_power_source": "invalid",
                "grid_power_source": "invalid",
            },
            "solakon_meter": {"direction_factor": -9},
            "solakon_one": {"port": 70000, "device_id": 999, "timeout_seconds": 0},
        })
        valid = si.ConfigManager.validate(config)
        self.assertEqual(valid["general"]["poll_interval_seconds"], 2)
        self.assertEqual(valid["general"]["port"], 65535)
        self.assertEqual(valid["general"]["solar_power_source"], "auto")
        self.assertEqual(valid["general"]["grid_power_source"], "auto")
        self.assertEqual(valid["solakon_meter"]["direction_factor"], -1)
        self.assertEqual(valid["solakon_one"]["port"], 65535)
        self.assertEqual(valid["solakon_one"]["device_id"], 247)
        self.assertEqual(valid["solakon_one"]["timeout_seconds"], 1)

    def test_period_day(self):
        start, end, labels, title = si.period_bounds("day", date(2026, 7, 19))
        self.assertEqual(len(labels), 24)
        self.assertEqual((end - start).days, 1)
        self.assertIn("2026", title)

    def test_database_migrates_v3_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "old.db"
            conn = sqlite3.connect(path)
            try:
                conn.execute("CREATE TABLE samples (id INTEGER PRIMARY KEY, ts_epoch REAL NOT NULL, ts_local TEXT NOT NULL)")
                conn.commit()
            finally:
                conn.close()
            db = si.Database(path)
            with db.connect() as conn:
                columns = {row[1] for row in conn.execute("PRAGMA table_info(samples)")}
            self.assertIn("solakon_battery_soc_pct", columns)
            self.assertIn("solakon_pv_wh", columns)
            self.assertIn("solar_source", columns)

    def test_modbus_read_only_protocol_and_register_parsing(self):
        registers: dict[int, int] = {}
        for i, value in enumerate(encode_string("Solakon ONE H3", 16)):
            registers[30000 + i] = value
        for i, value in enumerate(encode_string("ONE-TEST-123", 16)):
            registers[30016 + i] = value
        registers[39063] = 1 << 2
        registers[39070] = 362
        registers[39071] = 123
        put_i32(registers, 39118, 960)
        put_i32(registers, 39134, 740)
        registers[39138] = 990
        registers[39139] = 5001
        registers[39141] = 315
        put_u32(registers, 39149, 123456)
        put_u32(registers, 39151, 345)
        put_i32(registers, 39162, 210)
        put_i32(registers, 39168, -150)
        put_i32(registers, 39225, 590)
        put_i32(registers, 39230, 210)
        put_i32(registers, 39237, 220)
        put_i32(registers, 39279, 480)
        put_i32(registers, 39281, 480)
        registers[39424] = 76
        put_u32(registers, 39601, 123456)
        put_u32(registers, 39603, 345)
        put_u32(registers, 39605, 45678)
        put_u32(registers, 39609, 41922)

        server = FakeModbusServer(registers)
        try:
            reading = SolakonOneReader().read({
                "host": "127.0.0.1",
                "port": server.port,
                "device_id": 1,
                "timeout_seconds": 2,
                "simulation": False,
            })
        finally:
            server.close()

        self.assertEqual(reading.model_name, "Solakon ONE H3")
        self.assertEqual(reading.serial_number, "ONE-TEST-123")
        self.assertEqual(reading.status, "Betrieb")
        self.assertEqual(reading.total_pv_power_w, 960.0)
        self.assertEqual(reading.active_power_w, 740.0)
        self.assertEqual(reading.battery_power_w, 220.0)
        self.assertEqual(reading.meter_power_w, -150.0)
        self.assertEqual(reading.battery_soc_pct, 76.0)
        self.assertAlmostEqual(reading.total_pv_energy_kwh, 1234.56)
        self.assertTrue(server.requests)
        self.assertTrue(all(function == 3 for function, _, _ in server.requests))


    def test_collector_combines_simulated_solakon_and_shelly_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "config.json"
            cfg = si.deep_merge(si.DEFAULT_CONFIG, {
                "general": {"solar_power_source": "auto", "grid_power_source": "auto"},
                "solakon_one": {"enabled": True, "simulation": True},
                "house_meter": {"enabled": True, "type": "simulation"},
                "solakon_meter": {"enabled": True, "type": "simulation"},
            })
            cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
            manager = si.ConfigManager(cfg_path)
            db = si.Database(Path(tmp) / "collector.db")
            collector = si.Collector(manager, db)
            collector.collect_once()
            collector._previous_epoch -= 10
            second = collector.collect_once()
            self.assertEqual(second["solakon_ok"], 1)
            self.assertEqual(second["solar_source"], "Shelly AC (Auto)")
            self.assertIsNotNone(second["solakon_battery_soc_pct"])
            self.assertIsNotNone(second["solar_difference_w"])
            self.assertGreaterEqual(second["solakon_pv_wh"], 0)
            self.assertEqual(db.stats()["count"], 2)

    def test_web_pages_and_simulated_modbus_test(self):
        original = (si.config_manager, si.database, si.collector)
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "config.json"
            cfg = si.deep_merge(si.DEFAULT_CONFIG, {
                "solakon_one": {"enabled": True, "simulation": True},
            })
            cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
            temp_config = si.ConfigManager(cfg_path)
            temp_db = si.Database(Path(tmp) / "test.db")
            temp_collector = si.Collector(temp_config, temp_db)
            si.config_manager, si.database, si.collector = temp_config, temp_db, temp_collector
            try:
                client = si.app.test_client()
                self.assertEqual(client.get("/").status_code, 200)
                self.assertEqual(client.get("/configuration").status_code, 200)
                self.assertEqual(client.get("/acquisition").status_code, 200)
                self.assertEqual(client.get("/data").status_code, 200)
                self.assertEqual(client.get("/api/dashboard?period=day&anchor=2026-07-19").status_code, 200)
                self.assertEqual(client.get("/api/export.csv?from=2026-07-19&to=2026-07-19").status_code, 200)
                response = client.post("/api/test-solakon-one", json={
                    "enabled": True,
                    "simulation": True,
                    "port": 502,
                    "device_id": 1,
                    "timeout_seconds": 2,
                })
                self.assertEqual(response.status_code, 200)
                payload = response.get_json()
                self.assertTrue(payload["ok"])
                self.assertIn("Simulation", payload["reading"]["model_name"])
            finally:
                temp_collector.stop()
                si.config_manager, si.database, si.collector = original


if __name__ == "__main__":
    unittest.main()
