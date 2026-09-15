from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_local_ma_metrc_wrapper_bootstraps_and_normalizes_payloads() -> None:
    source = (ROOT / "scripts" / "run_local_ma_metrc_evaluation.ps1").read_text(encoding="utf-8")

    assert "start_local_authenticated.ps1" in source
    assert ". $bootstrap" in source
    assert "$env:PYTHONPATH = $root" in source
    assert ".pilot-venv/Scripts/python.exe" in source
    assert "run_local_ma_metrc_evaluation.py" in source
    assert "UTF8Encoding($false)" in source
    assert "ConvertFrom-Json" in source
    assert "Package create requires location" in source
    assert "[System.IO.Path]::IsPathRooted($PayloadFile)" in source
    assert "[System.IO.Path]::GetFullPath($PayloadFile)" in source
    assert "METRC_INTEGRATOR_API_KEY" not in source
    assert "METRC_USER_API_KEY" not in source
    assert "integrator/setup" not in source.casefold()
