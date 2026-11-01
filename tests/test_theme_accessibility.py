from ui.theme import PALETTE


def _luminance(color):
    values = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in values]
    return sum(channel * weight for channel, weight in zip(linear, (0.2126, 0.7152, 0.0722)))


def test_body_and_secondary_text_meet_wcag_aa_contrast():
    background = _luminance(PALETTE['background'])
    for key in ('text', 'secondary'):
        foreground = _luminance(PALETTE[key])
        ratio = (max(foreground, background) + 0.05) / (min(foreground, background) + 0.05)
        assert ratio >= 4.5
