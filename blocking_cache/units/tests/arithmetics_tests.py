"""
=========================================================================
arithmetrics_tests.py
=========================================================================
Tests some cache dpath moduels

Author : Xiaoyu Yan (xy97), Eric Tang (et396)
Date   : 26 March 2020
"""

from pymtl3 import *
from pymtl3.stdlib.test.test_utils import run_test_vector_sim
from mem_ifcs.MemMsg import MemMsgType, mk_mem_msg
# from constants.constants import *
from blocking_cache.CacheDerivedParams  import CacheDerivedParams

from ..arithmetics import *

obw  = 8   # Short name for opaque bitwidth
abw  = 32  # Short name for addr bitwidth

num_bytes = 32
associativity = 1

def test_replicator_dbw32_clw128( dump_vcd, test_verilog, max_cycles ):
  test_vectors = [ 
    ( "in_",      "amo","len_","out*" ),
    [  0xabcd1234, 0,    0,     0xabcd1234abcd1234abcd1234abcd1234 ],
    [  0xabcd1234, 0,    1,     0x34343434343434343434343434343434 ],
    [  0xabcd1234, 0,    2,     0x12341234123412341234123412341234 ],
    [  0xabcd1234, 0,    3,     0x000000000000000000000000abcd1234 ],
    [  0xabcd1234, 1,    0,     0x000000000000000000000000abcd1234 ],
  ] 
  CacheReqType, CacheRespType = mk_mem_msg(obw, abw, 32)
  MemReqType, MemRespType = mk_mem_msg(obw, abw, 128)
  cache_params = CacheDerivedParams( CacheReqType, CacheRespType, MemReqType,
      MemRespType, num_bytes, associativity )
  run_test_vector_sim( DataReplicator(cache_params), test_vectors, dump_vcd, test_verilog )

def test_replicator_dbw128_clw128( dump_vcd, test_verilog, max_cycles ):
  test_vectors = [ 
    ( "in_",                              "amo","len_","out*" ),
    [  0x0123456789abcdeffedcba9876543210, 0,    0,     0x0123456789abcdeffedcba9876543210 ],
    [  0x0123456789abcdeffedcba9876543210, 0,    1,     0x10101010101010101010101010101010 ],
    [  0x0123456789abcdeffedcba9876543210, 0,    2,     0x32103210321032103210321032103210 ],
    [  0x0123456789abcdeffedcba9876543210, 0,    3,     0x0123456789abcdeffedcba9876543210 ],
    [  0x0123456789abcdeffedcba9876543210, 0,    4,     0x76543210765432107654321076543210 ],
    [  0x0123456789abcdeffedcba9876543210, 0,    8,     0xfedcba9876543210fedcba9876543210 ],
    [  0x0123456789abcdeffedcba9876543210, 1,    8,     0x0123456789abcdeffedcba9876543210 ],
  ] 
  CacheReqType, CacheRespType = mk_mem_msg(obw, abw, 128)
  MemReqType, MemRespType = mk_mem_msg(obw, abw, 128)
  cache_params = CacheDerivedParams( CacheReqType, CacheRespType, MemReqType,
      MemRespType, num_bytes, associativity )
  run_test_vector_sim( DataReplicator(cache_params), test_vectors, dump_vcd, test_verilog )

def test_WriteBitEnGen( dump_vcd, test_verilog, max_cycles ):
  test_vectors = [ 
    ( 'offset', 'len_', 'out*' ),
    [  0b0000,   1,      0xff                               ],
    [  0b0001,   1,      0xff00                             ],
    [  0b0010,   1,      0xff0000                           ],
    [  0b0011,   1,      0xff000000                         ],
    [  0b0000,   2,      0xffff                             ],
    [  0b0010,   2,      0xffff0000                         ],
    [  0b0100,   2,      0xffff00000000                     ],
    [  0b0110,   2,      0xffff000000000000                 ],
    [  0b1000,   2,      0xffff0000000000000000             ],
    [  0b0000,   4,      0xffffffff                         ],
    [  0b0100,   4,      0xffffffff00000000                 ],
    [  0b1000,   4,      0xffffffff0000000000000000         ],
    [  0b1100,   4,      0xffffffff000000000000000000000000 ],
    [  0b0000,   8,      0x0000000000000000ffffffffffffffff ],
    [  0b1000,   8,      0xffffffffffffffff0000000000000000 ],
    [  0b0000,   0,      0xffffffffffffffffffffffffffffffff ],
  ]
  CacheReqType, CacheRespType = mk_mem_msg(obw, abw, 128)
  MemReqType, MemRespType = mk_mem_msg(obw, abw, 128)
  cache_params = CacheDerivedParams( CacheReqType, CacheRespType, MemReqType,
      MemRespType, num_bytes, associativity )
  run_test_vector_sim( WriteBitEnGen(cache_params), test_vectors, dump_vcd,
   test_verilog, max_cycles )
