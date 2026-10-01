# 타임라인 JSON 데이터 읽기
# - 씬 데이터 파일 읽기 -> "00:04:21" 같은 시간을 초로 변환
# - name = null 처리
# - 데이터 검증
# - Scene 데이터 구조 정의

import json
from dataclasses import dataclass


def timecode_to_seconds(timecode: str) -> float:
    """
    'HH:MM:SS' 또는 'HH:MM:SS.sss' 형식을 초 단위로 변환한다.

    예:
    00:04:01 -> 241초
    """

    if not isinstance(timecode, str):
        raise ValueError(f"시간값은 문자열이어야 합니다: {timecode}")

    parts = timecode.strip().split(":")

    if len(parts) != 3:
        raise ValueError(
            f"시간 형식이 올바르지 않습니다: {timecode} "
            "(HH:MM:SS 형식을 사용하세요)"
        )

    try:
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])

    except ValueError:
        raise ValueError(
            f"시간 형식이 올바르지 않습니다: {timecode}"
        )

    if hours < 0:
        raise ValueError("시간(hour)은 음수가 될 수 없습니다.")

    if not 0 <= minutes < 60:
        raise ValueError(
            f"분(minute)은 0~59여야 합니다: {timecode}"
        )

    if not 0 <= seconds < 60:
        raise ValueError(
            f"초(second)는 0~59여야 합니다: {timecode}"
        )

    return (
        hours * 3600
        + minutes * 60
        + seconds
    )


@dataclass(frozen=True)
class Scene:
    name: str | None

    # 원본 문자열
    start: str
    end: str

    # 프로그램 내부 계산용
    start_seconds: float
    end_seconds: float


def load_scenes(path: str) -> list[Scene]:
    """
    JSON 씬 데이터 파일을 읽는다.
    """

    with open(path, "r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError(
            "씬 데이터의 최상위 구조는 배열이어야 합니다."
        )

    scenes = []

    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(
                f"{index + 1}번째 씬의 형식이 올바르지 않습니다."
            )

        if "start" not in item:
            raise ValueError(
                f"{index + 1}번째 씬에 start가 없습니다."
            )

        if "end" not in item:
            raise ValueError(
                f"{index + 1}번째 씬에 end가 없습니다."
            )

        start = item["start"]
        end = item["end"]

        start_seconds = timecode_to_seconds(start)
        end_seconds = timecode_to_seconds(end)

        if end_seconds <= start_seconds:
            raise ValueError(
                f"{index + 1}번째 씬의 end가 "
                "start보다 뒤에 있어야 합니다."
            )

        name = item.get("name")

        if name is not None:
            # 빈 문자열은 name 없음으로 취급
            name = str(name).strip() or None

        scenes.append(
            Scene(
                name=name,
                start=start,
                end=end,
                start_seconds=start_seconds,
                end_seconds=end_seconds,
            )
        )

    # 시간 순으로 정렬
    scenes.sort(
        key=lambda scene: scene.start_seconds
    )

    return scenes