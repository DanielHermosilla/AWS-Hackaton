"""Bounded, temporary historical uploads; only summaries cross the HTTP boundary."""

from __future__ import annotations

import hashlib
import tempfile
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ev_routing.historical_energy import MAX_HISTORY_BYTES, MAX_HISTORY_JSON_BYTES

from .service import ProviderError, SolveRequestError, fingerprint


def _json_value(value):
    return value.model_dump(mode="json") if hasattr(value, "model_dump") else value


@dataclass
class HistoryEntry:
    profile_id: str
    filename: str
    temporary: Any
    path: Path
    size: int
    source_sha256: str
    inspection: dict
    data: Any = None
    mapping: dict | None = None
    status: str = "needs_mapping"
    warnings: list[str] = field(default_factory=list)
    ai_analysis: dict = field(default_factory=lambda: {
        "status": "not_requested", "message": "Todavía no se ha usado IA.",
    })
    fitted: OrderedDict = field(default_factory=OrderedDict)

    def public(self):
        summary = _json_value(self.data.summary) if self.data is not None else {}
        return {
            "profile_id": self.profile_id,
            "filename": self.filename,
            "source_sha256": self.source_sha256,
            "status": self.status,
            "summary": summary,
            "assumptions": summary.get("assumptions", []),
            "warnings": list(dict.fromkeys([*self.warnings, *summary.get("warnings", [])])),
            "ai_analysis": self.ai_analysis,
        }


