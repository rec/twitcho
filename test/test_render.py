from pathlib import Path

from scripts import render
from scripts.render import (
    Media,
    RenderConfig,
    RenderPlan,
    Scene,
    TitleEvent,
    Transition,
    build_plan,
    fade_duration,
    ffmpeg_command,
    filter_graph,
    stretch_scenes_for_transitions,
    timeline_duration,
)


def test_fade_duration_uses_half_longer_video() -> None:
    first = Scene(media=Media(path=Path("a.mp4"), duration=20), duration=20)
    second = Scene(media=Media(path=Path("b.mp4"), duration=10), duration=10)

    assert fade_duration(first, second) == 10


def test_fade_duration_uses_half_longer_media_for_video_and_still() -> None:
    video = Scene(media=Media(path=Path("a.mp4"), duration=20), duration=20)
    still = Scene(
        media=Media(path=Path("b.png"), duration=30, is_still=True), duration=30
    )

    assert fade_duration(video, still) == 15
    assert fade_duration(still, video) == 15


def test_fade_duration_uses_half_longer_still_for_two_stills() -> None:
    first = Scene(
        media=Media(path=Path("a.png"), duration=30, is_still=True), duration=30
    )
    second = Scene(
        media=Media(path=Path("b.png"), duration=8, is_still=True), duration=8
    )

    assert fade_duration(first, second) == 15


def test_build_plan_is_seeded_and_avoids_immediate_repeats() -> None:
    config = RenderConfig(
        inputs=[Path("a.mp4"), Path("b.mp4")],
        output=Path("out.mp4"),
        duration=40,
        seed=1,
    )
    media = [
        Media(path=Path("a.mp4"), duration=10),
        Media(path=Path("b.mp4"), duration=10),
    ]

    plan = build_plan(config, media)
    paths = [scene.media.path for scene in plan.scenes[1:]]

    for first, second in zip(paths, paths[1:], strict=False):
        assert first != second
    for index, transition in enumerate(plan.transitions):
        assert plan.scenes[index].duration >= transition.duration
        assert plan.scenes[index + 1].duration >= transition.duration
    assert timeline_duration(plan.scenes, plan.transitions) >= 40


def test_stretch_scenes_loops_short_media_for_adjacent_fades() -> None:
    scenes = [
        Scene(media=Media(path=Path("a.mp4"), duration=30), duration=30),
        Scene(media=Media(path=Path("b.mp4"), duration=8), duration=8),
        Scene(media=Media(path=Path("c.mp4"), duration=20), duration=20),
    ]
    transitions = [Transition(duration=15), Transition(duration=10)]

    stretch_scenes_for_transitions(scenes, transitions)

    assert scenes[0].duration == 30
    assert scenes[1].duration == 25
    assert scenes[2].duration == 20


def test_build_plan_can_insert_title_events_without_changing_base_sequence() -> None:
    config = RenderConfig(
        inputs=[Path("a.mp4")],
        output=Path("out.mp4"),
        duration=40,
        seed=1,
        title_card=Path("title.png"),
        title_probability=1,
    )
    media = [Media(path=Path("a.mp4"), duration=10)]

    plan = build_plan(config, media)

    assert plan.title_events
    assert [scene.media.path for scene in plan.scenes[:3]] == [
        Path("__black__"),
        Path("title.png"),
        Path("__black__"),
    ]


def test_ffmpeg_command_uses_inputs_xfade_and_title_overlay() -> None:
    config = RenderConfig(
        inputs=[Path("a.mp4"), Path("b.png")],
        output=Path("out.mp4"),
        duration=20,
        seed=1,
        title_card=Path("title.png"),
        title_probability=1,
    )
    plan = RenderPlan(
        scenes=[
            Scene(
                media=Media(path=Path("__black__"), duration=4, is_still=True),
                duration=4,
            ),
            Scene(media=Media(path=Path("a.mp4"), duration=10), duration=10),
            Scene(
                media=Media(path=Path("b.png"), duration=30, is_still=True),
                duration=30,
            ),
        ],
        transitions=[Transition(duration=2), Transition(duration=5)],
        title_events=[TitleEvent(start=8, duration=8)],
    )

    command = ffmpeg_command(config, plan)
    graph = command[command.index("-filter_complex") + 1]

    assert "a.mp4" in command
    assert "b.png" in command
    assert "title.png" in command
    assert "-stream_loop" in command
    assert "-loop" in command
    assert "xfade=transition=fade" in graph
    assert "overlay=(W-w)/2:(H-h)/2:eof_action=pass" in graph
    assert command[command.index("-t", command.index("-movflags")) + 1] == "20.000000"
    assert command[-1] == "out.mp4"


def test_filter_graph_maps_final_label() -> None:
    config = RenderConfig(
        inputs=[Path("a.mp4")],
        output=Path("out.mp4"),
        duration=5,
        seed=1,
    )
    plan = build_plan(config, [Media(path=Path("a.mp4"), duration=10)])

    graph, output = filter_graph(config, plan)

    assert "scale=640:360" in graph
    assert output.startswith("[")
    assert output.endswith("]")


def test_probe_media_uses_still_duration_for_images(
    monkeypatch, tmp_path: Path
) -> None:
    image = tmp_path / "still.png"
    image.touch()
    monkeypatch.setattr(render, "probe_duration", lambda path: 999)

    media = render.probe_media(image, 30)

    assert media.duration == 30
    assert media.is_still
