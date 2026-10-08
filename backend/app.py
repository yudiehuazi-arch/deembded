from __future__ import annotations

import re
import time
import uuid
from collections import OrderedDict
from pathlib import Path
from threading import Lock
from typing import Any

import numpy as np
import skrf as rf
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from . import deembed_engine

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "static"
MAX_FILE_BYTES = 50 * 1024 * 1024
SUPPORTED_PORTS = {2, 4}
NETWORK_KEYS = ("total", "dut", "fix_a", "fix_b", "thru_a", "thru_b")
CACHE_TTL_SECONDS = 10 * 60
MAX_INSPECTION_CACHE_ITEMS = 4
MAX_INSPECTION_CACHE_BYTES = 256 * 1024 * 1024
MAX_RESULT_CACHE_ITEMS = 2
MAX_RESULT_CACHE_BYTES = 384 * 1024 * 1024
_CACHE_LOCK = Lock()
_INSPECTION_CACHE: OrderedDict[str, tuple[float, tuple[rf.Network, rf.Network, rf.Network], int]] = OrderedDict()
_RESULT_CACHE: OrderedDict[str, tuple[float, dict[str, rf.Network], int]] = OrderedDict()


def _estimated_network_bytes(networks: list[rf.Network] | tuple[rf.Network, ...]) -> int:
    return sum(int(np.asarray(network.s).nbytes + np.asarray(network.f).nbytes + np.asarray(network.z0).nbytes) for network in networks)


def _purge_expired(cache: OrderedDict, now: float) -> None:
    for token in list(cache.keys()):
        if cache[token][0] <= now:
            del cache[token]


def _store_inspection_networks(networks: tuple[rf.Network, rf.Network, rf.Network]) -> str | None:
    size = _estimated_network_bytes(networks)
    if size > MAX_INSPECTION_CACHE_BYTES:
        return None
    now = time.monotonic()
    token = uuid.uuid4().hex
    with _CACHE_LOCK:
        _purge_expired(_INSPECTION_CACHE, now)
        total_size = sum(entry[2] for entry in _INSPECTION_CACHE.values())
        while _INSPECTION_CACHE and (len(_INSPECTION_CACHE) >= MAX_INSPECTION_CACHE_ITEMS or total_size + size > MAX_INSPECTION_CACHE_BYTES):
            _, (_, _, evicted_size) = _INSPECTION_CACHE.popitem(last=False)
            total_size -= evicted_size
        _INSPECTION_CACHE[token] = (now + CACHE_TTL_SECONDS, networks, size)
    return token


def _get_inspection_networks(token: str) -> tuple[rf.Network, rf.Network, rf.Network] | None:
    now = time.monotonic()
    with _CACHE_LOCK:
        _purge_expired(_INSPECTION_CACHE, now)
        entry = _INSPECTION_CACHE.get(token)
        if entry is None:
            return None
        _INSPECTION_CACHE.move_to_end(token)
        return entry[1]


def _store_result_networks(networks: dict[str, rf.Network]) -> str | None:
    size = _estimated_network_bytes(tuple(networks.values()))
    if size > MAX_RESULT_CACHE_BYTES:
        return None
    now = time.monotonic()
    token = uuid.uuid4().hex
    with _CACHE_LOCK:
        _purge_expired(_RESULT_CACHE, now)
        total_size = sum(entry[2] for entry in _RESULT_CACHE.values())
        while _RESULT_CACHE and (len(_RESULT_CACHE) >= MAX_RESULT_CACHE_ITEMS or total_size + size > MAX_RESULT_CACHE_BYTES):
            _, (_, _, evicted_size) = _RESULT_CACHE.popitem(last=False)
            total_size -= evicted_size
        _RESULT_CACHE[token] = (now + CACHE_TTL_SECONDS, networks, size)
    return token


def _get_result_network(token: str, key: str) -> rf.Network | None:
    now = time.monotonic()
    with _CACHE_LOCK:
        _purge_expired(_RESULT_CACHE, now)
        entry = _RESULT_CACHE.get(token)
        if entry is None:
            return None
        _RESULT_CACHE.move_to_end(token)
        return entry[1].get(key)


def _get_result_networks(token: str) -> dict[str, rf.Network] | None:
    now = time.monotonic()
    with _CACHE_LOCK:
        _purge_expired(_RESULT_CACHE, now)
        entry = _RESULT_CACHE.get(token)
        if entry is None:
            return None
        _RESULT_CACHE.move_to_end(token)
        return dict(entry[1])


