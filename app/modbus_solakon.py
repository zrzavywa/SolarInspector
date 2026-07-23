"""Compatibility layer for the Solakon ONE adapter.

The implementation lives in
``solarinspector_core.adapters.solakon``.
This module preserves the historic import and monkeypatch paths.
"""

from __future__ import annotations

import socket as _socket
from typing import Any

from solarinspector_core.adapters.solakon import (
    ModbusError,
    ModbusTcpConnection,
    SolakonOneReading,
)
from solarinspector_core.adapters.solakon import (
    SolakonOneReader as CoreSolakonOneReader,
)

socket = _socket


class SolakonOneReader(CoreSolakonOneReader):
    """Reader preserving historic module-level connection patching."""

    def _create_connection(
        self,
        host: str,
        port: int,
        unit_id: int,
        timeout: float,
    ) -> Any:
        """Resolve the connection through the legacy module."""
        return ModbusTcpConnection(
            host,
            port,
            unit_id,
            timeout,
        )


__all__ = [
    "ModbusError",
    "ModbusTcpConnection",
    "SolakonOneReader",
    "SolakonOneReading",
    "socket",
]
