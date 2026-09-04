"""
Module 3: AIS & Intelligence - Live API Smoke Test
Launches the uvicorn server, executes live HTTP queries against /health and /api/attribute,
validates the live response, and shuts down the server cleanly.
"""

import os
import sys
import json
import time
import subprocess
import httpx

base_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.abspath(os.path.join(base_dir, ".."))

contract_b_path = os.path.join(repo_root, "contracts", "sample_drift_output.json")
ais_csv_path = os.path.join(base_dir, "data", "synthetic_ais.csv")

SERVER_URL = "http://127.0.0.1:8000"


def run_smoke_test():
    print("Starting uvicorn server process...")
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "module3_ais.api:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8000"
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = repo_root

    proc = subprocess.Popen(cmd, cwd=repo_root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    try:
        # Wait for server to become healthy (up to 15 seconds)
        print("Waiting for server to become responsive...")
        healthy = False
        health_data = {}
        for attempt in range(15):
            time.sleep(1)
            try:
                resp = httpx.get(f"{SERVER_URL}/health", timeout=2.0)
                if resp.status_code == 200:
                    health_data = resp.json()
                    healthy = True
                    break
            except Exception:
                pass

        if not healthy:
            stdout, stderr = proc.communicate(timeout=2)
            raise RuntimeError(f"Server failed to start. Stdout: {stdout.decode()} | Stderr: {stderr.decode()}")

        print(f"[PASS] GET /health responded 200 OK: {health_data}")
        assert health_data.get("status") == "ok", "Status is not ok"
        assert health_data.get("module") == "member3_ais", "Module name mismatch"
        assert health_data.get("version") == "0.3.0", "Version mismatch"

        # 2. Test POST /api/attribute
        print(f"Testing POST /api/attribute with sample files...")
        with open(contract_b_path, "r", encoding="utf-8") as f:
            contract_b_content = f.read()

        with open(ais_csv_path, "rb") as f:
            ais_file_bytes = f.read()

        files = {
            "ais_file": ("synthetic_ais.csv", ais_file_bytes, "text/csv")
        }
        data = {
            "contract_b": contract_b_content
        }

        resp = httpx.post(f"{SERVER_URL}/api/attribute", files=files, data=data, timeout=10.0)
        print(f"[PASS] POST /api/attribute response code: {resp.status_code}")
        assert resp.status_code == 200, f"Expected HTTP 200, got {resp.status_code}: {resp.text}"

        contract_c = resp.json()
        assert contract_c.get("status") == "COMPLETED"
        assert contract_c.get("slick_id") == "SLICK-AS-MUMBAI-20260904-001"
        suspects = contract_c.get("ranked_suspects", [])
        assert len(suspects) == 2, f"Expected 2 suspects, got {len(suspects)}"

        print(f"Top Suspect: MMSI {suspects[0]['mmsi']} | Threat: {suspects[0]['threat_level']} | Score: {suspects[0]['composite_threat_score']}")
        print(f"Second Suspect: MMSI {suspects[1]['mmsi']} | Threat: {suspects[1]['threat_level']} | Score: {suspects[1]['composite_threat_score']}")
        assert suspects[0]["composite_threat_score"] >= suspects[1]["composite_threat_score"], "Ranking not descending"

        print("API Smoke Test completed successfully!")

    finally:
        print("Shutting down uvicorn server process...")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        print("Server process terminated cleanly.")


if __name__ == "__main__":
    run_smoke_test()
