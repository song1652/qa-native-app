import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[2] / "scripts" / "02_generate.py"
spec = importlib.util.spec_from_file_location("generate_script", SCRIPT)
generate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generate)


def test_generated_test_uses_native_first_hybrid_runtime(monkeypatch):
    monkeypatch.setattr(generate, "load_registry", lambda: {
        "targets": {
            "login.username": {
                "android": {
                    "surface": "auto",
                    "strategy": "ID",
                    "value": "app:id/username",
                    "webview": {"strategy": "label", "value": "아이디"},
                }
            }
        }
    })
    metadata = {
        "tc_number": "001", "tc_slug": "login", "title": "로그인",
        "precondition": "", "tc_blocks": [{
            "function_name": "test_login", "steps": ["username 필드를 확인한다"],
            "expected": "username", "selectors": {"username": "app:id/username"},
        }],
    }
    source = generate.generate_test_file(metadata, "android")
    assert "HybridSession(self.driver)" in source
    assert "'surface': 'auto'" in source
    assert "'strategy': 'label'" in source
    assert "self._find(AppiumBy.ID, SEL_USERNAME)" in source
    compile(source, "generated_test.py", "exec")
