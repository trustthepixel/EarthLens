import ast
import copy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / 'legacy' / 'tp_lib.py'
ATTACK_FUNCTIONS = {
    'feather', 'to_u16', 'shape_mask', 'place', 'random_mask', 'noise_sigma', 'detectability',
    'copy_move', 'splice', 'class_swap', '_affine_region', '_rotate', 'rotate_region', 'rotate_big',
    'scale_region', 'spectral_edit', 'photometric_region', 'noise_region', 'blur_region', 'jpeg_region',
    'object_insert', '_inpaint', 'inpaint_telea', 'inpaint_ns', 'cloud_region', 'resample_region',
    'band_shift', 'compound', '_single_attack', 'make_attack', 'benign',
}
ATTACK_ASSIGNMENTS = {
    'BANDS', 'CHIP', 'DEFAULT_OFFSET', 'SEVERITY', 'SEV_ALL', '_LAP', 'FAMILIES', 'TRAIN_FAMILIES',
    'HELDOUT_FAMILIES', 'ALL_FAMILIES', 'COMPOUND_POOL', 'COMPOUND_MIXED_POOL', 'EVAL_FAMILIES',
}
PROVENANCE_FUNCTIONS = {
    'canonical', 'pixel_bytes', 'sha256_hex', 'tile_hashes', 'merkle_root_hex', 'public_key_id',
    '_now_iso', 'channel_attack', 'decide',
}
PROVENANCE_CLASSES = {'Source', 'Ground', 'AuditLog'}
PROVENANCE_ASSIGNMENTS = {'TILE', 'CHANNEL_ATTACKS'}


def _names(node):
    if not isinstance(node, ast.Assign):
        return set()
    return {child.id for target in node.targets for child in ast.walk(target) if isinstance(child, ast.Name)}


def _without_docstrings(node):
    node = copy.deepcopy(node)
    for child in ast.walk(node):
        body = getattr(child, 'body', None)
        if isinstance(child, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
            del body[0]
    return ast.dump(node, include_attributes=False)


def _indexed(module):
    indexed = {}
    for node in module.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            indexed[node.name] = node
        elif isinstance(node, ast.Assign):
            for name in _names(node):
                indexed[name] = node
    return indexed


def test_split_definitions_match_legacy_ast():
    legacy = _indexed(ast.parse(LEGACY.read_text(encoding='utf-8')))
    expected = {
        'tp/attacks.py': ATTACK_FUNCTIONS | ATTACK_ASSIGNMENTS,
        'tp/provenance.py': PROVENANCE_FUNCTIONS | PROVENANCE_CLASSES | PROVENANCE_ASSIGNMENTS,
        'tp/data_io.py': {'export_geotiff'},
    }
    for relative_path, names in expected.items():
        current = _indexed(ast.parse((ROOT / relative_path).read_text(encoding='utf-8-sig')))
        for name in names:
            assert name in legacy, f'{name} is missing from the legacy source'
            assert name in current, f'{name} is missing from {relative_path}'
            assert _without_docstrings(current[name]) == _without_docstrings(legacy[name]), (
                f'{relative_path}:{name} differs from the legacy AST'
            )



