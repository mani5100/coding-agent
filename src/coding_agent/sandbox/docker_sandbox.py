# src/coding_agent/sandbox/docker_sandbox.py

import docker
from pathlib import Path
from docker.models.containers import Container
from docker.errors import DockerException

from coding_agent.core.config import settings
from coding_agent.core.log_manager import get_logger

logger = get_logger(__name__)


def _to_docker_path(path: str) -> str:
    """
    Convert a path to a Docker-compatible volume mount path.
    On Windows, Docker Desktop needs forward slashes: C:/Users/...
    """
    return Path(path).resolve().as_posix()


class DockerSandbox:
    def __init__(self, working_dir: str):
        self.working_dir = working_dir
        self.client = docker.from_env()
        self.container: Container | None = None

    def start(self) -> None:
        """Spin up the sandbox container with the working dir mounted."""
        docker_path = _to_docker_path(self.working_dir)
        logger.info(f"Mounting host path: {docker_path}")

        try:
            self.container = self.client.containers.run(
                image=settings.docker_image,
                command="sleep infinity",
                detach=True,
                tty=False,
                working_dir=settings.container_workdir,
                volumes={
                    docker_path: {
                        "bind": settings.container_workdir,
                        "mode": "rw",
                    }
                },
                mem_limit="512m",
                nano_cpus=1_000_000_000,
                network_mode="bridge",
                ports={
                    "3000/tcp": 3000,   # React, Next.js
                    "4200/tcp": 4200,   # Angular
                    "5000/tcp": 5000,   # Flask
                    "5173/tcp": 5173,   # Vite
                    "8000/tcp": 8000,   # FastAPI, Django
                    "8080/tcp": 8080,   # Alternative HTTP
                },
            )
            logger.info(f"Sandbox started | container={self.container.short_id} | mounted={docker_path}")
        except DockerException as e:
            logger.error(f"Failed to start sandbox: {e}")
            raise

    def exec(self, command: str) -> tuple[int, str, str]:
        """Run a shell command inside the container."""
        if self.container is None:
            raise RuntimeError("Sandbox is not running. Call start() first.")

        try:
            result = self.container.exec_run(
                cmd=["sh", "-c", command],
                workdir=settings.container_workdir,
                demux=True,
            )

            exit_code = result.exit_code
            stdout_bytes, stderr_bytes = result.output or (b"", b"")

            stdout = (stdout_bytes or b"").decode("utf-8", errors="replace").strip()
            stderr = (stderr_bytes or b"").decode("utf-8", errors="replace").strip()

            logger.debug(f"exec exit={exit_code} | cmd={command!r}")
            return exit_code, stdout, stderr

        except DockerException as e:
            logger.error(f"exec failed: {e}")
            return 1, "", str(e)

    def stop(self) -> None:
        """Stop and remove the container."""
        if self.container is None:
            return
        try:
            self.container.stop(timeout=5)
            self.container.remove(force=True)
            logger.info(f"Sandbox stopped | container={self.container.short_id}")
        except DockerException as e:
            logger.warning(f"Error stopping sandbox: {e}")
        finally:
            self.container = None