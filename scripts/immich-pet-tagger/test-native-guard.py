"""Check capacity hysteresis at the actual safety boundaries."""
from native_guard import permitted
assert permitted(2018,63.6,True)
assert not permitted(933,42,True)
assert not permitted(2000,65,True)
assert permitted(700,67,False)
assert not permitted(511,50,False)
assert not permitted(2000,68,False)
print('Native worker memory and thermal hysteresis checks passed')