app = FastAPI(
    title="RF De-embedding Workbench",
    description="Split independent 2X Thru A/B standards and de-embed a measured fixture-DUT-fixture network.",
    version="1.1.0",
)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-store, no-cache, must-revalidate"})


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "engine": "scikit-rf IEEE 370 NZC 2X Thru"}


def _infer_ports(filename: str, text: str) -> int:
    """Infer Touchstone port count from a standard filename or data block."""
    match = re.search(r"\.s(\d+)p(?:\.txt)?$", filename.lower())
    if match:
        return int(match.group(1))

    match = re.search(r"\[\s*number\s+of\s+ports\s*\]\s*(\d+)", text, re.I)
    if match:
        return int(match.group(1))

    numeric_tokens: list[float] = []
    for raw in text.splitlines():
        line = raw.split("!", 1)[0].strip()
        if not line or line.startswith(("#", "[")):
            continue
        for token in re.split(r"[\s,]+", line):
            if not token:
                continue
            try:
                numeric_tokens.append(float(token.replace("D", "E").replace("d", "e")))
            except ValueError:
                continue

    # Touchstone v1 has 1 + 2*N*N numeric values per frequency point.
    matches = [ports for ports in (4, 2, 1) if numeric_tokens and len(numeric_tokens) % (1 + 2 * ports * ports) == 0]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ValueError("文本数据无法唯一判断端口数，请保留 .s2p 或 .s4p 扩展名。")
    raise ValueError("无法判断 Touchstone 端口数，请使用 .s2p 或 .s4p 文件名。")


async def _read_network(upload: UploadFile, label: str) -> rf.Network:
    filename = Path(upload.filename or f"{label}.s2p").name
    raw = await upload.read()
    if not raw:
        raise HTTPException(status_code=400, detail=f"{label} 文件为空。")
    if len(raw) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail=f"{label} 文件超过 50 MB 限制。")

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = raw.decode("ascii")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"{label} 不是可识别的文本 Touchstone 文件。") from exc

    try:
        nports = _infer_ports(filename, text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{label}：{exc}") from exc
    if nports not in SUPPORTED_PORTS:
        raise HTTPException(status_code=400, detail=f"{label}：目前仅支持 S2P 或 S4P，检测到 {nports} 个端口。")

    try:
        return deembed_engine.load_network_from_str(text, f"{label}.s{nports}p")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"{label} 解析失败：{exc}") from exc


async def _load_triplet(total_file: UploadFile, thru_a_file: UploadFile, thru_b_file: UploadFile) -> tuple[rf.Network, rf.Network, rf.Network]:
    total_net = await _read_network(total_file, "Total")
    thru_a_net = await _read_network(thru_a_file, "2X Thru A")
    thru_b_net = await _read_network(thru_b_file, "2X Thru B")
    port_counts = {total_net.nports, thru_a_net.nports, thru_b_net.nports}
    if len(port_counts) != 1:
        raise HTTPException(status_code=400, detail="Total、2X Thru A、2X Thru B 的端口数必须一致；请勿混用 S2P 与 S4P。")
    if total_net.nports not in SUPPORTED_PORTS:
        raise HTTPException(status_code=400, detail="目前仅支持单端 S2P 或差分 S4P 网络。")
    return total_net, thru_a_net, thru_b_net


def _renormalize(network: rf.Network, z0: float) -> rf.Network:
    result = network.copy()
    if not np.allclose(np.asarray(result.z0), z0, rtol=1e-6, atol=1e-6):
        result.renormalize(z0)
    return result


def _align_to_total_grid(networks: list[rf.Network]) -> list[rf.Network]:
    """Interpolate on Total's frequency points inside the common measured band."""
    if not networks:
        return []
    for network in networks:
        f = np.asarray(network.f, dtype=float)
        if len(f) < 8:
            raise HTTPException(status_code=400, detail="每个文件至少需要 8 个频率点才能进行可靠的 2X Thru 劈半。")
        if not np.all(np.isfinite(f)) or np.any(np.diff(f) <= 0):
            raise HTTPException(status_code=400, detail="频率点必须为有限值且严格递增。")

    f_min = max(float(network.f[0]) for network in networks)
    f_max = min(float(network.f[-1]) for network in networks)
    if f_max <= f_min:
        raise HTTPException(status_code=400, detail="Total、2X Thru A、2X Thru B 的频率范围没有重叠。")

    base_f = np.asarray(networks[0].f, dtype=float)
    common_f = base_f[(base_f >= f_min) & (base_f <= f_max)]
    if len(common_f) < 8:
        raise HTTPException(status_code=400, detail="三份文件的共同频段内不足 8 个 Total 频率点，无法稳定计算。")

    common_freq = rf.Frequency.from_f(common_f, unit="hz")
    aligned: list[rf.Network] = []
    for network in networks:
        if len(network.f) == len(common_f) and np.allclose(network.f, common_f, rtol=1e-12, atol=1e-3):
            aligned.append(network.copy())
        else:
            try:
                aligned.append(network.interpolate(common_freq, kind="linear"))
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"频率网格插值失败：{exc}") from exc
    return aligned


