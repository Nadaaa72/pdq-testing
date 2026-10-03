# -*- coding: utf-8 -*-
"""
b2_access.py - the small door to our online storage (Backblaze B2), read-only.

The fingerprints of every film live in a B2 bucket. Scripts 1 and 2 read them from there.
This file holds the three things they need: read the key from credentials.env, open a
connection, list and fetch files. Nothing here can write or delete. The key Jude gives
you is read-only too, so even a bug cannot damage anything.

B2 speaks the same language as Amazon S3, so the boto3 package is used.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator, Tuple

HERE = Path(__file__).resolve().parent
CREDENTIALS_FILE = HERE / "credentials.env"

# the folder in the bucket where every film's fingerprint file lives: movie_<id>.blob
DEFAULT_BLOB_PREFIX = "NEVER_DELETE_movie_hash_source_of_truth/pdq/"
# the folder where the pod's index pieces live; each piece has a manifest.json naming its films
DEFAULT_SHARDS_PREFIX = "pdq_cache_flat_v2/shards/"


def load_credentials() -> dict:
    """Read credentials.env into a dict. Stops with a clear message if the file is missing."""
    if not CREDENTIALS_FILE.is_file():
        raise SystemExit(
            f"credentials.env not found at {CREDENTIALS_FILE}\n"
            "Copy credentials.env.example to credentials.env and paste in the key Jude gave you."
        )
    from dotenv import dotenv_values
    cfg = {k: (v or "").strip() for k, v in dotenv_values(str(CREDENTIALS_FILE)).items()}
    # the pod's own .env can be dropped in as credentials.env unchanged: it names two things differently
    if not cfg.get("B2_ENDPOINT") and cfg.get("B2_S3_ENDPOINT"):
        cfg["B2_ENDPOINT"] = cfg["B2_S3_ENDPOINT"]
    if not cfg.get("DATABASE_URL_READONLY") and cfg.get("DATABASE_URL"):
        cfg["DATABASE_URL_READONLY"] = cfg["DATABASE_URL"]
    for need in ("B2_KEY_ID", "B2_APP_KEY", "B2_BUCKET", "B2_ENDPOINT"):
        if not cfg.get(need):
            raise SystemExit(f"credentials.env is missing {need}")
    cfg.setdefault("B2_PDQ_BLOB_PREFIX", DEFAULT_BLOB_PREFIX)
    cfg.setdefault("B2_SHARDS_PREFIX", DEFAULT_SHARDS_PREFIX)
    if not cfg["B2_PDQ_BLOB_PREFIX"]:
        cfg["B2_PDQ_BLOB_PREFIX"] = DEFAULT_BLOB_PREFIX
    if not cfg["B2_SHARDS_PREFIX"]:
        cfg["B2_SHARDS_PREFIX"] = DEFAULT_SHARDS_PREFIX
    return cfg


class B2:
    """A read-only connection to the bucket."""

    def __init__(self, cfg: dict | None = None):
        import boto3
        from botocore.config import Config
        cfg = cfg or load_credentials()
        self.cfg = cfg
        self.bucket = cfg["B2_BUCKET"]
        endpoint = cfg["B2_ENDPOINT"].rstrip("/")
        # the region is written inside the endpoint: s3.eu-central-003.backblazeb2.com
        region = endpoint.split("//")[-1].split(".")[1] if ".backblazeb2.com" in endpoint else "us-east-1"
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=cfg["B2_KEY_ID"],
            aws_secret_access_key=cfg["B2_APP_KEY"],
            region_name=region,
            config=Config(signature_version="s3v4", retries={"max_attempts": 6, "mode": "standard"}),
        )

    def list_keys(self, prefix: str) -> Iterator[Tuple[str, int]]:
        """Every file under `prefix`, as (key, size in bytes). Pages through 1000 at a time."""
        token = None
        while True:
            kw = {"Bucket": self.bucket, "Prefix": prefix, "MaxKeys": 1000}
            if token:
                kw["ContinuationToken"] = token
            resp = self.client.list_objects_v2(**kw)
            for obj in resp.get("Contents", []) or []:
                yield obj["Key"], int(obj.get("Size", 0))
            if not resp.get("IsTruncated"):
                break
            token = resp.get("NextContinuationToken")

    def get_bytes(self, key: str) -> bytes:
        """Fetch one file into memory."""
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def download(self, key: str, path: str) -> None:
        """Fetch one file to disk. Written to a temp name first, so a half download never
        looks like a finished one."""
        tmp = str(path) + ".part"
        self.client.download_file(self.bucket, key, tmp)
        os.replace(tmp, str(path))

    def size_of(self, key: str) -> int:
        return int(self.client.head_object(Bucket=self.bucket, Key=key)["ContentLength"])
