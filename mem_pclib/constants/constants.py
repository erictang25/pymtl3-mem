"""
#=========================================================================
# constants.py
#=========================================================================
Important constants for the cache

Author : Xiaoyu Yan (xy97), Eric Tang (et396)
Date   : 10 February 2020
"""

from pymtl3 import *
from pymtl3.stdlib.ifcs.MemMsg import MemMsgType

# General

wr = y             = b1(1)
rd = n = x         = b1(0)

# Write masks

data_array_double_mask = 0xff
data_array_word_mask   = 0xf
data_array_2byte_mask  = 0x3
data_array_byte_mask   = 0x1

# Shorthands for MemMsgType

READ     = b4(MemMsgType.READ)
WRITE    = b4(MemMsgType.WRITE)
INIT     = b4(MemMsgType.WRITE_INIT)
AMO      = b4(3)
AMO_ADD  = b4(MemMsgType.AMO_ADD)
AMO_AND  = b4(MemMsgType.AMO_AND)
AMO_OR   = b4(MemMsgType.AMO_OR)
AMO_SWAP = b4(MemMsgType.AMO_SWAP)
AMO_MIN  = b4(MemMsgType.AMO_MIN)
AMO_MINU = b4(MemMsgType.AMO_MINU)
AMO_MAX  = b4(MemMsgType.AMO_MAX)
AMO_MAXU = b4(MemMsgType.AMO_MAXU)
AMO_XOR  = b4(MemMsgType.AMO_XOR)