def _effective_mapping(total: rf.Network, requested: str) -> str:
    if total.nports == 2:
        return "single-ended"
    if requested == "auto":
        return deembed_engine.auto_detect_port_mapping(total)
    return requested


def _pair_labels(nports: int, mapping: str) -> tuple[list[str], list[str]]:
    if nports == 2:
        return ["P1"], ["P2"]
    if mapping == "plts":
        return ["P1 (+)", "P3 (−)"], ["P2 (+)", "P4 (−)"]
    return ["P1 (+)", "P2 (−)"], ["P3 (+)", "P4 (−)"]


def _sample_network(network: rf.Network, indices: np.ndarray) -> rf.Network:
    frequencies = np.asarray(network.f, dtype=float)[indices]
    z0 = np.asarray(network.z0)
    sampled_z0 = z0[indices] if z0.ndim > 1 else z0
    return rf.Network(
        frequency=rf.Frequency.from_f(frequencies, unit="hz"),
        s=np.asarray(network.s)[indices],
        z0=sampled_z0,
    )


def _mixed_mode_db(network: rf.Network, port_mapping: str) -> dict[str, np.ndarray]:
    """Convert only the mixed-mode dB traces needed by the UI; skip phase/list work."""
    work = network.copy()
    if port_mapping == "plts":
        work.renumber([0, 1, 2, 3], [0, 2, 1, 3])
    work.se2gmm(p=2)
    s = np.asarray(work.s)
    entries = {
        "SDD11": s[:, 0, 0], "SDD21": s[:, 1, 0], "SDD12": s[:, 0, 1], "SDD22": s[:, 1, 1],
        "SCC11": s[:, 2, 2], "SCC21": s[:, 3, 2], "SCC12": s[:, 2, 3], "SCC22": s[:, 3, 3],
        "SCD21": s[:, 3, 0], "SCD11": s[:, 2, 0], "SCD12": s[:, 2, 1], "SCD22": s[:, 3, 1],
        "SDC21": s[:, 1, 2], "SDC11": s[:, 0, 2], "SDC12": s[:, 0, 3], "SDC22": s[:, 1, 3],
    }
    return {name: 20.0 * np.log10(np.maximum(np.abs(values), 1e-12)) for name, values in entries.items()}


def _network_preview(
    network: rf.Network,
    port_mapping: str,
    max_points: int = 500,
    mixed_mode_db: dict[str, np.ndarray] | None = None,
) -> dict[str, Any]:
    n = len(network.f)
    step = max(1, int(np.ceil(n / max_points)))
    indices = np.arange(0, n, step, dtype=int)
    if indices[-1] != n - 1:
        indices = np.append(indices, n - 1)
    series: dict[str, list[float]] = {}
    for i in range(network.nports):
        for j in range(network.nports):
            series[f"S{i + 1}{j + 1}"] = _db(network.s[indices, i, j])
    if network.nports == 4:
        if mixed_mode_db is None:
            mixed_mode_db = _mixed_mode_db(_sample_network(network, indices), port_mapping)
            mixed_indices = np.arange(len(indices), dtype=int)
        else:
            mixed_indices = indices
        for name, values in mixed_mode_db.items():
            series[name] = np.asarray(values, dtype=float)[mixed_indices].tolist()
    return {"freq_ghz": (network.f[indices] / 1e9).astype(float).tolist(), "series": series}


def _level_crossings(freq_ghz: np.ndarray, difference_db: np.ndarray, target_db: float, tolerance_db: float = 1e-6) -> dict[str, list[Any]]:
    """Return interpolated roots and contiguous equal-to-target frequency spans."""
    freq = np.asarray(freq_ghz, dtype=float).reshape(-1)
    residual = np.asarray(difference_db, dtype=float).reshape(-1) - float(target_db)
    n = min(len(freq), len(residual))
    points: list[float] = []
    ranges: list[list[float]] = []
    i = 0
    while i < n:
        if not np.isfinite(freq[i]) or not np.isfinite(residual[i]):
            i += 1
            continue
        if abs(residual[i]) <= tolerance_db:
            start = i
            end = i
            while end + 1 < n and np.isfinite(freq[end + 1]) and np.isfinite(residual[end + 1]) and abs(residual[end + 1]) <= tolerance_db:
                end += 1
            if end > start:
                ranges.append([float(freq[start]), float(freq[end])])
            else:
                points.append(float(freq[start]))
            i = end + 1
            continue
        if i + 1 < n and np.isfinite(freq[i + 1]) and np.isfinite(residual[i + 1]):
            next_residual = residual[i + 1]
            if abs(next_residual) > tolerance_db and residual[i] * next_residual < 0:
                fraction = -residual[i] / (next_residual - residual[i])
                root = freq[i] + fraction * (freq[i + 1] - freq[i])
                points.append(float(root))
        i += 1
    return {"points_ghz": points, "ranges_ghz": ranges}


