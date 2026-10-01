import importlib.util
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).parents[2] / "scripts" / "02_generate.py"
spec = importlib.util.spec_from_file_location("generate_tc_studio", SCRIPT)
generate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generate)


def test_approved_studio_markdown_generates_runnable_android_text_checks(tmp_path):
    markdown = tmp_path / "tc_LOC_01_location.md"
    markdown.write_text(
        "# TC-LOC_01: 위치 화면\n\n"
        "## 플랫폼\n- Android\n\n"
        "## 전제조건\n- 설정 앱(com.android.settings/.homepage.SettingsHomepageActivity)을 실행한 상태\n\n"
        "## 테스트 케이스 1\n\n"
        "### 테스트 함수명\n`test_location`\n\n"
        "### 단계\n1. 설정 홈에서 '위치' 항목을 누른다\n\n"
        "### 기대결과\n- '위치' 제목과 '위치 사용', '위치 서비스' 항목이 보인다.\n",
        encoding="utf-8",
    )

    meta = generate.parse_md_file(markdown)
    source = generate.generate_test_file(meta, "android", strict_locators=True)

    assert 'caps["appPackage"] = "com.android.settings"' in source
    assert 'caps["appActivity"] = ".homepage.SettingsHomepageActivity"' in source
    assert 'caps["udid"] = _uid' in source
    assert "UiScrollable" in source
    assert '"위치 사용"' in source and '"위치 서비스"' in source
    assert '@content-desc="위치"' in source
    assert "{PLACEHOLDER}" not in source
    compile(source, "generated_location.py", "exec")
    generated = tmp_path / "generated_location.py"
    generated.write_text(source, encoding="utf-8")
    lint = subprocess.run(
        [sys.executable, "-m", "flake8", str(generated)], capture_output=True, text=True
    )
    assert lint.returncode == 0, lint.stdout
