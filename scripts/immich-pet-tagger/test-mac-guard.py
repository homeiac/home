#!/usr/bin/env python3
"""Verify operator-approved warning policy without launching inference models."""
from unittest.mock import patch
import mac_burst_guard as guard

for level,expected in ((1,True),(2,True),(4,False),(8,False),(0,False)):
    with patch.object(guard.subprocess,'check_output',return_value=str(level)):
        assert guard.can_run(starting=True)==expected
        assert guard.can_run()==expected
with patch.object(guard.subprocess,'check_output',side_effect=RuntimeError('probe failure')):
    assert not guard.can_run(starting=True)
print('Mac warning permits work; critical/unknown pressure and probe failures refuse extras')
