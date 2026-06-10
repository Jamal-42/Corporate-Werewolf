import json

from human_agent import human_input_queue_path, pop_human_input


def test_human_input_queue_path_is_scoped_to_run_and_seat(tmp_path):
    path = human_input_queue_path("game_6p_20260607_120000", 3, str(tmp_path))

    assert path == tmp_path / "game_6p_20260607_120000_seat3.jsonl"


def test_pop_human_input_consumes_first_valid_line(tmp_path):
    path = tmp_path / "game_6p_20260607_120000_seat3.jsonl"
    path.write_text(
        "\n".join([
            json.dumps({"text": "第一条发言"}),
            json.dumps({"text": "第二条发言"}),
        ]) + "\n",
        encoding="utf-8",
    )

    assert pop_human_input(path) == "第一条发言"
    assert json.loads(path.read_text(encoding="utf-8").strip()) == {"text": "第二条发言"}
