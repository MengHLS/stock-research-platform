"""The development supervisor must only stop processes it started."""

import json
import os
import runpy
import signal
import subprocess
from pathlib import Path
from unittest.mock import Mock, call

import pytest


@pytest.fixture
def tasks(monkeypatch, tmp_path):
    namespace = runpy.run_path(str(Path(__file__).resolve().parents[2] / "tools/project.py"))
    scope = namespace["dev"].__globals__
    monkeypatch.setitem(scope, "SCRATCH", tmp_path)
    monkeypatch.setattr(scope["shutil"], "which", lambda _: "pnpm")
    # Lifecycle cases control children rather than touching a user's active ports.
    monkeypatch.setitem(scope, "check_dev_ports", lambda: None)
    job = Mock()
    job.assign.return_value = True
    job.terminate.return_value = True
    monkeypatch.setitem(scope, "WindowsProcessJob", Mock(return_value=job))
    scope["_test_job"] = job
    return scope


def test_second_start_failure_releases_first_child(tasks, monkeypatch):
    first = Mock(pid=12345)
    first.poll.return_value = None
    monkeypatch.setattr(
        tasks["subprocess"], "Popen", Mock(side_effect=[first, OSError("frontend failed")])
    )
    stopped = []
    monkeypatch.setitem(tasks, "stop_dev_process", lambda process: stopped.append(process) or True)

    with pytest.raises(OSError, match="frontend failed"):
        tasks["dev"]()

    assert stopped == [first]
    job = tasks["_test_job"]
    if tasks["os"].name == "nt":
        job.assign.assert_called_once_with(first)
        job.terminate.assert_called_once()
        job.close.assert_called_once()
    else:
        job.assign.assert_not_called()
        job.terminate.assert_not_called()


def test_unexpected_exit_returns_failure_and_stops_only_owned_children(tasks, monkeypatch):
    first = Mock(pid=12345)
    first.poll.return_value = 7
    second = Mock(pid=23456)
    second.poll.return_value = None
    popen = Mock(side_effect=[first, second])
    monkeypatch.setattr(tasks["subprocess"], "Popen", popen)
    stopped = []
    monkeypatch.setitem(tasks, "stop_dev_process", lambda process: stopped.append(process) or True)

    with pytest.raises(SystemExit) as failure:
        tasks["dev"]()

    assert failure.value.code == 7
    assert stopped == [first, second]
    web_command = popen.call_args_list[1].args[0]
    if tasks["os"].name == "nt":
        assert "--strictPort" in json.loads(web_command[-1])
        assert all(
            call.kwargs["creationflags"] == subprocess.CREATE_NEW_PROCESS_GROUP
            for call in popen.call_args_list
        )
        tasks["_test_job"].assign.assert_has_calls([call(first), call(second)])
        tasks["_test_job"].terminate.assert_called_once()
    else:
        assert "--strictPort" in web_command
        tasks["_test_job"].assign.assert_not_called()
        tasks["_test_job"].terminate.assert_not_called()


def test_ctrl_c_stops_owned_children_without_an_error(tasks, monkeypatch):
    first, second = Mock(pid=12345), Mock(pid=23456)
    for child in (first, second):
        child.poll.return_value = None
    first.wait.side_effect = KeyboardInterrupt
    monkeypatch.setattr(tasks["subprocess"], "Popen", Mock(side_effect=[first, second]))
    stopped = []
    monkeypatch.setitem(tasks, "stop_dev_process", lambda process: stopped.append(process) or True)

    tasks["dev"]()

    assert stopped == [first, second]
    job = tasks["_test_job"]
    if tasks["os"].name == "nt":
        job.assign.assert_has_calls([call(first), call(second)])
        job.terminate.assert_called_once()
    else:
        job.assign.assert_not_called()
        job.terminate.assert_not_called()


def test_cleanup_failure_returns_nonzero_after_ctrl_c(tasks, monkeypatch):
    first, second = Mock(pid=12345), Mock(pid=23456)
    for child in (first, second):
        child.poll.return_value = None
    first.wait.side_effect = KeyboardInterrupt
    monkeypatch.setattr(tasks["subprocess"], "Popen", Mock(side_effect=[first, second]))
    monkeypatch.setitem(tasks, "stop_dev_process", lambda process: False)

    with pytest.raises(SystemExit) as failure:
        tasks["dev"]()

    assert failure.value.code == 1


