from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml

from subagg.subscription.merge import merge_nodes
from subagg.subscription.normalize import fingerprint_proxy
from subagg.subscription.output import build_mihomo_yaml
from subagg.subscription.parser import parse_source
from subagg.subscription.profile import build_rule_profile

DEFAULT_SAMPLES = ("Quantum-Air.xyz", "念云", "星尘云")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify that generated Mihomo YAML preserves the semantic unique node set of local samples."
    )
    parser.add_argument("--samples-dir", type=Path, required=True)
    parser.add_argument("--mihomo", type=Path)
    parser.add_argument("--profile", choices=("metacubex", "minimal"), default="metacubex")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    results = []
    for filename in DEFAULT_SAMPLES:
        path = args.samples_dir / filename
        if not path.is_file():
            raise FileNotFoundError(f"missing sample: {filename}")
        results.append(parse_source(path.read_bytes(), filename))

    input_nodes = [node for result in results for node in result.nodes]
    input_fingerprints = {fingerprint_proxy(node.proxy) for node in input_nodes}
    merged_nodes, _, _, _ = merge_nodes(
        [(result.source, [node.proxy for node in result.nodes]) for result in results]
    )
    output = build_mihomo_yaml(
        [node.proxy for node in merged_nodes],
        build_rule_profile([node.name for node in merged_nodes], args.profile),
    )
    output_proxies = yaml.safe_load(output)["proxies"]
    output_fingerprints = {fingerprint_proxy(proxy) for proxy in output_proxies}

    missing = input_fingerprints - output_fingerprints
    unexpected = output_fingerprints - input_fingerprints
    duplicate_count = len(input_nodes) - len(input_fingerprints)
    print(
        "input_nodes=%d input_unique=%d output_nodes=%d output_unique=%d duplicates_merged=%d"
        % (len(input_nodes), len(input_fingerprints), len(output_proxies), len(output_fingerprints), duplicate_count)
    )
    if missing or unexpected or len(output_proxies) != len(output_fingerprints):
        print("semantic_node_sets_match=False")
        return 1
    print("semantic_node_sets_match=True")

    if args.mihomo:
        _validate_with_mihomo(args.mihomo, args.samples_dir, output)
        print("mihomo_config_check=True")
    return 0


def _validate_with_mihomo(binary: Path, temporary_parent: Path, output: str) -> None:
    if not binary.is_file():
        raise FileNotFoundError(f"mihomo binary not found: {binary}")
    temporary_dir = Path(tempfile.mkdtemp(prefix="subagg-mihomo-", dir=temporary_parent))
    config_path = temporary_dir / "generated.yaml"
    try:
        config_path.write_text(output, encoding="utf-8")
        completed = subprocess.run(
            [str(binary), "-t", "-f", str(config_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if completed.returncode:
            raise RuntimeError("Mihomo configuration check failed")
    finally:
        shutil.rmtree(temporary_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
