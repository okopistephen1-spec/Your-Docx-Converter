from pathlib import Path


def test_profile_frontend_reads_config_after_deferred_load():
    profile_html = (Path(__file__).resolve().parents[1] / "frontend" / "profile.html").read_text(encoding="utf-8")

    assert '<script src="./config.js" defer></script>' in profile_html
    assert 'window.APP_CONFIG = window.APP_CONFIG || {' not in profile_html
    assert 'googleClientId: ""' not in profile_html
    assert 'const googleClientId = getGoogleClientId();' in profile_html
    assert 'function getAppConfig()' in profile_html
    assert 'function getGoogleClientId()' in profile_html
    assert "document.addEventListener('DOMContentLoaded'" in profile_html
    assert 'initializeGoogleSignIn()' in profile_html
