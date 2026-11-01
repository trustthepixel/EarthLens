import numpy as np

from tp.attacks import ALL_FAMILIES, make_attack


def test_each_attack_family_preserves_chip_contract_and_eventually_changes_pixels():
    base_rng = np.random.default_rng(987)
    chip = base_rng.integers(1000, 12000, size=(4, 256, 256), dtype=np.uint16)
    donor = np.roll(chip, 19, axis=2)

    for family in ALL_FAMILIES:
        masks = []
        for seed in range(3):
            output, mask, _ = make_attack(chip, donor, family, 'subtle', np.random.default_rng(seed), 1000)
            assert output.shape == (4, 256, 256)
            assert output.dtype == np.uint16
            assert mask.shape == (256, 256)
            masks.append(mask)
        assert any(mask.any() for mask in masks), f'{family} produced no mask for all tested seeds'
