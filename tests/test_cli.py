import json

from typo_guard.cli import main


def test_cli_text_output_and_finding_exit_code(tmp_path, capsys):
    sample = tmp_path / "sample.py"
    sample.write_text("recieved_data = 1\n", encoding="utf-8")
    assert main(["lint", str(sample)]) == 1
    output = capsys.readouterr().out
    assert "TG001" in output
    assert "recieved" in output


def test_cli_clean_exit_code(tmp_path, capsys):
    sample = tmp_path / "clean.py"
    sample.write_text("received_data = 1\n", encoding="utf-8")
    assert main(["lint", str(sample)]) == 0
    assert "Found 0 possible typo(s)." in capsys.readouterr().out


def test_cli_json_output(tmp_path, capsys):
    sample = tmp_path / "sample.py"
    sample.write_text("innitial_value = 1\n", encoding="utf-8")
    assert main(["lint", str(sample), "--format", "json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["word"] == "innitial"
    assert payload[0]["identifier"] == "innitial_value"


def test_cli_inline_allow_word(tmp_path, capsys):
    sample = tmp_path / "sample.py"
    sample.write_text("frobnicator_value = 1\n", encoding="utf-8")
    assert main(["lint", str(sample), "--allow", "frobnicator"]) == 0
    capsys.readouterr()


def test_cli_allowlist_file(tmp_path, capsys):
    sample = tmp_path / "sample.py"
    sample.write_text("frobnicator_value = 1\n", encoding="utf-8")
    allowlist = tmp_path / "words.txt"
    allowlist.write_text("# project vocabulary\nfrobnicator\n", encoding="utf-8")
    assert main(["lint", str(sample), "--allowlist", str(allowlist)]) == 0
    capsys.readouterr()


def test_cli_missing_path_is_usage_error(capsys):
    assert main(["lint", "does-not-exist.py"]) == 2
    assert "path not found" in capsys.readouterr().err


def test_cli_syntax_error_is_usage_error(tmp_path, capsys):
    sample = tmp_path / "broken.py"
    sample.write_text("def broken(:\n", encoding="utf-8")
    assert main(["lint", str(sample)]) == 2
    assert "invalid syntax" in capsys.readouterr().err
