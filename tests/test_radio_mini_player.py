from radio import mini_player


def test_gradient_fragments_cover_entire_row_with_multiple_theme_classes():
    fragments = mini_player._gradient_fragments("ABCDEFGH", steps=4)

    assert "".join(text for _, text in fragments) == "ABCDEFGH"
    assert [style for style, _ in fragments] == [
        "class:radio-bars-grad-0",
        "class:radio-bars-grad-1",
        "class:radio-bars-grad-2",
        "class:radio-bars-grad-3",
    ]


def test_braille_stack_returns_requested_number_of_rows():
    stack = mini_player._braille_bar_stack(1.0, rows=3)

    assert len(stack) == 3
    assert all(len(ch) == 1 for ch in stack)
    assert all(0x2800 <= ord(ch) <= 0x28FF for ch in stack)