def _fixture_statistics(
    network: rf.Network,
    port_mapping: str,
    mixed_mode_db: dict[str, np.ndarray] | None = None,
) -> list[dict[str, Any]]:
    if network.nports != 4:
        return []
    values = mixed_mode_db if mixed_mode_db is not None else _mixed_mode_db(network, port_mapping)
    rules = (
        ("SDD21 − SDD22 = 5 dB", "SDD21", "SDD22", 5.0),
        ("SDD12 − SDD11 = 5 dB", "SDD12", "SDD11", 5.0),
        ("SDD22 = SDD21", "SDD22", "SDD21", 0.0),
        ("SDD11 = SDD12", "SDD11", "SDD12", 0.0),
    )
    freq_ghz = np.asarray(network.f, dtype=float) / 1e9
    report: list[dict[str, Any]] = []
    for label, first, second, target in rules:
        crossings = _level_crossings(freq_ghz, values[first] - values[second], target)
        report.append({"label": label, "target_db": target, **crossings})
    return report


@app.post("/api/inspect")
async def inspect_files(
    total: UploadFile | None = File(None),
    thru_a: UploadFile | None = File(None),
    thru_b: UploadFile | None = File(None),
    port_mapping: str = Form("auto"),
    inspection_token: str | None = Form(None),
) -> dict[str, Any]:
    if port_mapping not in {"auto", "sequential", "plts"}:
        raise HTTPException(status_code=400, detail="S4P 端口映射设置无效。")
    cached_networks = _get_inspection_networks(inspection_token) if inspection_token else None
    if cached_networks is not None:
        total_net, thru_a_net, thru_b_net = cached_networks
    else:
        if total is None or thru_a is None or thru_b is None:
            raise HTTPException(status_code=410 if inspection_token else 400, detail="文件识别缓存已过期或输入文件缺失，请重新选择三个文件。")
        total_net, thru_a_net, thru_b_net = await _load_triplet(total, thru_a, thru_b)
    parsed_networks = (total_net, thru_a_net, thru_b_net)
    effective_mapping = _effective_mapping(total_net, port_mapping)
    mixed_a = mixed_b = None
    if total_net.nports == 4:
        mixed_a = _mixed_mode_db(thru_a_net, effective_mapping)
        mixed_b = _mixed_mode_db(thru_b_net, effective_mapping)
    file_previews = {
        "thru_a": _network_preview(thru_a_net, effective_mapping, mixed_mode_db=mixed_a),
        "total": _network_preview(total_net, effective_mapping),
        "thru_b": _network_preview(thru_b_net, effective_mapping, mixed_mode_db=mixed_b),
    }
    fixture_statistics = None
    if total_net.nports == 4:
        fixture_statistics = {
            "thru_a": _fixture_statistics(thru_a_net, effective_mapping, mixed_a),
            "thru_b": _fixture_statistics(thru_b_net, effective_mapping, mixed_b),
        }
    aligned = _align_to_total_grid([total_net, thru_a_net, thru_b_net])
    total_net = aligned[0]
    left_ports, right_ports = _pair_labels(total_net.nports, effective_mapping)
    inspection_token = _store_inspection_networks(parsed_networks)
    return {
        "success": True,
        "inspection_token": inspection_token,
        "nports": int(total_net.nports),
        "topology": "单端 S2P" if total_net.nports == 2 else "差分 S4P",
        "requested_mapping": port_mapping,
        "detected_mapping": effective_mapping,
        "mapping_label": "单端双端口" if total_net.nports == 2 else ("PLTS 交叉 · 1/3 → 2/4" if effective_mapping == "plts" else "标准顺序 · 1/2 → 3/4"),
        "left_ports": left_ports,
        "right_ports": right_ports,
        "file_previews": file_previews,
        "fixture_statistics": fixture_statistics,
        "frequency_start_ghz": float(total_net.f[0] / 1e9),
        "frequency_stop_ghz": float(total_net.f[-1] / 1e9),
        "points": int(len(total_net.f)),
    }


