from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict, dataclass
from typing import Iterable, List


@dataclass(frozen=True)
class BranchCell:
    seed: int
    channel: str
    fade: float
    repeat: int
    launch_index: int = -1

    @property
    def key(self) -> str:
        return f"seed{self.seed:04d}_{self.channel}_fade{self.fade:.2f}_r{self.repeat}"


def randomized_cells(seeds: Iterable[int], channels: Iterable[str],
                     fades: Iterable[float], repeats: int, random_seed: int) -> List[BranchCell]:
    cells = [BranchCell(int(seed), str(channel), float(fade), repeat)
             for seed in seeds for channel in channels for fade in fades
             for repeat in range(repeats)]
    random.Random(random_seed).shuffle(cells)
    return [BranchCell(cell.seed, cell.channel, cell.fade, cell.repeat, index)
            for index, cell in enumerate(cells)]


def launch_order_sha256(cells: Iterable[BranchCell]) -> str:
    payload = [asdict(cell) for cell in cells]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
