from __future__ import annotations

from pathlib import Path

from periscopic.config import PeriscopicConfig
from periscopic.connection import connect_opticstudio
from periscopic.workflow import run_workflow


def main() -> None:
    config = PeriscopicConfig(output_dir=Path("outputs") / "periscopic")
    connection = connect_opticstudio(standalone=False, instance=0)
    run_workflow(connection.system, connection.zosapi, config)


if __name__ == "__main__":
    main()