def _db(values: np.ndarray) -> list[float]:
    return (20.0 * np.log10(np.maximum(np.abs(values), 1e-12))).astype(float).tolist()


def _chart_data(networks: dict[str, rf.Network], port_mapping: str) -> dict[str, Any]:
    total = networks["total"]
    n = len(total.f)
    step = max(1, int(np.ceil(n / 600)))
    indices = np.arange(0, n, step, dtype=int)
    if indices[-1] != n - 1:
        indices = np.append(indices, n - 1)
    freq_ghz = (total.f[indices] / 1e9).astype(float).tolist()

    spectra: dict[str, dict[str, list[float]]] = {}
    for network_key, network in networks.items():
        current: dict[str, list[float]] = {}
        for i in range(network.nports):
            for j in range(network.nports):
                name = f"S{i + 1}{j + 1}"
                current[name] = _db(network.s[indices, i, j])
        if network.nports == 4:
            # The UI chart is capped at 600 points; convert only those samples to mixed mode.
            mm = _mixed_mode_db(_sample_network(network, indices), port_mapping)
            for name, values in mm.items():
                current[name] = np.asarray(values, dtype=float).tolist()
        spectra[network_key] = current

    parameters = list(spectra["total"].keys())
    series = {
        parameter: {network_key: spectra[network_key][parameter] for network_key in networks}
        for parameter in parameters
    }
    return {"freq_ghz": freq_ghz, "network_keys": list(networks.keys()), "series": series}


@app.post("/api/deembed")
async def run_deembed(
    total: UploadFile | None = File(None),
    thru_a: UploadFile | None = File(None),
    thru_b: UploadFile | None = File(None),
    side: str = Form("both"),
    port_mapping: str = Form("auto"),
    reference_z0: float = Form(50.0),
    inspection_token: str | None = Form(None),
) -> dict[str, Any]:
    if side not in {"both", "left", "right"}:
        raise HTTPException(status_code=400, detail="去嵌侧设置无效。")
    if port_mapping not in {"auto", "sequential", "plts"}:
        raise HTTPException(status_code=400, detail="S4P 端口映射设置无效。")
    if not np.isfinite(reference_z0) or reference_z0 <= 0:
        raise HTTPException(status_code=400, detail="参考阻抗必须是大于 0 的有限数值。")

    if inspection_token:
        cached_networks = _get_inspection_networks(inspection_token)
        if cached_networks is None:
            raise HTTPException(status_code=410, detail="文件识别缓存已过期，请重新选择或等待文件重新识别。")
        networks = list(cached_networks)
    else:
        if total is None or thru_a is None or thru_b is None:
            raise HTTPException(status_code=400, detail="请上传 Total、2X Thru A 与 2X Thru B，或使用有效的识别缓存。")
        networks = await _load_triplet(total, thru_a, thru_b)
    networks = [_renormalize(network, float(reference_z0)) for network in networks]
    total_net, thru_a_net, thru_b_net = _align_to_total_grid(networks)
    effective_mapping = _effective_mapping(total_net, port_mapping)
    left_ports, right_ports = _pair_labels(total_net.nports, effective_mapping)
    mapping_label = "单端双端口" if total_net.nports == 2 else ("PLTS 交叉 · 1/3 → 2/4" if effective_mapping == "plts" else "标准顺序 · 1/2 → 3/4")

    try:
        if total_net.nports == 2:
            dut_net, fix_a, fix_b = deembed_engine.dual_2xthru_deembed_2port(
                total=total_net,
                thru_2x_a=thru_a_net,
                thru_2x_b=thru_b_net,
                side=side,
                z0=float(reference_z0),
            )
            topology = "单端 S2P"
        else:
            dut_net, fix_a, fix_b = deembed_engine.dual_2xthru_deembed_4port(
                total=total_net,
                thru_2x_a=thru_a_net,
                thru_2x_b=thru_b_net,
                side=side,
                z0=float(reference_z0),
                port_mapping=effective_mapping,
            )
            topology = "差分 S4P"

        quality = deembed_engine.quality_check(dut_net)
        display_networks = {
            "total": total_net,
            "dut": dut_net,
            "fix_a": fix_a,
            "fix_b": fix_b,
            "thru_a": thru_a_net,
            "thru_b": thru_b_net,
        }
        chart = _chart_data(display_networks, effective_mapping)
        result_token = _store_result_networks({"dut": dut_net, "fix_a": fix_a, "fix_b": fix_b})
        payload: dict[str, Any] = {
            "success": True,
            "result_token": result_token,
            "message": "去嵌计算完成。请结合夹具标准件结构与测量条件检查结果。",
            "topology": topology,
            "side": side,
            "port_mapping": effective_mapping if total_net.nports == 4 else None,
            "mapping_label": mapping_label,
            "left_ports": left_ports,
            "right_ports": right_ports,
            "reference_z0": float(reference_z0),
            "frequency_start_ghz": float(total_net.f[0] / 1e9),
            "frequency_stop_ghz": float(total_net.f[-1] / 1e9),
            "points": int(len(total_net.f)),
            "quality": quality,
            "chart": chart,
            "nports": int(dut_net.nports),
        }
        if result_token is None:
            # Extremely large result sets may exceed the in-memory export cache; preserve compatibility.
            payload.update({
                "dut_touchstone": deembed_engine.network_to_touchstone_str(dut_net, form="ri"),
                "fix_a_touchstone": deembed_engine.network_to_touchstone_str(fix_a, form="ri"),
                "fix_b_touchstone": deembed_engine.network_to_touchstone_str(fix_b, form="ri"),
            })
        return payload
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"去嵌计算失败：{type(exc).__name__}: {exc}") from exc


