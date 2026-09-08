"""Portable command-line entry point."""

import argparse
import asyncio
import json
import sys

from . import __version__
from .client import HunyuanClient, HunyuanError, Settings


async def probe(settings: Settings) -> dict:
    # Job 0 is deliberately nonexistent: this probe cannot create a generation job.
    async with HunyuanClient(settings) as client:
        try:
            return await client.query("0")
        except HunyuanError as exc:
            if "FailedOperation.JobNotFound:" in str(exc):
                return {"authenticated": True, "generation_jobs_created": 0, "detail": str(exc)}
            raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Tencent Hunyuan 3D MCP server (STDIO)")
    parser.add_argument("--version", action="version", version=__version__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check-config", action="store_true", help="Local check; no network calls")
    group.add_argument("--probe-auth", action="store_true", help="ONE query of nonexistent JobId 0")
    args = parser.parse_args()
    try:
        settings = Settings.from_env()
        if args.check_config:
            print(json.dumps(settings.public_info(), indent=2))
            if not settings.tc3_configured:
                sys.exit(1)
        elif args.probe_auth:
            print(json.dumps(asyncio.run(probe(settings)), ensure_ascii=False, indent=2))
        else:
            from .server import create_server

            create_server(settings).run(transport="stdio")
    except HunyuanError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
