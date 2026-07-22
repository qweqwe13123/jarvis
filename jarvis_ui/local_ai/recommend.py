"""Pick one Ollama model that fits this computer."""

from __future__ import annotations

from dataclasses import dataclass

from jarvis_ui.local_ai.hardware import HardwareProfile, probe_hardware


@dataclass(frozen=True)
class ModelRecommendation:
    model_id: str  # e.g. llama3.2:3b
    label: str  # Light & fast
    blurb: str  # short why
    size_gb: float  # approx download
    tier: str  # light | smart | coding
    ok_for_disk: bool


# Conservative sizes (compressed GGUF on disk ≈ this).
_CATALOG = {
    "llama3.2:1b": ("Light & fast", "Best for small laptops", 1.3, "light"),
    "llama3.2:3b": ("Good for chat", "Balanced speed and quality", 2.0, "smart"),
    "qwen2.5:7b": ("Smart (recommended)", "Strong answers on most PCs", 4.7, "smart"),
    "llama3.1:8b": ("Smart+", "Higher quality if you have memory", 4.9, "smart"),
    "qwen2.5-coder:7b": ("For coding", "Best for Forge and code help", 4.7, "coding"),
}


def recommend_model(
    hw: HardwareProfile | None = None,
    *,
    prefer_coding: bool = False,
) -> ModelRecommendation:
    hw = hw or probe_hardware()
    ram = hw.ram_gb
    # Apple Silicon shares RAM — leave headroom for OS + AURA.
    effective = ram * (0.85 if hw.apple_silicon else 1.0)

    if prefer_coding and effective >= 14:
        model_id = "qwen2.5-coder:7b"
    elif effective < 7.5:
        model_id = "llama3.2:1b"
    elif effective < 12:
        model_id = "llama3.2:3b"
    elif effective < 20:
        # Prefer Qwen 7B on mid machines; NVIDIA helps too.
        model_id = "qwen2.5:7b" if (hw.has_nvidia or hw.apple_silicon or effective >= 14) else "llama3.2:3b"
    else:
        model_id = "llama3.1:8b"

    label, blurb, size_gb, tier = _CATALOG[model_id]
    ok_disk = hw.disk_free_gb >= (size_gb + 2.0)
    if not ok_disk:
        blurb = f"Needs ~{size_gb:.0f} GB free — free some disk space first"
    return ModelRecommendation(
        model_id=model_id,
        label=label,
        blurb=blurb,
        size_gb=size_gb,
        tier=tier,
        ok_for_disk=ok_disk,
    )


def catalog_for_hardware(hw: HardwareProfile | None = None) -> list[ModelRecommendation]:
    """2–3 options the UI can show (still simple)."""
    hw = hw or probe_hardware()
    primary = recommend_model(hw)
    coding = recommend_model(hw, prefer_coding=True)
    light = recommend_model(
        HardwareProfile(
            os_name=hw.os_name,
            arch=hw.arch,
            ram_gb=min(hw.ram_gb, 6.0),
            disk_free_gb=hw.disk_free_gb,
            apple_silicon=hw.apple_silicon,
            has_nvidia=False,
            cpu_cores=hw.cpu_cores,
            summary=hw.summary,
        )
    )
    seen: set[str] = set()
    out: list[ModelRecommendation] = []
    for rec in (primary, coding, light):
        if rec.model_id in seen:
            continue
        seen.add(rec.model_id)
        out.append(rec)
    return out