# TDR plot settings are deliberately bounded: the transform operates on an evenly spaced
# low-pass grid and the UI receives at most 6,000 points per trace.
TDR_MAX_UNIFORM_POINTS = 32768
TDR_MAX_DISPLAY_POINTS = 6000
TDR_WINDOWS: dict[str, str | None] = {
    "hamming": "hamming", "hann": "hann", "blackman": "blackman", "none": None,
}
TDR_DC_METHODS = {"linear", "hold"}


def _tdr_reflection(network: rf.Network, port: int, port_mapping: str, reference_z0: float) -> tuple[np.ndarray, str, float]:
    """Return the selected single-ended or differential reflection and its Z reference."""
    work = _renormalize(network, reference_z0)
    if work.nports == 2:
        index = port - 1
        return np.asarray(work.s[:, index, index], dtype=complex), f"S{port}{port}", float(reference_z0)
    if work.nports != 4:
        raise HTTPException(status_code=400, detail="TDR 目前仅支持 S2P 或 S4P 网络。")
    if port_mapping == "plts":
        work.renumber([0, 1, 2, 3], [0, 2, 1, 3])
    work.se2gmm(p=2)
    index = port - 1
    return np.asarray(work.s[:, index, index], dtype=complex), f"SDD{port}{port}", float(2.0 * reference_z0)


