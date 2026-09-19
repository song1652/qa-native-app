"""Compatibility alias for the observability runtime.

Existing pytest hooks and tests import tests._observability and monkeypatch
its module globals. Aliasing the module preserves that behavior while the runtime
lives in a focused package.
"""

import sys

from tests.observability import runtime as _runtime

sys.modules[__name__] = _runtime
