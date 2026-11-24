"""Check the AC-only assertion and supervisor cleanup without starting a model."""
import unittest
from unittest.mock import Mock, patch
import supervisor


class SupervisorTest(unittest.TestCase):
    def test_assertion_is_ac_only_and_tied_to_model(self):
        with patch.object(supervisor.subprocess, 'Popen') as popen:
            supervisor.keep_awake(Mock(pid=123))
        popen.assert_called_once_with(['/usr/bin/caffeinate', '-s', '-w', '123'])

    def test_disabled_policy_stops_assertion_and_model(self):
        server, awake, tunnel = Mock(pid=123), Mock(), Mock()
        server.poll.return_value = None
        awake.poll.return_value = None
        tunnel.poll.return_value = None
        with patch.object(supervisor, 'policy', side_effect=[(4, 4), (0, 0)]), \
             patch.object(supervisor.time, 'monotonic', side_effect=[0, 0, 61, 61]), \
             patch.object(supervisor.time, 'sleep', side_effect=[None, SystemExit]), \
             patch.object(supervisor, 'start', return_value=server), \
             patch.object(supervisor, 'keep_awake', return_value=awake) as assertion, \
             patch.object(supervisor.urllib.request, 'urlopen', side_effect=OSError), \
             patch.object(supervisor, 'stop') as stop:
            with self.assertRaises(SystemExit):
                supervisor.main()
        assertion.assert_called_once_with(server)
        self.assertIn(unittest.mock.call(server), stop.call_args_list)
        self.assertIn(unittest.mock.call(awake), stop.call_args_list)


if __name__ == '__main__':
    unittest.main()