def _tdr_step_impedance(
    network: rf.Network,
    port: int,
    port_mapping: str,
    reference_z0: float,
    window: str,
    dc_method: str,
    rise_time_ps: float,
) -> dict[str, Any]:
    """Windowed low-pass step response, converted from reflection coefficient to impedance."""
    if port not in (1, 2):
        raise HTTPException(status_code=400, detail="TDR 端口必须为 1 或 2。")
    if window not in TDR_WINDOWS:
        raise HTTPException(status_code=400, detail="TDR 窗函数设置无效。")
    if dc_method not in TDR_DC_METHODS:
        raise HTTPException(status_code=400, detail="TDR 低频外推设置无效。")
    if not np.isfinite(reference_z0) or reference_z0 <= 0 or reference_z0 > 1000:
        raise HTTPException(status_code=400, detail="TDR 单端参考阻抗须为 0–1000 Ω 范围内的有限正数。")
    if not np.isfinite(rise_time_ps) or rise_time_ps < 0 or rise_time_ps > 10000:
        raise HTTPException(status_code=400, detail="TDR 上升时间须为 0–10000 ps。")

    frequency = np.asarray(network.f, dtype=float)
    if len(frequency) < 8 or not np.all(np.isfinite(frequency)) or np.any(np.diff(frequency) <= 0):
        raise HTTPException(status_code=400, detail="TDR 需要至少 8 个严格递增的有效频率点。")
    gamma, parameter, reference_ohm = _tdr_reflection(network, port, port_mapping, reference_z0)
    if not np.all(np.isfinite(gamma.real)) or not np.all(np.isfinite(gamma.imag)):
        raise HTTPException(status_code=422, detail=f"{parameter} 包含无效复数数据，无法生成 TDR。")

    f_max = float(frequency[-1])
    median_df = float(np.median(np.diff(frequency)))
    if f_max <= 0 or median_df <= 0:
        raise HTTPException(status_code=400, detail="TDR 频率范围或频率步进无效。")
    points = int(np.clip(round(f_max / median_df) + 1, 16, TDR_MAX_UNIFORM_POINTS))
    uniform_f = np.linspace(0.0, f_max, points, dtype=float)
    uniform_gamma = np.interp(uniform_f, frequency, gamma.real) + 1j * np.interp(uniform_f, frequency, gamma.imag)

    # Fill the unmeasured DC-to-first-point band. Linear extrapolation is the default;
    # "hold" anchors DC to the real part of the first measured reflection.
    if frequency[0] > 0:
        if dc_method == "linear" and len(frequency) >= 2:
            slope = (gamma[1] - gamma[0]) / (frequency[1] - frequency[0])
            gamma_dc = float(np.real(gamma[0] - frequency[0] * slope))
        else:
            gamma_dc = float(np.real(gamma[0]))
        low = uniform_f < frequency[0]
        ratio = np.clip(uniform_f[low] / frequency[0], 0.0, 1.0)
        uniform_gamma[low] = gamma_dc + (gamma[0] - gamma_dc) * ratio
    else:
        uniform_gamma[0] = float(np.real(gamma[0]))

    rise_time_s = float(rise_time_ps) * 1e-12
    if rise_time_s > 0:
        # Gaussian low-pass shaping with approximately the specified 10–90% step rise time.
        uniform_gamma *= np.exp(-3.005 * np.square(uniform_f * rise_time_s))

    one_port = rf.Network(
        frequency=rf.Frequency.from_f(uniform_f, unit="hz"),
        s=uniform_gamma[:, None, None],
        z0=float(reference_z0),
    )
    try:
        time_s, gamma_step = one_port.step_response(window=TDR_WINDOWS[window])
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"TDR 时域变换失败：{type(exc).__name__}: {exc}") from exc
    gamma_step = np.asarray(gamma_step).reshape(len(time_s), -1)[:, 0]
    time_s = np.asarray(time_s, dtype=float)
    denominator = 1.0 - gamma_step
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        impedance = reference_ohm * (1.0 + gamma_step) / denominator
    impedance = np.real(impedance)
    positive = np.flatnonzero(time_s >= 0.0)
    if not len(positive):
        raise HTTPException(status_code=422, detail="TDR 变换未生成非负时间数据。")
    if len(positive) > TDR_MAX_DISPLAY_POINTS:
        sample_positions = np.linspace(0, len(positive) - 1, TDR_MAX_DISPLAY_POINTS).round().astype(int)
        positive = positive[sample_positions]
    plotted_time = time_s[positive]
    plotted_impedance = impedance[positive]
    native_step_ps = float((time_s[1] - time_s[0]) * 1e12) if len(time_s) > 1 else 0.0
    finite_values: list[float | None] = [float(value) if np.isfinite(value) else None for value in plotted_impedance]
    return {
        "time_ns": (plotted_time * 1e9).astype(float).tolist(),
        "impedance_ohm": finite_values,
        "parameter": parameter,
        "reference_ohm": reference_ohm,
        "sample_step_ps": native_step_ps,
    }


def _tdr_settings(window: str, dc_method: str, rise_time_ps: float) -> dict[str, Any]:
    if window not in TDR_WINDOWS or dc_method not in TDR_DC_METHODS:
        raise HTTPException(status_code=400, detail="TDR 窗函数或低频外推设置无效。")
    if not np.isfinite(rise_time_ps) or rise_time_ps < 0 or rise_time_ps > 10000:
        raise HTTPException(status_code=400, detail="TDR 上升时间须为 0–10000 ps。")
    return {"window": window, "dc_method": dc_method, "rise_time_ps": float(rise_time_ps)}


@app.post("/api/tdr/input")
def input_network_tdr(
    inspection_token: str = Form(...),
    slot: str = Form(...),
    port: int = Form(1),
    port_mapping: str = Form("auto"),
    reference_z0: float = Form(50.0),
    window: str = Form("hamming"),
    dc_method: str = Form("linear"),
    rise_time_ps: float = Form(0.0),
) -> dict[str, Any]:
    if port_mapping not in {"auto", "sequential", "plts"}:
        raise HTTPException(status_code=400, detail="S4P 端口映射设置无效。")
    settings = _tdr_settings(window, dc_method, rise_time_ps)
    if not np.isfinite(reference_z0) or reference_z0 <= 0 or reference_z0 > 1000:
        raise HTTPException(status_code=400, detail="TDR 单端参考阻抗须为 0–1000 Ω 范围内的有限正数。")
    cached_networks = _get_inspection_networks(inspection_token)
    if cached_networks is None:
        raise HTTPException(status_code=410, detail="输入网络缓存已过期，请重新选择三个文件。")
    mapping = _effective_mapping(cached_networks[0], port_mapping)
    if slot == "all":
        aligned = _align_to_total_grid([_renormalize(network, float(reference_z0)) for network in cached_networks])
        ordered_networks = (("total", aligned[0]), ("thru_a", aligned[1]), ("thru_b", aligned[2]))
        series: dict[str, list[float | None]] = {}
        time_ns: list[float] | None = None
        sample_step_ps: float | None = None
        reference_ohm: float | None = None
        parameter: str | None = None
        for key, network in ordered_networks:
            transformed = _tdr_step_impedance(network, port, mapping, float(reference_z0), **settings)
            if time_ns is None:
                time_ns = transformed["time_ns"]
                sample_step_ps = transformed["sample_step_ps"]
                reference_ohm = transformed["reference_ohm"]
                parameter = transformed["parameter"]
            series[key] = transformed["impedance_ohm"]
        return {
            "success": True, "slot": "all", "time_ns": time_ns or [], "series": series,
            "sample_step_ps": sample_step_ps or 0.0, "reference_ohm": reference_ohm or 0.0,
            "parameter": parameter or "", "port_mapping": mapping, **settings,
        }
    slot_index = {"total": 0, "thru_a": 1, "thru_b": 2}.get(slot)
    if slot_index is None:
        raise HTTPException(status_code=400, detail="未知的输入网络类型。")
    network = cached_networks[slot_index]
    result = _tdr_step_impedance(network, port, mapping, float(reference_z0), **settings)
    result.update({"success": True, "slot": slot, "port_mapping": mapping, **settings})
    return result