@pytest.mark.skipif(os.name != "nt", reason="Windows process semantics")
def test_windows_children_are_assigned_before_their_start_gate_opens(tasks, monkeypatch):
    first, second = Mock(pid=12345), Mock(pid=23456)
    first.stdin = Mock()
    second.stdin = Mock()
    events = []
    for child in (first, second):
        child.poll.return_value = None
    first.wait.side_effect = KeyboardInterrupt
    tasks["_test_job"].assign.side_effect = lambda child: events.append(("assign", child)) or True
    first.stdin.write.side_effect = lambda _: events.append(("start", first))
    second.stdin.write.side_effect = lambda _: events.append(("start", second))
    popen = Mock(side_effect=[first, second])
    monkeypatch.setattr(tasks["subprocess"], "Popen", popen)
    monkeypatch.setitem(tasks, "stop_dev_process", lambda process: True)

    tasks["dev"]()

    assert events == [
        ("assign", first),
        ("start", first),
        ("assign", second),
        ("start", second),
    ]
    for index, command in enumerate(
        (
            [
                tasks["sys"].executable,
                "-m",
                "uvicorn",
                "research_platform.main:create_app",
                "--factory",
                "--reload",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
            ],
            ["pnpm", "dev", "--port", "5173", "--strictPort"],
        )
    ):
        launch = popen.call_args_list[index]
        assert launch.args[0][:3] == [
            tasks["sys"].executable,
            "-c",
            tasks["_WINDOWS_DEV_GATE"],
        ]
        assert json.loads(launch.args[0][3]) == command
        assert launch.kwargs["stdin"] is tasks["subprocess"].PIPE
        assert launch.kwargs["text"] is True
    first.stdin.close.assert_called_once()
    second.stdin.close.assert_called_once()


@pytest.mark.skipif(os.name != "nt", reason="Windows process semantics")
def test_windows_start_gate_releases_a_real_command(tasks, tmp_path):
    marker = tmp_path / "gate-ran.txt"
    command = [
        tasks["sys"].executable,
        "-c",
        f"from pathlib import Path; Path({str(marker)!r}).write_text('ran')",
    ]
    process = tasks["_start_dev_child"](
        command,
        cwd=tmp_path,
        group_options={"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP},
    )
    try:
        assert process.poll() is None
        tasks["_open_dev_child_gate"](process)
        assert process.wait(timeout=10) == 0
        assert marker.read_text(encoding="utf-8") == "ran"
    finally:
        tasks["stop_dev_process"](process)


def test_port_precheck_failure_does_not_launch_children(tasks, monkeypatch):
    launch = Mock()
    monkeypatch.setattr(tasks["subprocess"], "Popen", launch)
    monkeypatch.setitem(
        tasks,
        "check_dev_ports",
        Mock(side_effect=SystemExit("Development port 8000 is unavailable")),
    )

    with pytest.raises(SystemExit, match="unavailable"):
        tasks["dev"]()

    launch.assert_not_called()


def test_busy_port_check_preserves_existing_listener():
    import socket

    scope = runpy.run_path(str(Path(__file__).resolve().parents[2] / "tools/project.py"))
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        with pytest.raises(SystemExit, match=str(port)):
            scope["check_dev_ports"]((port,))
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            pass


@pytest.mark.skipif(os.name != "nt", reason="Windows process semantics")
def test_stop_exited_windows_process_never_signals_a_reused_pid(tasks, monkeypatch):
    exited = Mock(pid=12345)
    exited.poll.return_value = 0
    kill = Mock()
    monkeypatch.setattr(tasks["subprocess"], "run", kill)
    tasks["stop_dev_process"](exited)
    kill.assert_not_called()
    exited.send_signal.assert_not_called()


@pytest.mark.skipif(os.name != "nt", reason="Windows process semantics")
def test_stop_windows_group_cooperatively_then_forces_the_tree(tasks, monkeypatch):
    child = Mock(pid=12345)
    child.poll.return_value = None
    child.wait.side_effect = [subprocess.TimeoutExpired("child", 10), None]
    forced = Mock()
    monkeypatch.setattr(tasks["subprocess"], "run", forced)
    assert tasks["stop_dev_process"](child) is False
    child.send_signal.assert_called_once_with(signal.CTRL_BREAK_EVENT)
    forced.assert_called_once_with(
        ["taskkill", "/PID", "12345", "/T", "/F"],
        check=False,
    )
    assert child.wait.call_count == 2


@pytest.mark.skipif(os.name == "nt", reason="POSIX process semantics")
def test_stop_waits_for_a_posix_group_after_its_leader_exits(tasks, monkeypatch):
    child = Mock(pid=12345)
    child.poll.return_value = 0
    group_exists = iter([True, False])
    killpg = Mock()
    monkeypatch.setattr(tasks["os"], "killpg", killpg)
    monkeypatch.setitem(
        tasks,
        "_posix_process_group_exists",
        lambda _: next(group_exists),
    )

    assert tasks["stop_dev_process"](child) is True

    killpg.assert_called_once_with(12345, signal.SIGTERM)
