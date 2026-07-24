"""Regression for pure backend DigiPin utility."""

import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.modules.master_data.digipin import (
    ALGORITHM_VERSION,
    decode_digipin,
    encode_digipin,
    generate_location_digipin,
    is_within_digipin_bounds,
    normalize_digipin,
    validate_digipin,
)


def check(condition, label, detail=None):
    print(f"  {'PASS' if condition else 'FAIL'} {label}")
    if detail is not None:
        print(f"       {detail}")
    if not condition:
        raise AssertionError(label)


def main():
    print("=" * 72)
    print("DIGIPIN UTILITY REGRESSION")
    print("=" * 72)

    official_example = encode_digipin(13.11179621, 80.20264269)
    check(official_example == "4T396F42L7", "Official India Post example encodes", official_example)

    chennai = decode_digipin("4T396F42L7")
    check(encode_digipin(chennai.latitude, chennai.longitude) == "4T396F42L7", "Decoded center re-encodes to same DigiPin", chennai)
    check(abs(chennai.latitude - Decimal("13.11179621")) < Decimal("0.0001"), "Decoded latitude center is close to source coordinate", chennai)
    check(abs(chennai.longitude - Decimal("80.20264269")) < Decimal("0.0001"), "Decoded longitude center is close to source coordinate", chennai)

    bengaluru = encode_digipin(12.971601, 77.594584)
    check(len(bengaluru) == 10, "Encoded DigiPin is 10 characters", bengaluru)
    check(validate_digipin(bengaluru), "Encoded DigiPin validates")

    normalized = normalize_digipin(" 4T3 96F 42L7 ")
    check(normalized == "4T396F42L7", "Display spaces can be normalized")

    generated = generate_location_digipin(28.6139, 77.2090)
    check(generated["algorithm_version"] == ALGORITHM_VERSION, "Generated payload includes algorithm version")
    check(validate_digipin(generated["digipin"]), "Generated payload DigiPin validates")

    check(is_within_digipin_bounds(28.6139, 77.2090), "Delhi coordinate inside DigiPin bounds")
    check(not is_within_digipin_bounds(40.0, 77.2090), "Out-of-bounds latitude rejected by bounds check")

    failed = False
    try:
        encode_digipin(40.0, 77.2090)
    except ValueError:
        failed = True
    check(failed, "Encoding rejects out-of-bounds coordinates")

    failed = False
    try:
        normalize_digipin("4T3-96F-42L7")
    except ValueError:
        failed = True
    check(failed, "Hyphenated DigiPin rejected for API/database storage")

    print("=" * 72)
    print("DigiPin utility validated")
    print("=" * 72)


if __name__ == "__main__":
    main()
