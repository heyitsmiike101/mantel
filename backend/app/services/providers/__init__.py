"""Calendar providers.

Import `base` for the shared types and `registry` for the factory. Nothing is
re-exported here on purpose: `google_api` imports `base`, so a package that
pulled its own submodules in at import time would close a cycle.
"""
