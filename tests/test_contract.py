"""Tests for chip and STAC input validation."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import numpy as np
import pytest

from tp.contract import validate_chip, validate_stac_item


def valid_chip():
    rng = np.random.default_rng(12)
    return rng.integers(1000, 9000, size=(4, 256, 256), dtype=np.uint16)


def test_valid_chip_and_stac_item():
    result = validate_chip(valid_chip(), 1000, {'epsg': 32632, 'region': 'Tunis', 'baseline': '04.00'})
    assert result['ok'] and not result['errors']
    assert all(len(entry) == 3 for entry in result['checks'])
    assert validate_stac_item({'collection': 'sentinel-2-l2a', 'assets': {key: {} for key in ('B02', 'B03', 'B04', 'B08', 'SCL')}})['ok']


@pytest.mark.parametrize('pixels,offset,meta,error', [
    (np.zeros((4, 255, 256), dtype=np.uint16), 1000, None, 'shape'),
    (np.ones((4, 256, 256), dtype=np.float32), 1000, None, 'dtype'),
    (np.ones((4, 256, 256), dtype=np.uint16), 7, None, 'offset'),
    (np.zeros((4, 256, 256), dtype=np.uint16), 0, None, 'zero fraction'),
    (np.ones((4, 256, 256), dtype=np.uint16), 0, None, 'constant'),
    (np.full((4, 256, 256), 65535, dtype=np.uint16), 0, None, 'mean reflectance'),
    (np.full((4, 256, 256), 5000, dtype=np.uint16), 0, {'epsg': 4326}, 'epsg'),
])
def test_each_invalid_contract_case(pixels, offset, meta, error):
    result = validate_chip(pixels, offset, meta)
    assert not result['ok']
    assert any(error in entry.lower() for entry in result['errors'])


def test_domain_and_metadata_warnings_are_non_blocking():
    meta = {'epsg': 32632, 'region': 'Unknown', 'product': 'L1C'}
    result = validate_chip(valid_chip(), 0, meta)
    assert result['ok']
    assert 'outside training domain' in result['warnings']
    assert any('L1C' in warning for warning in result['warnings'])
    assert any('baseline' in warning for warning in result['warnings'])


def test_stac_item_reports_wrong_collection_and_missing_assets():
    result = validate_stac_item({'collection': 'other', 'assets': {}})
    assert not result['ok']
    assert len(result['errors']) == 2


def _notebook_reference_functions():
    notebook_path = Path('data_preparation.ipynb')
    if not notebook_path.is_file():
        pytest.skip('data preparation notebook is not available as a local reference.')
    notebook = json.loads(notebook_path.read_text(encoding='utf-8'))
    names = {'season_of', 'baseline_offset', 'aoi_window', 'classify_chip', 'chip_georef', 'sample_scene'}
    found = {}
    for cell in notebook['cells']:
        if cell.get('cell_type') != 'code':
            continue
        try:
            tree = ast.parse(''.join(cell.get('source', [])))
        except SyntaxError:  # Notebook shell magics are not Python source.
            continue
        found.update({node.name: node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names})
    return found


def _normalized(node):
    node = ast.fix_missing_locations(ast.parse(ast.unparse(node)).body[0])
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, (ast.Str, ast.Constant)) and isinstance(getattr(node.body[0].value, 'value', None), str):
        node.body.pop(0)
    return ast.dump(node, include_attributes=False)


def test_copied_helpers_match_data_preparation_notebook_ast():
    from tp import sentinel_live
    expected = _notebook_reference_functions()
    assert set(expected) == {'season_of', 'baseline_offset', 'aoi_window', 'classify_chip', 'chip_georef', 'sample_scene'}
    actual_tree = ast.parse(Path(sentinel_live.__file__).read_text(encoding='utf-8'))
    actual = {node.name: node for node in actual_tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    for name, reference in expected.items():
        assert _normalized(reference) == _normalized(actual[name]), name


@pytest.mark.network
def test_live_tunis_chip_validates_and_scores():
    from tp.onnx_analyzer import OnnxAnalyzer
    from tp.sentinel_live import NetworkUnavailable, latest_chip
    try:
        chip, meta, _ = latest_chip('Tunis')
    except NetworkUnavailable as exc:
        pytest.skip(f'Planetary Computer is unavailable: {exc}')
    if chip is None:
        pytest.skip('No recent clean Tunis chip is available.')
    result = validate_chip(chip, meta['offset'], meta)
    assert result['ok'], result['errors']
    assert np.isfinite(OnnxAnalyzer('model').analyze(chip, meta['offset'])['score'])
