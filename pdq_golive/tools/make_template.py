"""Part 12: create (or update) the RunPod template "PDQ testing to go live", then read it back.

    python pdq_golive/tools/make_template.py --image ghcr.io/nadaaa72/pdq-golive:<sha> \
        --registry-auth <RunPod registry credential id>

The RunPod key is read from credentials.env and never printed. The B2 key is NOT put in the
template: the template refers to the RunPod secrets b2_key_id and b2_app_key, which already
exist in the account, so the value never leaves RunPod. Bucket and endpoint are names, not
keys, and are copied from credentials.env without being printed.

The read-back lists every environment variable name and fails if any name or value looks
like a production key other than the two secret references."""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NAME = "PDQ testing to go live"
ALLOWED = {"B2_KEY_ID", "B2_APP_KEY", "B2_BUCKET", "B2_ENDPOINT", "GOLIVE_MAX_MIN",
           "PDQ_IVF_NPROBE", "OMP_NUM_THREADS", "PUBLIC_KEY"}


def cred(name: str) -> str:
    for line in open(ROOT / "credentials.env", encoding="utf-8"):
        m = re.match(r"\s*%s\s*=\s*(.+)" % re.escape(name), line)
        if m:
            return m.group(1).strip().strip("\"'")
    raise SystemExit("credentials.env has no %s" % name)


def gql(key: str, query: str, variables: dict | None = None) -> dict:
    req = urllib.request.Request(
        "https://api.runpod.io/graphql",
        data=json.dumps({"query": query, "variables": variables or {}}).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key,
                 "User-Agent": "pdq-golive"})
    r = json.load(urllib.request.urlopen(req, timeout=60))
    if r.get("errors"):
        raise SystemExit("RunPod API error: %s" % json.dumps(r["errors"])[:500])
    return r["data"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--registry-auth", default="")
    ap.add_argument("--disk-gb", type=int, default=300)
    ap.add_argument("--max-min", type=int, default=170)
    a = ap.parse_args()
    key = cred("RUNPOD_API_KEY")
    endpoint = ""
    for n in ("B2_ENDPOINT", "B2_S3_ENDPOINT"):
        try:
            endpoint = cred(n)
            break
        except SystemExit:
            pass
    env = [
        {"key": "B2_KEY_ID", "value": "{{ RUNPOD_SECRET_b2_key_id }}"},
        {"key": "B2_APP_KEY", "value": "{{ RUNPOD_SECRET_b2_app_key }}"},
        {"key": "B2_BUCKET", "value": cred("B2_BUCKET")},
        {"key": "B2_ENDPOINT", "value": endpoint if endpoint.startswith("http") else "https://" + endpoint},
        {"key": "GOLIVE_MAX_MIN", "value": str(a.max_min)},
        {"key": "PDQ_IVF_NPROBE", "value": "16"},
        {"key": "OMP_NUM_THREADS", "value": "16"},
    ]
    # The account's public SSH key, so boot.sh can let us in without editing the pod after it
    # starts (run 1 had to, which restarts the container). A public key is not a secret.
    pub = gql(key, "query { myself { pubKey } }")["myself"]["pubKey"] or ""
    if pub.strip():
        env.append({"key": "PUBLIC_KEY", "value": pub.strip()})
    existing = [t for t in gql(key, "query { myself { podTemplates { id name } } }")["myself"]["podTemplates"]
                if t["name"] == NAME]
    inp = {"name": NAME, "imageName": a.image, "containerDiskInGb": a.disk_gb, "volumeInGb": 0,
           "volumeMountPath": "/workspace", "ports": "22/tcp", "env": env, "isServerless": False,
           "dockerArgs": "", "startSsh": False,
           "readme": "PDQ alone, read-only, on the live index. Not for users. See pdq_golive/ in "
                     "Nadaaa72/pdq-testing. Hard stop after GOLIVE_MAX_MIN minutes."}
    if a.registry_auth:
        inp["containerRegistryAuthId"] = a.registry_auth
    if existing:
        inp["id"] = existing[0]["id"]
    t = gql(key, "mutation($input: SaveTemplateInput!) { saveTemplate(input: $input) { id name } }",
            {"input": inp})["saveTemplate"]
    print("template", t["id"], t["name"])

    # read back
    back = [x for x in gql(key, "query { myself { podTemplates { id name imageName containerDiskInGb "
                                "volumeInGb ports containerRegistryAuthId env { key value } } } }")
            ["myself"]["podTemplates"] if x["id"] == t["id"]][0]
    names = sorted(e["key"] for e in back["env"])
    bad = [n for n in names if n not in ALLOWED]
    secret_ok = all(e["value"].startswith("{{ RUNPOD_SECRET_") for e in back["env"]
                    if e["key"] in ("B2_KEY_ID", "B2_APP_KEY"))
    leaked = [e["key"] for e in back["env"] if re.search(r"postgres://|BEGIN PRIVATE|sk-[A-Za-z0-9]{20}", e["value"])]
    print(json.dumps({"id": back["id"], "image": back["imageName"], "disk_gb": back["containerDiskInGb"],
                      "volume_gb": back["volumeInGb"], "ports": back["ports"],
                      "registry_auth": bool(back.get("containerRegistryAuthId")),
                      "env_names": names, "unexpected_env": bad,
                      "b2_values_are_secret_refs": secret_ok, "suspicious_values": leaked}, indent=1))
    return 1 if (bad or not secret_ok or leaked) else 0


if __name__ == "__main__":
    sys.exit(main())
