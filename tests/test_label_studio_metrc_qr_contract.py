from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_label_studio_qr_is_bound_to_assigned_finished_metrc_tag():
    workflow = (ROOT / "modules" / "label_studio_workflow.py").read_text(encoding="utf-8")
    frontend = (ROOT / "frontend" / "src" / "components" / "InventoryDrivenLabelWorkflow.tsx").read_text(encoding="utf-8")

    # Backend traceability must build the QR payload from the exact finished
    # METRC package tag assigned to the durable label-production run.
    assert 'tag = _text(run.metrc_package_tag)' in workflow
    assert '"qr": {"value": tag, "svg": _qr_svg(tag)}' in workflow

    # The printed label must refuse to render a QR whose payload disagrees with
    # the assigned tag and must print the human-readable last five characters
    # directly beneath the QR for quick physical verification.
    assert 'const qrValue=String(run.traceability.qr?.value??"").trim();' in frontend
    assert 'if(!tag||qrValue!==tag)return null;' in frontend
    assert '.slice(-5)' in frontend
    assert 'className="printed-metrc-tag-suffix"' in frontend
    assert 'data-metrc-tag={tag}' in frontend
    assert 'QR code for finished METRC package ${tag}' in frontend


def test_compact_label_layouts_use_the_verified_metrc_qr_component():
    frontend = (ROOT / "frontend" / "src" / "components" / "InventoryDrivenLabelWorkflow.tsx").read_text(encoding="utf-8")

    assert frontend.count('<PrintedMetrcQr run={run}/>') == 2
    assert 'The QR encodes the exact finished-package METRC tag assigned in step 5.' in frontend
