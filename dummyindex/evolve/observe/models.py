"""Frozen records for exposures, corrections and attributions."""

from __future__ import annotations

from dataclasses import dataclass, fields
from enum import Enum
from typing import Any

from .enums import CorrectionStatus, ExposureVia, Verdict


def _encode(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return list(value)
    return value


@dataclass(frozen=True)
class Exposure:
    """One item the agent read, invoked or was injected with."""

    item: str
    version: str | None
    rules: tuple[str, ...]
    session: str
    turn: int
    day: str
    via: ExposureVia
    call: str
    model: str | None
    cli: str
    detector: int

    def to_dict(self) -> dict:
        return {f.name: _encode(getattr(self, f.name)) for f in fields(self)}

    @classmethod
    def from_dict(cls, data: dict) -> Exposure:
        return cls(
            item=data["item"],
            version=data["version"],
            rules=tuple(data["rules"]),
            session=data["session"],
            turn=data["turn"],
            day=data["day"],
            via=ExposureVia(data["via"]),
            call=data["call"],
            model=data["model"],
            cli=data["cli"],
            detector=data["detector"],
        )


@dataclass(frozen=True)
class Correction:
    """One human message that corrects the agent, with its candidate exposures."""

    id: str
    host: str
    session: str
    turn: int
    day: str
    source_id: str
    byte_offset: int | None
    model: str | None
    cli: str
    detector: int
    candidates: tuple[str, ...]
    quarantine: tuple[str, ...]
    status: CorrectionStatus
    ts: str = ""

    def to_dict(self) -> dict:
        return {f.name: _encode(getattr(self, f.name)) for f in fields(self)}

    @classmethod
    def from_dict(cls, data: dict) -> Correction:
        return cls(
            id=data["id"],
            host=data["host"],
            session=data["session"],
            turn=data["turn"],
            day=data["day"],
            source_id=data["source_id"],
            byte_offset=data["byte_offset"],
            model=data["model"],
            cli=data["cli"],
            detector=data["detector"],
            candidates=tuple(data["candidates"]),
            quarantine=tuple(data["quarantine"]),
            status=CorrectionStatus(data["status"]),
            ts=data.get("ts", ""),
        )


@dataclass(frozen=True)
class Attribution:
    """A recorded verdict linking one correction to one exposed item."""

    correction: str
    verdict: Verdict
    item: str | None
    durable: bool
    retracts: bool
    session: str
    turn: int
    day: str

    def to_dict(self) -> dict:
        return {f.name: _encode(getattr(self, f.name)) for f in fields(self)}

    @classmethod
    def from_dict(cls, data: dict) -> Attribution:
        return cls(
            correction=data["correction"],
            verdict=Verdict(data["verdict"]),
            item=data["item"],
            durable=data["durable"],
            retracts=data["retracts"],
            session=data["session"],
            turn=data["turn"],
            day=data["day"],
        )
