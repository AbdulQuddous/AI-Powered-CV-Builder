"""Ensure an accidentally unmocked AI call cannot reach a provider during tests."""
from contextlib import ExitStack
from unittest.mock import patch

from django.test.runner import DiscoverRunner


class OfflineAITestRunner(DiscoverRunner):
    def run_tests(self, *args, **kwargs):
        with ExitStack() as stack:
            for transport in ('httpx.Client.send', 'httpx.AsyncClient.send'):
                stack.enter_context(patch(transport, side_effect=RuntimeError(
                    'External AI transport is disabled in tests. Mock the provider.')))
            return super().run_tests(*args, **kwargs)
