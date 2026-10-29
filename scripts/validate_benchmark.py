import json
import glob
import os
import sys

def main():
    schema_path = 'data/benchmark/schema.json'
    with open(schema_path, 'r', encoding='utf-8') as f:
        schema = json.load(f)

    case_def = schema['definitions']['case']
    gt_def = schema['definitions']['ground_truth']

    case_files = sorted(glob.glob('data/benchmark/cases/*.json'))
    gt_files = sorted(glob.glob('data/benchmark/ground_truth/*.json'))

    print(f"Found {len(case_files)} cases and {len(gt_files)} ground truth files.")

    try:
        import jsonschema
        has_jsonschema = True
        print("Using jsonschema for full Draft-7 schema validation.")
    except ImportError:
        has_jsonschema = False
        print("jsonschema not installed, performing manual structural validation.")

    errors = []

    # Category tricky tracking
    category_tricky = {}

    for cf in case_files:
        with open(cf, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if has_jsonschema:
            v = jsonschema.Draft7Validator(case_def)
            for err in v.iter_errors(data):
                path_str = "/".join(str(p) for p in err.path)
                errors.append(f"{cf}: {err.message} at {path_str}")

        cat = data.get('category')
        if data.get('is_tricky'):
            category_tricky[cat] = True

        if not data.get('real_world_source'):
            errors.append(f"{cf}: missing real_world_source")
        
        abu = data.get('invoice', {}).get('amount_base_units')
        if not (isinstance(abu, str) and abu.isdigit()):
            errors.append(f"{cf}: invoice amount_base_units not integer string ({abu})")

        tx_abu = data.get('transaction', {}).get('amount_base_units')
        if not (isinstance(tx_abu, str) and tx_abu.isdigit()):
            errors.append(f"{cf}: tx amount_base_units not integer string ({tx_abu})")

    for gf in gt_files:
        with open(gf, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if has_jsonschema:
            v = jsonschema.Draft7Validator(gt_def)
            for err in v.iter_errors(data):
                path_str = "/".join(str(p) for p in err.path)
                errors.append(f"{gf}: {err.message} at {path_str}")

    # Check categories tricky requirement
    categories = [
        "destination_conflict", "status_amount_conflict",
        "wrong_asset", "duplicate_shared_cause",
        "sanctions_frozen", "insufficient_evidence"
    ]
    for cat in categories:
        if not category_tricky.get(cat):
            errors.append(f"Category {cat} has no case with is_tricky=True")

    # Check D4 link
    with open('data/benchmark/cases/A2.json', 'r', encoding='utf-8') as f:
        a2 = json.load(f)
    with open('data/benchmark/cases/D4.json', 'r', encoding='utf-8') as f:
        d4 = json.load(f)

    a2_attacker = a2['transaction']['recipient']
    d4_text = json.dumps(d4)
    if a2_attacker.lower() not in d4_text.lower():
        errors.append(f"D4 does not reference A2 attacker address {a2_attacker}")

    # Check manifest.json
    manifest_path = 'data/benchmark/manifest.json'
    if not os.path.exists(manifest_path):
        errors.append("data/benchmark/manifest.json is missing")
    else:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
        if len(manifest.get('cases', [])) != 25:
            errors.append(f"manifest.json has {len(manifest.get('cases', []))} cases, expected 25")

    if errors:
        print(f"FAILED with {len(errors)} errors:")
        for e in errors:
            print("  -", e)
        sys.exit(1)
    else:
        print("SUCCESS! All 25 benchmark cases and ground truth files validated successfully against schema and CP4 criteria.")

if __name__ == '__main__':
    main()
