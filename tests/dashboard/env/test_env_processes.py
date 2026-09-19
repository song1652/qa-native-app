"""Environment process helper contracts."""

from subprocess import CompletedProcess

from agents.dashboard.utils.env_processes import command_detail


def test_command_detail_prefers_stderr_and_decodes_bytes():
    result = CompletedProcess(
        args=["tool"],
        returncode=1,
        stdout=b"less useful",
        stderr="실행 실패".encode(),
    )

    assert command_detail(result) == "실행 실패"


def test_command_detail_falls_back_to_stdout_then_default():
    stdout_only = CompletedProcess(["tool"], 1, stdout=" output ", stderr="")
    empty = CompletedProcess(["tool"], 1, stdout="", stderr="")

    assert command_detail(stdout_only) == "output"
    assert command_detail(empty) == "명령 실행에 실패했습니다."
