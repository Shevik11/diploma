"""E2E tests — run against your live Ollama server.

Start Ollama (or docker-compose up) first, then:

    cd scripts/tests
    pytest test_e2e_results.py -v

Configuration (optional env vars):
    OLLAMA_HOST   host where Ollama is running   (default: localhost)
    OLLAMA_PORT   Ollama API port                (default: 11434)
    TEST_MODEL    model name to use              (auto-detected if not set)

The unit tests (TestResultUtils) never need the server and always run.
The live tests (TestScriptConsolidation, TestRunAllTests) are skipped
automatically when Ollama is not reachable.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
TESTS_DIR = Path(__file__).parent
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "localhost")
OLLAMA_PORT = int(os.environ.get("OLLAMA_PORT", "11434"))
OLLAMA_BASE = f"http://{OLLAMA_HOST}:{OLLAMA_PORT}"

# Backend (FastAPI) and frontend (web UI) endpoints — exposed by
# ``docker-compose.yml`` on host ports 8000 and 3000 respectively. We assert
# their availability in the session fixture so an incomplete stack is caught
# up front instead of producing confusing per-test failures later.
BACKEND_HOST = os.environ.get("BACKEND_HOST", "localhost")
BACKEND_PORT = int(os.environ.get("BACKEND_PORT", "8000"))
BACKEND_BASE = f"http://{BACKEND_HOST}:{BACKEND_PORT}"
FRONTEND_HOST = os.environ.get("FRONTEND_HOST", "localhost")
FRONTEND_PORT = int(os.environ.get("FRONTEND_PORT", "3000"))
FRONTEND_BASE = f"http://{FRONTEND_HOST}:{FRONTEND_PORT}"


# ---------------------------------------------------------------------------
# Session-scoped fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def ollama_check():
    """Fail fast with a clear skip message if any required service is down.

    Previously this only verified that Ollama was reachable. Per the
    project's test contract the full stack also needs:

      * the FastAPI backend responding ``200`` on ``/api/status``
      * the frontend SPA reachable on port ``3000``

    Without these assertions the live tests can spuriously pass while the
    UI/backend half of the stack is broken — or they fail deep inside a
    test with an opaque ``ConnectionError``. We surface both conditions
    here with explicit ``pytest.skip`` messages.
    """
    # 1) Ollama — original check, kept first because most live tests
    #    talk directly to the model server.
    try:
        requests.get(f"{OLLAMA_BASE}/api/tags", timeout=5)
    except Exception:
        pytest.skip(
            f"Ollama not reachable at {OLLAMA_BASE}. "
            "Start the server first (e.g. `docker-compose up` or `ollama serve`)."
        )

    # 2) Backend FastAPI — ``/api/status`` must return HTTP 200. We treat
    #    any non-200 (or transport error) as "stack not ready".
    try:
        backend_resp = requests.get(f"{BACKEND_BASE}/api/status", timeout=5)
    except Exception as e:
        pytest.skip(
            f"Backend not reachable at {BACKEND_BASE}/api/status ({e!r}). "
            "Start it with `docker-compose up backend` or `uvicorn main:app --port 8000`."
        )
    if backend_resp.status_code != 200:
        pytest.skip(
            f"Backend /api/status returned HTTP {backend_resp.status_code} "
            f"(expected 200). Body: {backend_resp.text[:200]!r}"
        )

    # 3) Frontend — any 2xx/3xx response on port 3000 proves the SPA is
    #    being served (some dev servers redirect ``/`` -> ``/index.html``,
    #    and the production nginx image returns 200 directly).
    try:
        fe_resp = requests.get(f"{FRONTEND_BASE}/", timeout=5, allow_redirects=False)
    except Exception as e:
        pytest.skip(
            f"Frontend not reachable at {FRONTEND_BASE} ({e!r}). "
            "Start it with `docker-compose up frontend` or `npm run dev` in `frontend/`."
        )
    if fe_resp.status_code >= 400:
        pytest.skip(
            f"Frontend at {FRONTEND_BASE} returned HTTP {fe_resp.status_code} "
            "(expected a 2xx/3xx response from the SPA root)."
        )


@pytest.fixture(scope="session")
def live_model(ollama_check):
    """Return the model to use for tests.

    Honours the TEST_MODEL env var; otherwise picks the first model that
    Ollama already has pulled.  Skips the session if no model is available.
    """
    explicit = os.environ.get("TEST_MODEL", "").strip()
    if explicit:
        return explicit

    try:
        resp = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=5)
        models = [m["name"] for m in resp.json().get("models", [])]
    except Exception:
        models = []

    if not models:
        pytest.skip(
            "No models found in Ollama. Pull one first, e.g.:\n"
            "  ollama pull phi3:mini\n"
            "or set TEST_MODEL=<name> before running pytest."
        )

    print(f"\n[test_e2e_results] Using model: {models[0]}")
    return models[0]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _run_script(script_name, model, port, master_file, extra_args=None, timeout=300):
    """Run a test script as a subprocess with SLM_OUTPUT_FILE pointing at master_file."""
    cmd = [sys.executable, str(TESTS_DIR / script_name), model, str(port)]
    if extra_args:
        cmd.extend(extra_args)
    env = os.environ.copy()
    env["SLM_OUTPUT_FILE"] = str(master_file)
    env["SLM_TEST_HOST"] = OLLAMA_HOST
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(TESTS_DIR),
        env=env,
    )


# ---------------------------------------------------------------------------
# Unit tests — result_utils (no server needed, always run)
# ---------------------------------------------------------------------------

class TestResultUtils:
    """Pure unit tests for save_results(); no network required."""

    def test_standalone_creates_individual_file(self, monkeypatch):
        """Without SLM_OUTPUT_FILE an individual timestamped file is created."""
        monkeypatch.delenv("SLM_OUTPUT_FILE", raising=False)
        import result_utils

        saved_path = None
        try:
            path_str = result_utils.save_results(
                {"model": "phi", "score": 42}, "quality", "phi:3.5", "quality"
            )
            saved_path = Path(path_str)
            assert saved_path.exists(), "Individual result file was not created"
            content = json.loads(saved_path.read_text())
            assert content["score"] == 42
            assert "quality" in saved_path.name
        finally:
            if saved_path and saved_path.exists():
                saved_path.unlink()

    def test_master_mode_writes_to_env_file(self, tmp_path, monkeypatch):
        """With SLM_OUTPUT_FILE set, results go into test_sections[key]."""
        master = tmp_path / "master.json"
        monkeypatch.setenv("SLM_OUTPUT_FILE", str(master))
        import result_utils

        result_utils.save_results({"model": "phi", "score": 99}, "quality", "phi:3.5", "quality")

        assert master.exists()
        content = json.loads(master.read_text())
        assert content["test_sections"]["quality"]["score"] == 99

    def test_master_mode_accumulates_multiple_calls(self, tmp_path, monkeypatch):
        """Three separate save_results calls all end up in one file."""
        master = tmp_path / "master.json"
        monkeypatch.setenv("SLM_OUTPUT_FILE", str(master))
        import result_utils

        result_utils.save_results({"result": "a"}, "quality", "phi", "quality")
        result_utils.save_results({"result": "b"}, "performance", "phi", "performance")
        result_utils.save_results({"result": "c"}, "multilingual", "phi", "multilingual")

        content = json.loads(master.read_text())
        sections = content["test_sections"]
        assert sections["quality"]["result"] == "a"
        assert sections["performance"]["result"] == "b"
        assert sections["multilingual"]["result"] == "c"

    def test_subkey_accumulates_without_overwriting(self, tmp_path, monkeypatch):
        """Stress/consistency subkeys coexist under stress_consistency."""
        master = tmp_path / "master.json"
        monkeypatch.setenv("SLM_OUTPUT_FILE", str(master))
        import result_utils

        result_utils.save_results(
            {"type": "consistency", "rate": 0.9}, "consistency", "phi",
            "stress_consistency", subkey="consistency",
        )
        result_utils.save_results(
            {"type": "stress", "rate": 0.8}, "stress", "phi",
            "stress_consistency", subkey="stress",
        )

        content = json.loads(master.read_text())
        sc = content["test_sections"]["stress_consistency"]
        assert sc["consistency"]["type"] == "consistency"
        assert sc["stress"]["type"] == "stress"

    def test_existing_master_fields_are_preserved(self, tmp_path, monkeypatch):
        """Pre-existing benchmark summary fields survive a merge."""
        master = tmp_path / "master.json"
        master.write_text(json.dumps({
            "model": "phi", "platform": "docker",
            "summary": {"avg_tokens_per_second": 45.0},
            "test_sections": {},
        }))
        monkeypatch.setenv("SLM_OUTPUT_FILE", str(master))
        import result_utils

        result_utils.save_results({"score": 77}, "quality", "phi", "quality")

        content = json.loads(master.read_text())
        assert content["model"] == "phi"
        assert content["platform"] == "docker"
        assert content["summary"]["avg_tokens_per_second"] == 45.0
        assert content["test_sections"]["quality"]["score"] == 77

    def test_stdout_always_contains_results_saved_to(self, tmp_path, monkeypatch, capsys):
        """Backend regex requires 'Results saved to:' in stdout in both modes."""
        master = tmp_path / "master.json"
        monkeypatch.setenv("SLM_OUTPUT_FILE", str(master))
        import result_utils

        result_utils.save_results({"x": 1}, "quality", "phi", "quality")
        captured = capsys.readouterr()
        assert "Results saved to:" in captured.out


# ---------------------------------------------------------------------------
# Live E2E tests — individual scripts against the real Ollama server
# ---------------------------------------------------------------------------

class TestScriptConsolidation:
    """Run real test scripts against the live Ollama server."""

    def test_quality_script_writes_to_master(self, tmp_path, live_model):
        master = tmp_path / "run.json"
        proc = _run_script("quality_test.py", live_model, OLLAMA_PORT, master)

        assert master.exists(), (
            f"Master file not created.\n"
            f"stdout: {proc.stdout[-600:]}\nstderr: {proc.stderr[-400:]}"
        )
        content = json.loads(master.read_text())
        assert "quality" in content.get("test_sections", {}), (
            f"'quality' key missing from test_sections.\n"
            f"Keys: {list(content.get('test_sections', {}).keys())}\n"
            f"stdout: {proc.stdout[-400:]}"
        )
        quality = content["test_sections"]["quality"]
        assert quality["model"] == live_model
        assert isinstance(quality.get("tests"), list)
        assert len(quality["tests"]) > 0, "quality section has no test entries"

    def test_performance_script_writes_to_master(self, tmp_path, live_model):
        master = tmp_path / "run.json"
        # Pass num_tests=1 so the test runs quickly
        proc = _run_script("performance_test.py", live_model, OLLAMA_PORT, master, ["1"])

        assert master.exists(), (
            f"Master file not created.\n"
            f"stdout: {proc.stdout[-600:]}\nstderr: {proc.stderr[-400:]}"
        )
        content = json.loads(master.read_text())
        assert "performance" in content.get("test_sections", {}), (
            f"'performance' key missing.\nstdout: {proc.stdout[-400:]}"
        )
        perf = content["test_sections"]["performance"]
        assert perf["model"] == live_model
        assert isinstance(perf.get("tests"), list)

    def test_multiple_scripts_share_one_file(self, tmp_path, live_model):
        """quality + performance run sequentially → exactly one JSON file."""
        master = tmp_path / "shared.json"

        _run_script("quality_test.py", live_model, OLLAMA_PORT, master)
        _run_script("performance_test.py", live_model, OLLAMA_PORT, master, ["1"])

        content = json.loads(master.read_text())
        sections = content.get("test_sections", {})
        assert "quality" in sections, "quality section missing"
        assert "performance" in sections, "performance section missing"

        json_files = list(tmp_path.glob("*.json"))
        assert len(json_files) == 1, (
            f"Expected exactly 1 JSON file, found {len(json_files)}: "
            f"{[f.name for f in json_files]}"
        )

    def test_stdout_contains_results_saved_to(self, tmp_path, live_model):
        """Backend regex relies on 'Results saved to:' appearing in stdout."""
        master = tmp_path / "run.json"
        proc = _run_script("quality_test.py", live_model, OLLAMA_PORT, master)
        assert "Results saved to:" in proc.stdout, (
            f"'Results saved to:' not in stdout.\nstdout: {proc.stdout[-500:]}"
        )

    def test_multilingual_script_writes_to_master(self, tmp_path, live_model):
        master = tmp_path / "run.json"
        proc = _run_script("multilingual_test.py", live_model, OLLAMA_PORT, master)

        assert master.exists(), f"Master file not created.\nstderr: {proc.stderr[-400:]}"
        content = json.loads(master.read_text())
        assert "multilingual" in content.get("test_sections", {}), (
            f"'multilingual' key missing.\nstdout: {proc.stdout[-400:]}"
        )

    def test_stress_consistency_uses_subkeys(self, tmp_path, live_model):
        """stress_and_consistency_test.py must populate consistency and/or stress subkeys."""
        master = tmp_path / "run.json"
        _run_script("stress_and_consistency_test.py", live_model, OLLAMA_PORT, master)

        content = json.loads(master.read_text())
        sc = content.get("test_sections", {}).get("stress_consistency", {})
        assert sc, (
            "stress_consistency section is missing or empty in master file. "
            f"test_sections keys: {list(content.get('test_sections', {}).keys())}"
        )
        assert "consistency" in sc or "stress" in sc, (
            f"Expected 'consistency' or 'stress' subkeys, got: {list(sc.keys())}"
        )


# ---------------------------------------------------------------------------
# Live E2E test — full run_all_tests.py (slow, opt-in)
# ---------------------------------------------------------------------------

class TestRunAllTests:
    """Full pipeline test.  Runs all 16 test scripts — takes several minutes.

    Skipped unless --run-slow is passed:
        pytest test_e2e_results.py -v -m slow --run-slow
    """

    @pytest.mark.slow
    def test_produces_single_master_file(self, live_model):
        env = os.environ.copy()
        env["SLM_TEST_HOST"] = OLLAMA_HOST

        proc = subprocess.run(
            [sys.executable, str(TESTS_DIR / "run_all_tests.py"), live_model, str(OLLAMA_PORT)],
            capture_output=True,
            text=True,
            timeout=600,
            cwd=str(TESTS_DIR),
            env=env,
        )

        # Locate master file from stdout
        master_path = None
        for line in proc.stdout.splitlines():
            if line.startswith("Master results file:"):
                master_path = Path(line.split(":", 1)[1].strip())
                break

        assert master_path is not None, (
            f"Could not find 'Master results file:' in stdout.\n"
            f"stdout (first 2000):\n{proc.stdout[:2000]}"
        )
        assert master_path.exists(), f"Master file {master_path} does not exist"

        content = json.loads(master_path.read_text())
        assert "test_sections" in content, "master file missing 'test_sections'"
        assert "run_summary" in content, "master file missing 'run_summary'"
        assert content["model"] == live_model
        assert len(content["test_sections"]) > 0, "test_sections is empty"

        # Cleanup
        master_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# pytest hooks for the --run-slow gate live in conftest.py (they are not
# picked up by pytest when defined inside a test module).
# ---------------------------------------------------------------------------
