import json
import os

def load(file):
    try:
        with open(file) as f:
            return json.load(f)
    except:
        return {}

report = {
    "deployment": {
        "commit_sha": os.getenv("COMMIT_SHA"),
        "branch": os.getenv("BRANCH"),
        "github_run_id": os.getenv("RUN_ID")
    },

    "scans": [
        {"tool": "SEMGREP", "report": load("semgrep.json")},
        {"tool": "TRIVY_FS", "report": load("trivy-fs.json")},
        {"tool": "TRIVY_IMAGE", "report": load("trivy-image.json")},
        {"tool": "GITLEAKS", "report": load("gitleaks.json")},
        {"tool": "ZAP", "report": load("zap.json")}
    ]
}

with open("security-report.json", "w") as f:
    json.dump(report, f, indent=2)

print("report generated")
