import copy
import unittest

from modules.label_design import BLOCKS, validate_design


def design():
    return {"version": 1, "width_in": 4, "height_in": 6, "blocks": [
        {"id": key, "x": 0.1, "y": index * 0.5, "width": 3.8, "height": 0.4,
         "font_size": 8, "bold": False, "align": "left"}
        for index, key in enumerate(sorted(BLOCKS))
    ]}


class LabelDesignTests(unittest.TestCase):
    def test_custom_dimensions_and_content_are_separate(self):
        value = design()
        value["width_in"] = 4.125
        value["blocks"][0]["text"] = "Untrusted replacement"
        saved = validate_design(value)
        self.assertEqual(saved["width_in"], 4.125)
        self.assertNotIn("text", saved["blocks"][0])

    def test_invalid_dimensions_are_rejected(self):
        for number in (0, -1, 201, float("nan"), float("inf"), True, "4"):
            with self.subTest(number=number), self.assertRaises(ValueError):
                value = design()
                value["width_in"] = number
                validate_design(value)

    def test_missing_duplicate_and_unknown_blocks_are_rejected(self):
        for change in (lambda rows: rows.pop(), lambda rows: rows.__setitem__(0, copy.copy(rows[1])),
                       lambda rows: rows[0].update(id="unknown")):
            value = design()
            change(value["blocks"])
            with self.assertRaises(ValueError):
                validate_design(value)

    def test_overflow_and_overlap_are_rejected(self):
        for patch in ({"x": -1}, {"width": 5}, {"height": 7}, {"y": 0.5}, {"font_size": 0}):
            value = design()
            value["blocks"][0].update(patch)
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                validate_design(value)

    def test_geometry_roundtrip(self):
        value = design()
        self.assertEqual(validate_design(validate_design(value)), value)


if __name__ == "__main__":
    unittest.main()
