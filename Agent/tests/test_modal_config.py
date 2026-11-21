import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from deploy.modal_config import build_vllm_command, deployment_environment, load_deployment_model


def environment(name: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (ROOT / "deploy" / "models" / f"{name}.env").read_text().splitlines():
        if line and not line.startswith("#"):
            key, value = line.split("=", 1)
            values[key] = value
    return values


class DeploymentConfigTests(unittest.TestCase):
    def test_cloud_reimport_keeps_entire_selected_profile(self):
        for name in ("qwen", "glm", "llama"):
            model = load_deployment_model(environment(name))
            self.assertEqual(load_deployment_model(deployment_environment(model)), model)

    def test_qwen_uses_compose_environment_and_awq(self):
        model = load_deployment_model(environment("qwen"))
        command = build_vllm_command(model, api_key="internal-test-key")

        self.assertEqual(model.name, "qwen")
        self.assertIn("Qwen/Qwen3-8B-AWQ", command)
        self.assertIn("--quantization", command)
        self.assertIn("--enable-auto-tool-choice", command)
        self.assertIn("--enforce-eager", command)
        self.assertIn("hermes", command)

    def test_all_compose_model_environments_are_valid(self):
        for name in ("qwen", "glm", "llama"):
            with self.subTest(name=name):
                self.assertEqual(load_deployment_model(environment(name)).name, name)

    def test_non_quantized_models_do_not_emit_empty_argument(self):
        model = load_deployment_model(environment("llama"))
        self.assertNotIn("--quantization", build_vllm_command(model))

    def test_missing_required_model_value_is_rejected(self):
        values = environment("qwen")
        values["MODEL_CHECKPOINT"] = ""
        with self.assertRaises(ValueError):
            load_deployment_model(values)
