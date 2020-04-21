"""
=========================================================================
HypothesisTest.py
=========================================================================
Hypothesis test with cache
Now with Latencies!!

Author : Xiaoyu Yan (xy97), Eric Tang (et396)
Date   : 25 December 2019  Merry Christmas!! UWU
"""

import random
import hypothesis
from hypothesis import strategies as st

from pymtl3 import *

# cifer specific memory req/resp msg
from mem_ifcs.MemMsg import MemMsgType
from mem_ifcs.MemMsg import mk_mem_msg as mk_cache_msg
from mem_ifcs.MemMsg import mk_mem_msg

from constants.constants import *
from test.sim_utils    import rand_mem
from ..BlockingCacheFL import ModelCache

obw  = 8   # Short name for opaque bitwidth
abw  = 32  # Short name for addr bitwidth
dbw  = 32  # Short name for data bitwidth

@st.composite
def gen_reqs( draw, addr_min, addr_max ):
  addr = draw( st.integers(addr_min, addr_max), label="addr" )
  type_ranges = draw( st.integers( 0, 2) )
  if type_ranges == 0:
    type_ = draw( st.sampled_from([
      MemMsgType.READ,
      MemMsgType.WRITE,
      MemMsgType.AMO_ADD,
      MemMsgType.AMO_AND,
      MemMsgType.AMO_OR,
      MemMsgType.AMO_SWAP,
      MemMsgType.AMO_MIN,
      MemMsgType.AMO_MINU,
      MemMsgType.AMO_MAX,
      MemMsgType.AMO_MAXU,
      MemMsgType.AMO_XOR,
    ]), label='type')
  elif type_ranges == 1:
    type_ = draw( st.sampled_from([
      MemMsgType.READ,
      MemMsgType.WRITE,
      MemMsgType.INV,
      MemMsgType.FLUSH,
    ]), label="type" )
  else:
    type_ = draw( st.sampled_from([
      MemMsgType.READ,
      MemMsgType.WRITE,
      MemMsgType.AMO_ADD,
      MemMsgType.AMO_AND,
      MemMsgType.AMO_OR,
      MemMsgType.AMO_SWAP,
      MemMsgType.AMO_MIN,
      MemMsgType.AMO_MINU,
      MemMsgType.AMO_MAX,
      MemMsgType.AMO_MAXU,
      MemMsgType.AMO_XOR,
      MemMsgType.INV,
      MemMsgType.FLUSH,
    ]), label="type" )
  if type_ == MemMsgType.INV or type_ == MemMsgType.FLUSH:
    addr = Bits32(0)
    len_ = 0
    data = 0
  else:
    data = draw( st.integers(0, 0xffffffff), label="data" )
    if type_ >= MemMsgType.AMO_ADD and type_ <= MemMsgType.AMO_XOR:
      addr = addr & Bits32(0xfffffffc)
      len_ = 0
    else:
      len_ = draw( st.integers(0, 2), label="len" )
      if len_ == 0:
        addr = addr & Bits32(0xfffffffc)
      elif len_ == 1:
        addr = addr & Bits32(0xffffffff)
      elif len_ == 2:
        addr = addr & Bits32(0xfffffffe)
      else:
        addr = addr & Bits32(0xfffffffc)

  return (addr, type_, data, len_)

max_examples = 30
hypothesis_max_cycles = 10000

