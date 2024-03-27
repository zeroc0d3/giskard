import os
import tempfile
from pathlib import Path
from unittest.mock import Mock

from giskard.scanner.issues import Issue, IssueLevel, Robustness
from giskard.scanner.report import ScanReport


def test_scan_report_exports_to_html():
    model = Mock()
    dataset = Mock()

    report = ScanReport(issues=[Issue(model, dataset, Robustness, IssueLevel.MAJOR)])

    # HTML report
    html = report.to_html()

    assert html is not None
    assert isinstance(html, str)
    assert html.startswith("<!doctype html>")
    assert html.strip().endswith("</html>")

    # Save to a file
    with tempfile.TemporaryDirectory() as tmpdir:
        dest = Path(tmpdir).joinpath("report.html")
        report.to_html(dest)

        assert dest.exists()
        assert dest.is_file()
        assert dest.read_text().startswith("<!doctype html>")
        assert dest.read_text().strip().endswith("</html>")


def test_scan_report_exports_to_markdown():
    model = Mock()
    dataset = Mock()

    report = ScanReport(issues=[Issue(model, dataset, Robustness, IssueLevel.MAJOR)])

    # Markdown report
    markdown = report.to_markdown()

    assert markdown is not None
    assert isinstance(markdown, str)

    # Save to a file
    with tempfile.TemporaryDirectory() as tmpdir:
        dest = Path(tmpdir).joinpath("report.md")
        report.to_markdown(dest)

        assert dest.exists()
        assert dest.is_file()
        assert dest.read_text() == markdown


def test_scan_report_exports_to_doc():
    model = Mock()
    dataset = Mock()

    report = ScanReport(issues=[Issue(model, dataset, Robustness, IssueLevel.MAJOR)])

    # Markdown report
    with tempfile.TemporaryDirectory() as tmpdir:
        report.to_doc(dir=tmpdir)
        assert "Robustness.md" in os.listdir(tmpdir)
