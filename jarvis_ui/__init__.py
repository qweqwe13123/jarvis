# JARVIS UI package

# Re-apply clap-filter wake agent whenever UI code loads (frozen main may overwrite it).
try:
    from jarvis_ui.wake_bootstrap import ensure_clap_wake_async

    ensure_clap_wake_async(delay_s=1.0)
except Exception:
    pass