@app.post("/api/tdr/result")
def result_networks_tdr(
    inspection_token: str = Form(...),
    result_token: str = Form(...),
    port: int = Form(1),
    port_mapping: str = Form("auto"),
    reference_z0: float = Form(50.0),
    window: str = Form("hamming"),
    dc_method: str = Form("linear"),
    rise_time_ps: float = Form(0.0),
) -> dict[str, Any]:
    if port_mapping not in {"auto", "sequential", "plts"}:
        raise HTTPException(status_code=400, detail="S4P 端口映射设置无效。")
    settings = _tdr_settings(window, dc_method, rise_time_ps)
    input_networks = _get_inspection_networks(inspection_token)
    if input_networks is None:
        raise HTTPException(status_code=410, detail="输入网络缓存已过期，请重新识别并运行去嵌。")
    computed = _get_result_networks(result_token)
    if computed is None:
        raise HTTPException(status_code=410, detail="去嵌结果缓存已过期，请重新运行计算。")
    if not np.isfinite(reference_z0) or reference_z0 <= 0 or reference_z0 > 1000:
        raise HTTPException(status_code=400, detail="TDR 单端参考阻抗须为 0–1000 Ω 范围内的有限正数。")

    mapping = _effective_mapping(input_networks[0], port_mapping)
    aligned_inputs = _align_to_total_grid([_renormalize(net, float(reference_z0)) for net in input_networks])
    networks: dict[str, rf.Network] = {
        "total": aligned_inputs[0],
        "thru_a": aligned_inputs[1],
        "thru_b": aligned_inputs[2],
        "dut": _renormalize(computed["dut"], float(reference_z0)),
        "fix_a": _renormalize(computed["fix_a"], float(reference_z0)),
        "fix_b": _renormalize(computed["fix_b"], float(reference_z0)),
    }
    series: dict[str, list[float | None]] = {}
    time_ns: list[float] | None = None
    sample_step_ps: float | None = None
    reference_ohm: float | None = None
    parameter: str | None = None
    for key, network in networks.items():
        transformed = _tdr_step_impedance(network, port, mapping, float(reference_z0), **settings)
        if time_ns is None:
            time_ns = transformed["time_ns"]
            sample_step_ps = transformed["sample_step_ps"]
            reference_ohm = transformed["reference_ohm"]
            parameter = transformed["parameter"]
        series[key] = transformed["impedance_ohm"]
    return {
        "success": True, "time_ns": time_ns or [], "series": series,
        "sample_step_ps": sample_step_ps or 0.0, "reference_ohm": reference_ohm or 0.0,
        "parameter": parameter or "", "port_mapping": mapping, **settings,
    }


@app.get("/api/download/{result_token}/{network_key}")
def download_result(result_token: str, network_key: str) -> PlainTextResponse:
    labels = {"dut": "DUT_deembedded", "fix_a": "Fixture_A_1X", "fix_b": "Fixture_B_1X"}
    if network_key not in labels:
        raise HTTPException(status_code=404, detail="未知的 Touchstone 导出类型。")
    network = _get_result_network(result_token, network_key)
    if network is None:
        raise HTTPException(status_code=410, detail="计算结果下载缓存已过期，请重新运行去嵌。")
    content = deembed_engine.network_to_touchstone_str(network, form="ri")
    filename = f"{labels[network_key]}.s{network.nports}p"
    return PlainTextResponse(content, headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"})
