"""Shared utility for saving test results.

When the ``SLM_OUTPUT_FILE`` environment variable is set (e.g. set by the
backend or by ``run_all_tests.py``), results are merged into that single
master JSON file under ``test_sections[test_key]``.  Otherwise a standalone
``{prefix}_{model}_{timestamp}.json`` file is written to ``results/``.

In both cases the function prints ``Results saved to: <path>`` so the
backend's existing regex can still locate the file if needed.
"""
import json
import os
import time
from pathlib import Path

RESULTS_DIR = Path(__file__).parent.parent.parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def save_results(
    data: dict,
    prefix: str,
    model_name: str,
    test_key: str,
    subkey: str = "",
) -> str:
    """Save *data* for *test_key* either into the master file or individually.

    Parameters
    ----------
    data:       The results dict to save.
    prefix:     Filename prefix used when writing a standalone file
                (e.g. ``"quality"`` → ``quality_phi_1746….json``).
    model_name: Model name, used in the standalone filename.
    test_key:   Key under ``test_sections`` in the master file
                (should match the corresponding key in ``TESTS`` in main.py).
    subkey:     Optional second-level key inside ``test_sections[test_key]``.
                Used when one script produces two separate result dicts
                (e.g. ``stress_and_consistency_test.py``).
    """
    master_path = os.environ.get("SLM_OUTPUT_FILE", "").strip()
    if master_path:
        path = Path(master_path)
        existing: dict = {}
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    existing = json.load(fh)
            except Exception:
                existing = {}

        sections: dict = existing.setdefault("test_sections", {})
        if subkey:
            sections.setdefault(test_key, {})[subkey] = data
        else:
            sections[test_key] = data

        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(existing, fh, indent=2, ensure_ascii=False)

        print(f"Results saved to: {master_path}")
        return master_path

    safe = model_name.replace(":", "_").replace("/", "_")
    ram = os.environ.get("SLM_RAM_GB", "")
    cpu = os.environ.get("SLM_CPU_CORES", "")
    config = f"_{ram}GB_{cpu}c" if ram and cpu else (f"_{ram}GB" if ram else (f"_{cpu}c" if cpu else ""))
    output_file = RESULTS_DIR / f"{prefix}_{safe}{config}_{int(time.time())}.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    print(f"Results saved to: {output_file}")
    return str(output_file)
