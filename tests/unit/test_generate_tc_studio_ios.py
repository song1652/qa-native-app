import importlib.util
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).parents[2] / "scripts" / "02_generate.py"
spec = importlib.util.spec_from_file_location("generate_tc_studio_ios", SCRIPT)
generate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generate)


def test_approved_studio_markdown_generates_runnable_ios_text_checks(tmp_path):
    markdown = tmp_path / "tc_SETTINGS_01_general.md"
    markdown.write_text(
        "# TC-SETTINGS_01: 일반 화면\n\n"
        "## 플랫폼\n- iOS\n\n"
        "## 전제조건\n- 설정 앱(com.apple.Preferences)을 실행한 상태\n\n"
        "## 테스트 케이스 1\n\n"
        "### 테스트 함수명\n`test_general`\n\n"
        "### 단계\n1. 설정 홈에서 'General' 항목을 누른다\n\n"
        "### 기대결과\n- 'General' 제목과 'About' 항목이 보인다.\n",
        encoding="utf-8",
    )

    meta = generate.parse_md_file(markdown)
    source = generate.generate_test_file(meta, "ios", strict_locators=True)

    assert 'caps["bundleId"] = "com.apple.Preferences"' in source
    assert "find_element(AppiumBy.ACCESSIBILITY_ID, 'General').click()" in source
    assert "'About'" in source
    assert "{PLACEHOLDER}" not in source
    compile(source, "generated_general.py", "exec")
    generated = tmp_path / "generated_general.py"
    generated.write_text(source, encoding="utf-8")
    lint = subprocess.run(
        [sys.executable, "-m", "flake8", str(generated)], capture_output=True, text=True
    )
    assert lint.returncode == 0, lint.stdout