class HistoryStore:
    """Called while the server's compute lock is held; no original file is modified."""

    def __init__(self, bedrock, *, max_profiles=2, max_bytes=2 * MAX_HISTORY_BYTES):
        self.bedrock = bedrock
        self.max_profiles, self.max_bytes = max_profiles, max_bytes
        self.entries: OrderedDict[str, HistoryEntry] = OrderedDict()

    def get(self, identifier):
        if not isinstance(identifier, str) or identifier not in self.entries:
            raise ProviderError(
                "El histórico ya no está disponible. Adjunta el archivo de nuevo "
                "o retíralo para usar el consumo supuesto.",
                "history_expired", 404,
            )
        return self.entries[identifier]

    def remove(self, identifier):
        entry = self.get(identifier)
        del self.entries[identifier]
        entry.temporary.cleanup()
        return {"removed": True, "profile_id": identifier}

    def cache_key(self, identifier):
        entry = self.get(identifier)
        return {
            "source_sha256": entry.source_sha256, "mapping": entry.mapping,
            "status": entry.status, "ai_analysis": entry.ai_analysis,
        }

    def close(self):
        for entry in self.entries.values():
            entry.temporary.cleanup()
        self.entries.clear()

    def load_example(self, *, data_directory=None):
        from ev_routing.energy import file_sha256

        from .scenarios import data_directory_path

        path = data_directory_path(data_directory) / "eVED_EV.csv"
        if not path.is_file():
            raise ProviderError(
                "Falta eVED_EV.csv en data/ del servidor. Adjunta tu histórico eléctrico "
                "para usarlo con las ubicaciones de la hackatón.",
                "example_history_unavailable", 404,
            )
        digest = file_sha256(path)
        for entry in self.entries.values():
            if entry.source_sha256 == digest:
                return entry.public()
        with path.open("rb") as stream:
            return self.upload(stream, path.stat().st_size, path.name)

    def upload(self, stream, length, filename):
        from ev_routing.historical_energy import (
            HistoryNeedsMapping,
            inspect_history,
            normalize_history,
        )

        if not 0 < length <= MAX_HISTORY_BYTES:
            raise ProviderError(
                "Adjunta un histórico CSV de hasta 4 GiB o JSON de hasta 256 MiB.",
                "history_too_large", 413,
            )
        filename = filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
        if (
            not filename or len(filename) > 180
            or any(ord(char) < 32 for char in filename)
            or Path(filename).suffix.lower() not in {".csv", ".json"}
        ):
            raise SolveRequestError("El histórico debe ser un archivo CSV o JSON.")
        if Path(filename).suffix.lower() == ".json" and length > MAX_HISTORY_JSON_BYTES:
            raise ProviderError(
                "El JSON histórico supera 256 MiB. Expórtalo como CSV (hasta 4 GiB).",
                "history_too_large", 413,
            )
        directory = tempfile.TemporaryDirectory(prefix="zmd-history-")
        path = Path(directory.name) / ("upload" + Path(filename).suffix.lower())
        digest = hashlib.sha256()
        remaining = length
        try:
            with path.open("xb") as output:
                path.chmod(0o600)
                while remaining:
                    block = stream.read(min(1024 * 1024, remaining))
                    if not block:
                        raise SolveRequestError("La carga se interrumpió. Adjunta el archivo de nuevo.")
                    output.write(block)
                    digest.update(block)
                    remaining -= len(block)
            source_hash = digest.hexdigest()
            for stored in self.entries.values():
                if stored.source_sha256 == source_hash:
                    directory.cleanup()
                    return stored.public()
            inspection = inspect_history(path)
            entry = HistoryEntry(
                str(uuid.uuid4()), filename, directory, path, length, source_hash, inspection,
            )
            try:
                entry.data = normalize_history(path)
                entry.status = "ready"
            except HistoryNeedsMapping as error:
                entry.warnings = [str(error)[:600]]
            except ValueError as error:
                # A known schema with invalid data must not be "fixed" by invented AI values.
                entry.status = "error"
                entry.warnings = [str(error)[:600]]
            while self.entries and (
                len(self.entries) >= self.max_profiles
                or sum(item.size for item in self.entries.values()) + length > self.max_bytes
            ):
                _, old = self.entries.popitem(last=False)
                old.temporary.cleanup()
            self.entries[entry.profile_id] = entry
        except Exception:
            directory.cleanup()
            raise
        # Known eVED remains usable when AWS is absent or the interpretation fails.
        if self.bedrock.status().get("connected") and entry.status != "error":
            self.analyze(entry.profile_id)
        elif entry.data is None and entry.status != "error":
            entry.ai_analysis = {
                "status": "unavailable",
                "message": "Conecta con AWS para interpretar las columnas y unidades de este archivo. "
                "Mientras tanto se conservará el consumo supuesto.",
            }
        return entry.public()

    def analyze(self, identifier):
        from ev_routing.historical_energy import normalize_history

        entry = self.get(identifier)
        if entry.status == "error":
            entry.ai_analysis = {
                "status": "error",
                "message": "Corrige los datos del archivo y adjúntalo de nuevo. "
                "La IA no reemplaza las mediciones inválidas.",
            }
            return entry.public()
        profile = dict(entry.inspection)
        if entry.data is not None:
            profile["computed_summary"] = _json_value(entry.data.summary)
        try:
            reply = _json_value(self.bedrock.analyze(profile))
            interpretation = _json_value(reply.get("interpretation", reply))
            mapping = _json_value(interpretation.get("mapping"))
            if entry.data is None:
                if not mapping:
                    raise ValueError("La IA no identificó un mapeo utilizable de columnas y unidades.")
                data = normalize_history(entry.path, mapping=mapping)
                entry.mapping, entry.data, entry.status = mapping, data, "ready"
                entry.warnings = []
                entry.fitted.clear()
                # One additional bounded request can explain full-file statistics.
                # Failure here must not discard a mapping already checked locally.
                profile["computed_summary"] = _json_value(data.summary)
                try:
                    explanation = _json_value(self.bedrock.analyze(profile))
                    explained = _json_value(explanation.get("interpretation", explanation))
                    usage = {}
                    for response in (reply, explanation):
                        for key, value in response.get("ai", {}).get("usage", {}).items():
                            if isinstance(value, (int, float)):
                                usage[key] = usage.get(key, 0) + value
                    reply, interpretation = explanation, explained
                    reply.setdefault("ai", {})["usage"] = usage
                except Exception:
                    entry.warnings.append(
                        "Las columnas se validaron, pero no se completó la explicación "
                        "adicional con IA. Los cálculos locales siguen disponibles."
                    )
            ai = reply.get("ai", {})
            entry.ai_analysis = {
                "status": "applied" if entry.mapping is not None else "reviewed",
                "message": "Interpretación validada. Los cálculos de consumo se realizan sobre el archivo.",
                "model_id": self.bedrock.status().get("model_id"),
                "reasoning_effort": "high",
                "usage": ai.get("usage", {}),
                "scope": ai.get("scope", "sample_profile_not_complete_file"),
                "observations": interpretation.get("observations", []),
                "assumptions": interpretation.get("assumptions", []),
                "limitations": interpretation.get("limitations", []),
                "unknowns": interpretation.get("unresolved_fields", []),
            }
        except Exception as error:
            # SDK and model errors may carry request details; never echo their repr/message.
            from .bedrock_session import BedrockSessionError

            message = str(error) if isinstance(error, BedrockSessionError) else (
                "No se pudo validar la interpretación. Revisa las columnas, sus unidades y "
                "que los datos correspondan a un vehículo eléctrico."
            )
            usage = getattr(error, "usage", {})
            usage = {
                key: value for key, value in usage.items()
                if key in {"inputTokens", "outputTokens", "totalTokens"}
                and isinstance(value, (int, float)) and not isinstance(value, bool)
                and value >= 0
            } if isinstance(usage, dict) else {}
            entry.ai_analysis = {
                "status": "error", "message": message,
                "reasoning_effort": "high", "usage": usage,
            }
        return entry.public()

    def apply(self, identifier, road, fallback_rate, *, synthetic=False):
        from ev_routing.historical_energy import (
            MODEL_VERSION,
            apply_historical_energy,
            fit_historical_energy,
            historical_network_fingerprint,
        )

        entry = self.get(identifier)
        if entry.data is None or synthetic:
            reason = (
                "La aproximación por distancia no identifica calles. Se conserva el consumo supuesto."
                if synthetic else
                "El histórico aún no tiene un mapeo validado. Se conserva el consumo supuesto."
            )
            report = {
                "model_id": "manual_fallback",
                "source_sha256": entry.source_sha256,
                "profile_id": identifier,
                "summary": {
                    **(_json_value(entry.data.summary) if entry.data is not None else {}),
                    "calibrated_arc_count": 0, "road_arc_count": len(road.arcs),
                    "arc_coverage_fraction": 0, "distance_coverage_fraction": 0,
                },
                "assumptions": [], "warnings": [reason],
                "ai_analysis": entry.ai_analysis,
            }
            from ev_routing.contracts import ProblemInstance

            updated = road.model_dump(mode="json")
            updated["provenance"]["energy_model"] = {
                **report, "kind": "manual_fallback", "fallback_kwh_per_km": fallback_rate,
            }
            return ProblemInstance.model_validate(updated), report
        # Geometry, arc identity and fallback costs determine this calibration.
        # Fleet capacity/SoC do not: changing them must not repeat GPS matching.
        key = fingerprint({
            "road": historical_network_fingerprint(road), "history": entry.source_sha256,
            "mapping": entry.mapping, "model_version": MODEL_VERSION,
        })
        profile = entry.fitted.get(key)
        if profile is None:
            profile = fit_historical_energy(entry.data, road)
            entry.fitted.clear()  # only the latest map per upload; bounded memory
            entry.fitted[key] = profile
        updated = apply_historical_energy(road, profile, fallback_rate)
        report = _json_value(profile)
        report = {key: value for key, value in report.items() if key != "estimates"}
        report.update(profile_id=identifier, ai_analysis=entry.ai_analysis)
        updated.provenance["energy_model"].update(
            profile_id=identifier, ai_analysis=entry.ai_analysis,
        )
        return updated, report