class HypothesisTests:
  def hypothesis_test_harness( s, associativity, clw, num_blocks,
                               req, stall_prob, latency, src_delay, sink_delay,
                               dump_vcd, test_verilog, max_cycles, dump_vtb ):
    cacheSize = (clw * associativity * num_blocks) // 8
    addr_min = 0
    addr_max = int( cacheSize // 4 * 2 * associativity )
    mem = rand_mem(addr_min, addr_max)
    CacheReqType, CacheRespType = mk_cache_msg(obw, abw, dbw, has_wr_mask=False)
    MemReqType, MemRespType = mk_mem_msg(obw, abw, clw)
    # FL Model to generate expected transactions
    model = ModelCache( cacheSize, associativity, 0, CacheReqType, CacheRespType,
                        MemReqType, MemRespType, mem )
    # Grab list of generated transactions
    reqs_lst = req.draw(
      st.lists( gen_reqs( addr_min, addr_max ), min_size=30, max_size=200 ),
      label= "requests"
    )
    for i in range(len(reqs_lst)):
      addr, type_, data, len_ = reqs_lst[i]
      if type_ == MemMsgType.WRITE:
        model.write(addr, data, i, len_)
      elif type_ == MemMsgType.READ:
        model.read(addr, i, len_)
      elif type_ == MemMsgType.WRITE_INIT:
        model.init(addr, data, i, len_)
      elif type_ >= MemMsgType.AMO_ADD and type_ <= MemMsgType.AMO_XOR:
        model.amo(addr, data, i, type_)
      elif type_ == MemMsgType.INV:
        model.invalidate(i)
      elif type_ == MemMsgType.FLUSH:
        model.flush(i)
      else:
        assert False, "FL model: Undefined transaction type"
    msgs = model.get_transactions() # Get FL response
    # Prepare RTL test harness
    s.run_test( msgs, mem, CacheReqType, CacheRespType, MemReqType, MemRespType,
                associativity, cacheSize, stall_prob, latency, src_delay, sink_delay,
                dump_vcd, test_verilog, hypothesis_max_cycles, 1, dump_vtb )

  @hypothesis.settings( deadline = None, max_examples=max_examples )
  @hypothesis.given(
    clw          = st.sampled_from([64,128,256]),
    block_order  = st.integers( 1, 7 ),
    req          = st.data(),
    stall_prob   = st.integers( 0 ),
    latency      = st.integers( 1, 5 ),
    src_delay    = st.integers( 0, 5 ),
    sink_delay   = st.integers( 0, 5 )
  )
  def test_hypothesis_2way( s, clw, block_order, req, stall_prob,
                            latency, src_delay, sink_delay, dump_vcd,
                            test_verilog, max_cycles, dump_vtb ):
    num_blocks = 2**block_order
    s.hypothesis_test_harness( 2, clw, num_blocks, req, stall_prob,
                               latency, src_delay, sink_delay, dump_vcd,
                               test_verilog, max_cycles, dump_vtb )

  @hypothesis.settings( deadline = None, max_examples=max_examples )
  @hypothesis.given(
    clw          = st.sampled_from([64,128,256]),
    block_order  = st.integers( 1, 7 ), # order of number of blocks based 2
    req          = st.data(),
    stall_prob   = st.integers( 0 ),
    latency      = st.integers( 1, 5 ),
    src_delay    = st.integers( 0, 5 ),
    sink_delay   = st.integers( 0, 5 )
  )
  def test_hypothesis_dmapped( s, clw, block_order, req, stall_prob,
                               latency, src_delay, sink_delay, dump_vcd,
                               test_verilog, max_cycles, dump_vtb ):
    num_blocks = 2**block_order
    s.hypothesis_test_harness( 1, clw, num_blocks, req, stall_prob,
                               latency, src_delay, sink_delay, dump_vcd,
                               test_verilog, max_cycles, dump_vtb )

  @hypothesis.settings( deadline = None, max_examples=max_examples )
  @hypothesis.given(
    req          = st.data(),
    latency      = st.integers( 1, 2 ),
    src_delay    = st.integers( 0, 2 ),
    sink_delay   = st.integers( 0, 2 )
  )
  def test_hypothesis_2way_stress( s,  req, latency, src_delay,
                                   sink_delay, dump_vcd, test_verilog, max_cycles, dump_vtb ):
    s.hypothesis_test_harness( 2, 128, 2,  req, 0,
                               latency, src_delay, sink_delay,
                               dump_vcd, test_verilog, max_cycles, dump_vtb )

  @hypothesis.settings( deadline = None, max_examples=max_examples )
  @hypothesis.given(
    req          = st.data(),
    latency      = st.integers( 1, 2 ),
    src_delay    = st.integers( 0, 2 ),
    sink_delay   = st.integers( 0, 2 )
  )
  def test_hypothesis_dmapped_stress( s, req, latency,
                                      src_delay, sink_delay, dump_vcd,
                                      test_verilog, max_cycles, dump_vtb ):
    s.hypothesis_test_harness( 1, 128, 2, req, 0,
                               latency, src_delay, sink_delay, dump_vcd,
                               test_verilog, max_cycles, dump_vtb )
