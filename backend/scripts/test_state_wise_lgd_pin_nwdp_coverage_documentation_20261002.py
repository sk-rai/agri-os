#!/usr/bin/env python3
"""Static documentation contract for LGD/PIN/NWDP coverage."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOC = (
    ROOT / "docs/state-wise-lgd-pin-nwdp-coverage-2026-10-02.md"
).read_text(encoding="utf-8")


CHECKS = {
    "Corrected schema is recorded":
        "state_wise_lgd_pin_nwdp_coverage.v2",
    "V1 is superseded":
        "v1 artifact is diagnostic and superseded",
    "Canonical total is pinned": "600,647",
    "PIN-covered total is pinned": "560,151",
    "PIN gap is pinned": "40,496",
    "Effective NWDP total is pinned": "487,999",
    "Effective NWDP gap is pinned": "112,648",
    "Runtime total is pinned": "467,397",
    "Post-LGD lineage is pinned": "17,498",
    "Fully resolved class is documented":
        "`FULLY_RESOLVED` | Present | Present | 454,996",
    "PIN-only class is documented":
        "`PIN_ONLY` | Present | Missing | 105,155",
    "NWDP-only class is documented":
        "`NWDP_ONLY` | Missing | Present | 33,003",
    "Unresolved class is documented":
        "`UNRESOLVED` | Missing | Missing | 7,493",
    "Candidate mapping remains distinct":
        "Candidate NWDP mapping means",
    "Runtime mapping remains distinct":
        "Active runtime NWDP mapping means",
    "Effective mapping is a union":
        "Effective NWDP mapping is the union",
    "Village admin gap is explicit":
        "Neither currently exposes a canonical village-level combined",
    "Pagination is required": "Results must be paginated",
    "Canonical writes are excluded":
        "alter canonical LGD geography",
    "PIN writes are excluded":
        "add, remove, or modify PIN links",
    "Candidate promotion is excluded":
        "activate or promote NWDP candidates",
    "Runtime writes are excluded":
        "modify runtime features or crosswalks",
    "Android changes are excluded":
        "change Android behavior",
}


def main() -> int:
    for label, needle in CHECKS.items():
        if needle not in DOC:
            raise AssertionError(f"{label}: missing {needle!r}")
        print(f"PASS {label}")

    print(
        "STATE-WISE LGD PIN NWDP COVERAGE "
        "DOCUMENTATION CONTRACT PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
