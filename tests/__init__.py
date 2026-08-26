"""Shared test support for the qacompanion suite."""

import io
from unittest import mock


def quiet_stdout(testcase):
    """Redirect sys.stdout into a StringIO for the rest of the test.

    Regression guard for the stdout-leak defect (mails #93/#98, TASK #112):
    in-process main() drives printed parent-CLI lines like 'recorded new
    case #N times_seen=1' straight into the unittest console because the
    capture-path helpers redirected stderr only. Call at the top of setUp;
    returns the buffer so tests may assert on what main() printed.
    """
    buf = io.StringIO()
    patcher = mock.patch("sys.stdout", new=buf)
    patcher.start()
    testcase.addCleanup(patcher.stop)
    return buf
