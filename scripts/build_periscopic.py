from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from periscopic.config import PeriscopicConfig
from periscopic.connection import connect_opticstudio
from periscopic.workflow import run_workflow


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and optimize a symmetric periscopic lens in OpticStudio.")
    parser.add_argument("--standalone", action="store_true", help="Launch/connect using ZOS-API standalone mode.")
    parser.add_argument("--instance", type=int, default=0, help="Interactive Extension instance number.")
    parser.add_argument("--field-flattening", choices=("none", "tangential", "sagittal"), default="tangential")
    parser.add_argument("--break-symmetry", choices=("none", "curvatures", "full"), default="full")
    parser.add_argument("--output", type=Path, default=Path("outputs") / "periscopic")
    parser.add_argument("--cycles", type=int, default=10)
    parser.add_argument("--cores", type=int, default=None)
    parser.add_argument("--initial-thickness", type=float, default=15.0)
    parser.add_argument("--final-thickness", type=float, default=5.0)
    parser.add_argument("--pause-after-stage", action="store_true", default=True, help="Pause for Enter after each completed stage.")
    parser.add_argument("--no-pause-after-stage", action="store_false", dest="pause_after_stage", help="Run stages continuously without waiting for Enter.")
    parser.add_argument("--stop-after-stage", type=int, default=None, help="Stop after this stage index, e.g. 0 for Stage 0 only.")
    parser.add_argument("--only-stage", type=int, default=None, help="Run only this stage index on the currently open system.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    flattening = None if args.field_flattening == "none" else args.field_flattening
    config = PeriscopicConfig(
        field_flattening=flattening,
        break_symmetry=args.break_symmetry,
        output_dir=args.output,
        local_optimization_cycles=args.cycles,
        number_of_cores=args.cores,
        initial_thickness=args.initial_thickness,
        final_thickness=args.final_thickness,
        pause_after_stage=args.pause_after_stage,
        stop_after_stage=args.stop_after_stage,
        only_stage=args.only_stage,
    )
    connection = connect_opticstudio(standalone=args.standalone, instance=args.instance)
    run_workflow(connection.system, connection.zosapi, config)


if __name__ == "__main__":
    main()
