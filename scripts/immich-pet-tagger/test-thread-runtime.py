#!/usr/bin/env python3
"""Verify the pinned Ultralytics selector respects each explicit CPU thread setting."""
import torch
from ultralytics.utils import torch_utils

for threads in (2,4,8,16):
    torch_utils.NUM_THREADS=threads
    torch.set_num_threads(threads)
    assert torch_utils.select_device('cpu',verbose=False).type=='cpu'
    assert torch.get_num_threads()==threads
print('Pinned PyTorch/Ultralytics selector verified at 2, 4, 8 and 16 CPU threads')
