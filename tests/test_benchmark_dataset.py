import json
import glob
import os
import jsonschema

def test_benchmark_schema_and_cases():
    schema_path = 'data/benchmark/schema.json'
    assert os.path.exists(schema_path), "data/benchmark/schema.json missing"
    with open(schema_path, 'r', encoding='utf-8') as f:
        schema = json.load(f)

    case_def = schema['definitions']['case']
    gt_def = schema['definitions']['ground_truth']

    case_files = sorted(glob.glob('data/benchmark/cases/*.json'))
    gt_files = sorted(glob.glob('data/benchmark/ground_truth/*.json'))

    assert len(case_files) == 25, f"Expected 25 case files, found {len(case_files)}"
    assert len(gt_files) == 25, f"Expected 25 ground truth files, found {len(gt_files)}"

    case_validator = jsonschema.Draft7Validator(case_def)
    gt_validator = jsonschema.Draft7Validator(gt_def)

    category_tricky = {}

    for cf in case_files:
        with open(cf, 'r', encoding='utf-8') as f:
            data = json.load(f)
        errors = list(case_validator.iter_errors(data))
        assert not errors, f"Validation errors in {cf}: {[e.message for e in errors]}"

        cat = data['category']
        if data.get('is_tricky'):
            category_tricky[cat] = True

        assert data.get('real_world_source'), f"{cf} missing real_world_source"
        assert data['invoice']['amount_base_units'].isdigit(), f"{cf} invoice amount_base_units not integer string"
        assert data['transaction']['amount_base_units'].isdigit(), f"{cf} tx amount_base_units not integer string"

    for gf in gt_files:
        with open(gf, 'r', encoding='utf-8') as f:
            data = json.load(f)
        errors = list(gt_validator.iter_errors(data))
        assert not errors, f"Validation errors in {gf}: {[e.message for e in errors]}"

    required_categories = [
        "destination_conflict", "status_amount_conflict",
        "wrong_asset", "duplicate_shared_cause",
        "sanctions_frozen", "insufficient_evidence"
    ]
    for cat in required_categories:
        assert category_tricky.get(cat), f"Category {cat} has no tricky cases"

    # Verify D4 references A2 attacker address
    with open('data/benchmark/cases/A2.json', 'r', encoding='utf-8') as f:
        a2 = json.load(f)
    with open('data/benchmark/cases/D4.json', 'r', encoding='utf-8') as f:
        d4 = json.load(f)
    a2_attacker = a2['transaction']['recipient']
    assert a2_attacker.lower() in json.dumps(d4).lower(), f"D4 does not link to A2 attacker {a2_attacker}"
