"""Runtime secret loading from AWS SSM Parameter Store.

Secrets are never written to disk and never committed. Each parameter under
the configured prefix holds the full contents of a .env file as its value.

Nothing here names a particular account: the profile, region and prefix are
read from the environment (TICKERROOM_SSM_PROFILE / _REGION / _PREFIX). A
deployment that names its own store in code is publishing a map of where its
credentials live, which is free reconnaissance and buys nothing.

SSM is optional. An env var named after the key (PARALLEL_API_KEY) is
consulted first, so running this needs no AWS account at all.
"""
from __future__ import annotations

import os
from functools import lru_cache

import boto3

PROFILE = os.environ.get("TICKERROOM_SSM_PROFILE", "")
REGION = os.environ.get("TICKERROOM_SSM_REGION", "eu-west-1")
PREFIX = os.environ.get("TICKERROOM_SSM_PREFIX", "/tickerroom/secrets/")


def _session():
    """A boto3 session that works locally and in a container.

    Locally the named profile is present. In Cloud Run it is not, and
    credentials come from the environment instead, so asking for the profile
    would fail before the environment is ever consulted.
    """
    if not PROFILE:
        return boto3.Session(region_name=REGION)
    try:
        return boto3.Session(profile_name=PROFILE, region_name=REGION)
    except Exception:
        return boto3.Session(region_name=REGION)


@lru_cache(maxsize=None)
def _load(env_file: str) -> dict[str, str]:
    # An env var wins over SSM: it is how the deployed container receives a
    # secret without carrying AWS credentials.
    direct = os.environ.get(env_file.replace(".env", "").upper() + "_ENV")
    raw = direct or _session().client("ssm").get_parameter(
        Name=f"{PREFIX}{env_file}", WithDecryption=True
    )["Parameter"]["Value"]
    out: dict[str, str] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def get_key(env_file: str, key: str) -> str:
    """get_key("parallel.env", "PARALLEL_API_KEY") -> the key.

    The named variable is honoured first, so `export PARALLEL_API_KEY=...` is
    all a clone needs and SSM is never contacted. Without this the only way in
    was the whole-file form (PARALLEL_ENV), which is what the deployed
    container uses but is a strange thing to ask of someone running it once.
    """
    direct = os.environ.get(key)
    if direct:
        return direct
    return _load(env_file)[key]


def load_env(env_file: str) -> None:
    """Push every key of an env file into os.environ, without touching disk."""
    for k, v in _load(env_file).items():
        os.environ.setdefault(k, v)
