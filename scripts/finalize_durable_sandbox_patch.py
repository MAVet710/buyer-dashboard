from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"missing patch anchor: {label}")
    return text.replace(old, new, 1)


# The catalog is now a first-class durable sandbox source, so restoration must
# require it instead of silently rebuilding it when a persisted set is damaged.
demo_path = Path("services/demo_data.py")
demo = demo_path.read_text(encoding="utf-8")
demo = replace_once(
    demo,
    '    required = {\n        "buyer_inventory",',
    '    required = {\n        "buyer_catalog",\n        "buyer_inventory",',
    "durable buyer catalog requirement",
)
demo_path.write_text(demo, encoding="utf-8")

# Avoid a magic upload-count assertion. The durable catalog increased the source
# set and future sandbox sources should not require editing this test again.
test_path = Path("tests/test_demo_simulation.py")
test = test_path.read_text(encoding="utf-8")
test = replace_once(
    test,
    '    assert len(state["data_hub_import_history"]) == 20',
    '    assert len(state["data_hub_import_history"]) == len(state["demo_upload_catalog"])',
    "dynamic sandbox upload count",
)
test_path.write_text(test, encoding="utf-8")
