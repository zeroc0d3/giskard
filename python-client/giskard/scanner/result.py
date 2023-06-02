from collections import defaultdict, Counter

import pandas as pd

from giskard.utils.analytics_collector import analytics, anonymize


class ScanResult:
    def __init__(self, issues):
        self.issues = issues

    def has_issues(self):
        return len(self.issues) > 0

    def __repr__(self):
        if not self.has_issues():
            return "<PerformanceScanResult (no issues)>"

        return f"<PerformanceScanResult ({len(self.issues)} issue{'s' if len(self.issues) > 1 else ''})>"

    def _ipython_display_(self):
        from IPython.core.display import display_html

        html = self._repr_html_()
        display_html(html, raw=True)

    def _repr_html_(self):
        from jinja2 import Environment, PackageLoader, select_autoescape
        from .visualization.custom_jinja import pluralize, format_metric
        from html import escape

        env = Environment(
            loader=PackageLoader("giskard.scanner", "templates"),
            autoescape=select_autoescape(),
        )
        env.filters["pluralize"] = pluralize
        env.filters["format_metric"] = format_metric

        tpl = env.get_template("scan_results.html")

        issues_by_group = defaultdict(list)
        for issue in self.issues:
            issues_by_group[issue.group].append(issue)

        html = tpl.render(
            issues=self.issues,
            issues_by_group=issues_by_group,
            num_major_issues={
                group: len([i for i in issues if i.is_major]) for group, issues in issues_by_group.items()
            },
            num_medium_issues={
                group: len([i for i in issues if not i.is_major]) for group, issues in issues_by_group.items()
            },
        )

        escaped = escape(html)
        uid = id(self)

        from pathlib import Path

        with Path(__file__).parent.joinpath("templates", "static", "external.js").open("r") as f:
            js_lib = f.read()

        return f'''<iframe id="scan-{uid}" srcdoc="{escaped}" style="width: 100%; border: none;" class="gsk-scan"></iframe>
<script>
{js_lib}
(function(){{iFrameResize({{ checkOrigin: false }}, '#scan-{uid}');}})();
</script>
'''

    def to_html(self, filename=None):
        html = self._repr_html_()

        if not filename:
            return html

        with open(filename, "w") as f:
            f.write(html)

    def to_dataframe(self):
        df = pd.DataFrame(
            [
                {
                    "domain": issue.domain,
                    "metric": issue.metric,
                    "deviation": issue.deviation,
                    "description": issue.description,
                }
                for issue in self.issues
            ]
        )
        return df

    def generate_tests(self, with_names=False):
        tests = sum([issue.generate_tests(with_names=with_names) for issue in self.issues], [])
        return tests

    def generate_test_suite(self, name=None):
        from giskard import Suite

        suite = Suite(name=name or "Test suite (generated by automatic scan)")
        for test, test_name in self.generate_tests(with_names=True):
            suite.add_test(test, test_name)

        self._track_suite(suite, name)
        return suite

    def _track_suite(self, suite, name):
        tests_cnt = {}
        if suite.tests:
            for t in suite.tests:
                try:
                    name = t.giskard_test.meta.full_name
                    if name not in tests_cnt:
                        tests_cnt[name] = 1
                    else:
                        tests_cnt[name] += 1
                except:  # noqa
                    pass
        analytics.track(
            "scan:generate_test_suite",
            {
                "suite_name": anonymize(name),
                "tests_cnt": len(suite.tests),
                **tests_cnt
            },
        )
