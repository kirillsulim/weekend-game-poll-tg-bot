from subprocess import run
from pathlib import Path

import os

from oak_build import task


IMAGE_NAME = "weekend-game-poll-tg-bot"
ENV_TOKEN_VAR = "TELEGRAM_BOT_TOKEN"

BUILD_DIR = Path("./build")


@task
def build_docker():
    run(["docker", "build", "-t", IMAGE_NAME, "."], check=True)


@task(depends_on=[build_docker])
def run_docker():
    token = os.getenv(ENV_TOKEN_VAR)
    data_dir = Path(".").absolute() / "data"
    run(
        [
            "docker",
            "run",
            "-e", f"{ENV_TOKEN_VAR}={token}",
            "-v", f"{data_dir}:/app/data",
            IMAGE_NAME,
        ],
        check=True
    )


@task(depends_on=[build_docker])
def build_tar():
    BUILD_DIR.mkdir(exist_ok=True)
    run(["docker", "save", "--output", f"{BUILD_DIR / (IMAGE_NAME + '.tar')}", IMAGE_NAME])