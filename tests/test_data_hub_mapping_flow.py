from dataclasses import dataclass

from modules.data_hub import build_mapped_upload, inspect_uploaded_dataset


@dataclass
class Upload:
    name: str
    payload: bytes
    type: str = "text/csv"

    def getvalue(self) -> bytes:
        return self.payload


def test_confirmed_mapping_rewrites_headers_for_downstream_parser():
    source = Upload(
        "odd-sales.csv",
        b"Item Description,Dept,Qty Movement\nBlue Dream,Flower,10\n",
    )

    mapped = build_mapped_upload(
        source,
        "Product Sales",
        {
            "Product": "Item Description",
            "Category": "Dept",
            "Units sold": "Qty Movement",
        },
    )
    inspection = inspect_uploaded_dataset(mapped, "Product Sales")

    assert inspection["quality"] == "Ready"
    assert inspection["matches"] == {
        "Product": "Product Name",
        "Units sold": "Quantity Sold",
        "Category": "Category",
    }
    rendered = mapped.getvalue().decode("utf-8")
    assert "Product Name" in rendered
    assert "Quantity Sold" in rendered
    assert "Category" in rendered


def test_mapping_normalization_refuses_unresolved_required_fields():
    source = Upload(
        "odd-sales.csv",
        b"Item Description,Qty Movement\nBlue Dream,10\n",
    )

    try:
        build_mapped_upload(
            source,
            "Product Sales",
            {"Product": "Item Description", "Units sold": "Qty Movement"},
        )
    except ValueError as exc:
        assert "Category" in str(exc)
    else:
        raise AssertionError("Expected unresolved mapping to block normalization")
