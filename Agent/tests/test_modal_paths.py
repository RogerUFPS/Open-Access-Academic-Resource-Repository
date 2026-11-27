"""Las rutas del SDK remoto no coinciden con las del repositorio."""
import ast
import unittest
from pathlib import Path
from unittest.mock import patch


class ModalPathTests(unittest.TestCase):
    def root_for(self, name, remote_file, existing):
        path = Path(__file__).resolve().parents[1] / "deploy/modal" / name
        tree = ast.parse(path.read_text())
        assignment = next(n for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "LOCAL_ROOT" for t in n.targets))
        context = {"Path": Path, "__file__": remote_file}
        with patch.object(Path, "is_file", lambda p: str(p) in existing):
            exec(compile(ast.Module(body=[assignment], type_ignores=[]), str(path), "exec"), context)
        return context["LOCAL_ROOT"]

    def test_server_imported_from_root_uses_packaged_application(self):
        self.assertEqual(self.root_for("app.py", "/root/app.py", {"/app/SKILL.md"}), Path("/app"))

    def test_cpu_download_uses_its_packaged_deploy_directory(self):
        self.assertEqual(self.root_for("tasks.py", "/root/tasks.py", {"/root/deploy/model_config.py"}), Path("/root"))

    def test_local_repository_remains_supported(self):
        self.assertEqual(self.root_for("app.py", "/tmp/project/Agent/deploy/modal/app.py", set()), Path("/tmp/project/Agent"))
