from typer.testing import CliRunner

from xiaohongshureport.cli import app


def test_cli_exposes_required_commands() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "login" in result.stdout
    assert "discover" in result.stdout
    assert "crawl-account" in result.stdout
    assert "report" in result.stdout
    assert "feishu" in result.stdout
