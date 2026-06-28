from subprocess import run
from pathlib import Path

import os

from oak_build import task

IMAGE_NAME = "weekend-game-poll-tg-bot"
BUILD_DIR = Path("./build")


@task
def build_docker():
    run(["docker", "build", "-t", IMAGE_NAME, "."], check=True)


@task(depends_on=[build_docker])
def run_docker():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise Exception("Please set the environment variable TELEGRAM_BOT_TOKEN")
    data_dir = Path(".").absolute() / "data"
    run(
        [
            "docker",
            "run",
            "-e", f"TELEGRAM_BOT_TOKEN={token}",
            "-e", f"DB_PATH=/data/bot_data.sqlite",
            "-v", f"{data_dir}:/data",
            IMAGE_NAME,
        ],
        check=True
    )


@task(depends_on=[build_docker])
def build_tar():
    BUILD_DIR.mkdir(exist_ok=True)
    run(["docker", "save", "--output", f"{BUILD_DIR / (IMAGE_NAME + '.tar')}", IMAGE_NAME])