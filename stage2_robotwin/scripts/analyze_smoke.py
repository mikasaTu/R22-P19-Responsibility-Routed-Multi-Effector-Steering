"""Create auditable plots and event-frame montages for Stage-2 smoke runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


EVENTS = ("E0", "E1", "E2", "E3", "E4", "E5", "E6")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def artifact_path(value: str, repo_root: Path) -> Path:
    path = Path(value)
    if path.is_file():
        return path
    marker = "stage2_robotwin/"
    if marker in value:
        return repo_root / marker / value.split(marker, 1)[1]
    raise FileNotFoundError(value)


def event_steps(episode: Dict[str, Any]) -> Dict[str, int]:
    return {
        name: int(episode["event_audit"]["events"][name]["step"])
        for name in EVENTS
    }


def plot_episode(
    episode: Dict[str, Any], trace_path: Path, output_path: Path
) -> Dict[str, float]:
    frame = pd.read_parquet(trace_path)
    position = np.stack(frame["object_position"].map(np.asarray))
    linear = np.stack(frame["object_linear_velocity"].map(np.asarray))
    angular = np.stack(frame["object_angular_velocity"].map(np.asarray))
    time_s = frame["time_s"].to_numpy()
    events = event_steps(episode)

    figure, axes = plt.subplots(4, 1, figsize=(11, 11), sharex=True)
    axes[0].plot(time_s, position[:, 0], label="x")
    axes[0].plot(time_s, position[:, 1], label="y")
    axes[0].plot(time_s, position[:, 2], label="z")
    axes[0].set_ylabel("object pos [m]")
    axes[0].legend(ncol=3)

    axes[1].plot(time_s, np.linalg.norm(linear, axis=1), label="linear")
    axes[1].plot(time_s, np.linalg.norm(angular, axis=1), label="angular")
    axes[1].set_ylabel("twist norm")
    axes[1].legend(ncol=2)

    axes[2].step(time_s, frame["left_contact"].astype(int), label="left")
    axes[2].step(time_s, frame["right_contact"].astype(int), label="right")
    axes[2].set_ylabel("object contact")
    axes[2].set_ylim(-0.1, 1.1)
    axes[2].legend(ncol=2)

    axes[3].plot(time_s, frame["left_impulse"], label="left impulse")
    axes[3].plot(time_s, frame["right_impulse"], label="right impulse")
    axes[3].set_ylabel("impulse sum")
    axes[3].set_xlabel("expert trajectory time [s]")
    axes[3].legend(ncol=2)

    for axis in axes:
        for index, name in enumerate(EVENTS):
            event_time = events[name] / 250.0
            axis.axvline(event_time, color=f"C{index % 10}", alpha=0.45)
        axis.grid(alpha=0.2)
    axes[0].set_title(
        f"episode {episode['episode']} seed {episode['seed']} | "
        f"donor={episode['donor']} receiver={episode['receiver']}"
    )
    figure.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=160)
    plt.close(figure)
    return {
        "overlap_E2_to_E5_s": (events["E5"] - events["E2"]) / 250.0,
        "stable_overlap_E3_to_E4_s": (events["E4"] - events["E3"]) / 250.0,
        "receiver_only_E5_to_E6_s": (events["E6"] - events["E5"]) / 250.0,
        "minimum_object_height_m": float(position[:, 2].min()),
    }


def read_video_frame(capture: cv2.VideoCapture, index: int) -> np.ndarray:
    capture.set(cv2.CAP_PROP_POS_FRAMES, int(index))
    ok, frame = capture.read()
    if not ok:
        raise RuntimeError(f"cannot read video frame {index}")
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)


def event_frame_index(step: int, all_steps: Iterable[int]) -> int:
    extra_before = len({value for value in all_steps if value < step and value % 25})
    current_extra = 1 if step % 25 else 0
    return step // 25 + current_extra + extra_before


def make_event_montage(
    episode: Dict[str, Any], video_path: Path, output_path: Path
) -> None:
    steps = event_steps(episode)
    capture = cv2.VideoCapture(str(video_path))
    images: List[np.ndarray] = []
    for name in EVENTS:
        image = read_video_frame(
            capture, event_frame_index(steps[name], steps.values())
        )
        cv2.putText(
            image,
            f"{name} step={steps[name]}",
            (8, image.shape[0] - 12),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 0),
            2,
            cv2.LINE_AA,
        )
        images.append(image)
    capture.release()

    figure, axes = plt.subplots(2, 4, figsize=(16, 7))
    for axis, image, name in zip(axes.flat, images, EVENTS):
        axis.imshow(image)
        axis.set_title(name)
        axis.axis("off")
    axes.flat[-1].axis("off")
    figure.suptitle(
        f"Visual event audit: episode {episode['episode']}, seed {episode['seed']}"
    )
    figure.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=150)
    plt.close(figure)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--report-dir", required=True)
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    report_dir = Path(args.report_dir).resolve()
    repo_root = Path(__file__).resolve().parents[2]
    summary = read_json(run_dir / "smoke_summary.json")
    metrics = []
    for episode in summary["episodes"]:
        trace_path = artifact_path(episode["trace"], repo_root)
        video_path = artifact_path(episode["video"], repo_root)
        stem = f"episode_{episode['episode']:02d}_seed_{episode['seed']:04d}"
        values = plot_episode(
            episode, trace_path, report_dir / "curves" / f"{stem}.png"
        )
        make_event_montage(
            episode, video_path, report_dir / "event_montages" / f"{stem}.png"
        )
        metrics.append(
            {
                "episode": episode["episode"],
                "seed": episode["seed"],
                **values,
            }
        )
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "smoke_trace_metrics.json").write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
