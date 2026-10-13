import logging
import unittest

from mikasa.__main__ import _shutdown


class ShutdownTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.log = logging.getLogger('test.shutdown')
        self.calls = []

    def make(self, name, fail=False):
        async def step():
            self.calls.append(name)
            if fail:
                raise RuntimeError(name)
        return step()

    async def test_runs_all_steps_in_order(self):
        await _shutdown(self.log, [('a', self.make('a')), ('b', self.make('b'))])
        self.assertEqual(self.calls, ['a', 'b'])

    async def test_continues_after_failure(self):
        await _shutdown(self.log, [
            ('a', self.make('a')),
            ('b', self.make('b', fail=True)),
            ('c', self.make('c')),
        ])
        self.assertEqual(self.calls, ['a', 'b', 'c'])
