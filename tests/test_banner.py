
import os
from unittest.mock import patch
from gemini_manager.banner import print_logo, blend, lerp

def test_lerp():
    assert lerp(0, 10, 0.5) == 5
    assert lerp(-10, 10, 0.5) == 0
    assert lerp(10, 20, 0) == 10
    assert lerp(10, 20, 1) == 20

def test_blend():
    c1 = (0, 0, 0)
    c2 = (255, 255, 255)
    assert blend(c1, c2, 0) == "#000000"
    # The blend function uses a wave shaping formula that does not produce a pure white color
    assert blend(c1, c2, 1) == "#cfcfcf"
    # Just check if it returns a valid color format for an intermediate value
    assert blend(c1, c2, 0.5).startswith("#")

@patch("rich.console.Console.print")
def test_print_logo_procedural(mock_print):
    print_logo()
    mock_print.assert_called()

@patch("rich.console.Console.print")
def test_print_logo_fixed_palette(mock_print):
    with patch.dict(os.environ, {"CREATE_DUMP_PALETTE": "0"}):
        print_logo()
        mock_print.assert_called()

@patch("rich.console.Console.print")
def test_print_logo_fixed_palette_invalid_index(mock_print):
    with patch.dict(os.environ, {"CREATE_DUMP_PALETTE": "999"}):
        # Should fall back to procedural
        print_logo()
        mock_print.assert_called()

@patch("rich.console.Console.print")
def test_print_logo_fixed_palette_invalid_value(mock_print):
    with patch.dict(os.environ, {"CREATE_DUMP_PALETTE": "invalid"}):
        # Should fall back to procedural
        print_logo()
        mock_print.assert_called()
