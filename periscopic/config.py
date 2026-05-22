from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


FieldFlatteningMode = Literal["tangential", "sagittal", None]
BreakSymmetryMode = Literal["none", "curvatures", "full"]


@dataclass
class PeriscopicConfig:
    effective_focal_length: float = 200.0
    lens_separation: float = 180.0
    wavelength_um: float = 0.55
    glass: str = "SF2"
    glass_fallbacks: tuple[str, ...] = ("SF2", "N-SF2")
    refractive_index: float = 1.65174
    selected_power: float = 0.0038
    alternate_power: float = 0.0073
    field_angles_deg: tuple[float, ...] = (0.0, 10.0, 15.0)
    working_f_number: float = 10.0
    initial_thickness: float = 15.0
    final_thickness: float = 5.0
    initial_object_distance: float = 800.0
    pmag_target: float = -1.0
    pmag_weight: float = 1.0
    efly_weight: float = 1.0
    field_flattening: FieldFlatteningMode = "tangential"
    break_symmetry: BreakSymmetryMode = "full"
    output_dir: Path = field(default_factory=lambda: Path("outputs") / "periscopic")
    local_optimization_cycles: int = 10
    local_optimization_algorithm: str = "DampedLeastSquares"
    number_of_cores: int | None = None
    save_extension: str = ".zos"
    use_dummy_image_surface: bool = True
    pause_after_stage: bool = True
    stop_after_stage: int | None = None

    @property
    def initial_radius(self) -> float:
        return 2.0 * (self.refractive_index - 1.0) / self.selected_power

    @property
    def half_lens_separation(self) -> float:
        return self.lens_separation / 2.0

    def stage_path(self, stage_code: str) -> Path:
        return self.output_dir / f"{stage_code}{self.save_extension}"
