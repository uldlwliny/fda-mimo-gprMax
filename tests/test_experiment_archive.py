from __future__ import annotations

from pathlib import Path

import yaml


REQUIRED_TEMPLATE_DIRS = ["configs", "scripts", "results", "runs", "reports"]
REQUIRED_EXPERIMENT_FIELDS = [
    "schema_version",
    "id",
    "application",
    "title",
    "status",
    "purpose",
    "scenarios",
    "commands",
    "outputs",
    "data_policy",
]


def test_experiments_root_registry_and_template_exist() -> None:
    root = Path("experiments")
    assert (root / "README.md").exists()
    assert (root / "registry.yaml").exists()
    template = root / "_template"
    assert (template / "experiment.yaml").exists()
    assert (template / "README.md").exists()
    for name in REQUIRED_TEMPLATE_DIRS:
        assert (template / name).is_dir()


def test_experiment_template_yaml_required_fields() -> None:
    data = yaml.safe_load(Path("experiments/_template/experiment.yaml").read_text(encoding="utf-8"))
    for field in REQUIRED_EXPERIMENT_FIELDS:
        assert field in data
    assert isinstance(data["commands"], dict)
    assert isinstance(data["outputs"], dict)
    assert isinstance(data["data_policy"], dict)
    assert data["data_policy"]["commit_raw_h5_npz_out"] is False


def test_registry_yaml_structure() -> None:
    data = yaml.safe_load(Path("experiments/registry.yaml").read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert "application_families" in data
    assert "experiments" in data
    assert isinstance(data["experiments"], list)
    for family in ["media_sensitivity", "array_design", "target_detection"]:
        assert family in data["application_families"]
