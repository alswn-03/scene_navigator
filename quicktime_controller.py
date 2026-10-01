# QuickTime과 통신
# - QuickTime Player 제어 전담
# - 영상 열기
# - 현재 시간 / 전체 길이 / 재생 여부 읽기
# - 특정 시점으로 이동, 재생 / 일시정지
# - QuickTimeWorker: osascript를 UI 스레드 밖에서 실행 (UI 끊김 방지)

import queue
import subprocess
import time
from dataclasses import dataclass, replace

from PySide6.QtCore import QThread, Signal

# 폴링 간격(초). osascript 1회가 약 40ms라 실제 갱신은 약 120ms 주기.
# 화면 표시는 main.py에서 이 사이를 보간하므로 더 줄일 필요는 없다.
POLL_INTERVAL = 0.12


@dataclass(frozen=True)
class QuickTimeState:
    # "ok" | "no_app" (QuickTime 미실행) | "no_document" | "error"
    status: str
    current: float = 0.0
    duration: float = 0.0
    playing: bool = False
    rate: float = 0.0
    sampled_at: float = 0.0  # time.monotonic() 기준 측정 시각
    commands_done: int = 0  # 이 시점까지 처리된 명령 수


class QuickTimeController:
    """동기 방식 QuickTime 제어. 반드시 워커 스레드에서만 호출한다."""

    def open_video(self, path: str):
        subprocess.Popen(["open", "-a", "QuickTime Player", path])

    def _osascript(self, script: str) -> str:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=3,
        )

        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "osascript 오류")

        return result.stdout.strip()

    @staticmethod
    def _to_float(text: str) -> float:
        # 로케일에 따라 소수점이 ',' 로 나오는 경우 방어
        return float(text.replace(",", "."))

    def get_state(self) -> QuickTimeState:
        # `is running` 은 앱을 실행시키지 않는다.
        # (tell 블록을 먼저 열면 종료한 QuickTime이 다시 켜진다)
        started = time.monotonic()

        result = self._osascript(
            '''
            if application "QuickTime Player" is not running then return "off"

            tell application "QuickTime Player"
                if (count of documents) = 0 then return "nodoc"

                tell front document
                    return "ok|" & (current time as text) & "|" & (duration as text) & "|" & (rate as text)
                end tell
            end tell
            '''
        )

        sampled_at = (started + time.monotonic()) / 2

        if result == "off":
            return QuickTimeState("no_app", sampled_at=sampled_at)

        if result == "nodoc":
            return QuickTimeState("no_document", sampled_at=sampled_at)

        _, current, duration, rate = result.split("|")
        rate = self._to_float(rate)

        return QuickTimeState(
            "ok",
            current=self._to_float(current),
            duration=self._to_float(duration),
            playing=rate != 0,  # 일시정지 시 rate = 0
            rate=rate,
            sampled_at=sampled_at,
        )

    def _run_on_document(self, command: str):
        result = self._osascript(
            f'''
            if application "QuickTime Player" is not running then return "off"

            tell application "QuickTime Player"
                if (count of documents) = 0 then return "nodoc"

                tell front document
                    {command}
                end tell
            end tell

            return "ok"
            '''
        )

        if result == "off":
            raise RuntimeError("QuickTime Player가 실행 중이 아닙니다.")

        if result == "nodoc":
            raise RuntimeError("QuickTime에 열린 영상이 없습니다.")

    @staticmethod
    def _play_command(rate: float) -> str:
        # play 는 배속을 1x로 되돌리므로 필요하면 다시 지정
        return "play" if rate == 1 else f"play\nset rate to {rate:.2f}"

    def seek(self, seconds: float, play: bool = False, rate: float = 1.0):
        seconds = max(0.0, float(seconds))

        self._run_on_document(
            f"set current time to {seconds:.3f}\n"
            + (self._play_command(rate) if play else "")
        )

    def play(self, rate: float = 1.0):
        self._run_on_document(self._play_command(rate))

    def set_rate(self, rate: float):
        self._run_on_document(f"set rate to {rate:.2f}")

    def pause(self):
        self._run_on_document("pause")


class QuickTimeWorker(QThread):
    """
    별도 스레드에서 QuickTime 상태를 폴링하고 명령을 실행한다.
    명령과 폴링이 한 스레드에서 직렬 처리되므로 서로 겹치지 않는다.
    """

    state_changed = Signal(object)  # QuickTimeState
    command_failed = Signal(str)

    def __init__(self, controller: QuickTimeController, parent=None):
        super().__init__(parent)

        self._controller = controller
        self._commands: queue.Queue = queue.Queue()
        self._done = 0

    def submit(self, name: str, *args):
        self._commands.put((name, args))

    def stop(self):
        self._commands.put(None)
        self.wait(4000)

    def _execute(self, name: str, args: tuple):
        try:
            getattr(self._controller, name)(*args)

        except Exception as error:
            self.command_failed.emit(str(error))

        finally:
            self._done += 1

    def run(self):
        next_poll = 0.0

        while True:
            timeout = max(0.0, next_poll - time.monotonic())

            try:
                command = self._commands.get(timeout=timeout)

            except queue.Empty:
                command = False  # 폴링 시각

            if command is None:
                return

            started = time.monotonic()

            if command is not False:
                self._execute(*command)

            try:
                state = self._controller.get_state()

            except Exception:
                state = QuickTimeState("error", sampled_at=time.monotonic())

            # 명령이 더 대기 중이면 오래된 상태는 보내지 않고 바로 처리
            if self._commands.empty():
                self.state_changed.emit(
                    replace(state, commands_done=self._done)
                )

            next_poll = started + POLL_INTERVAL
