"""
=========================================================================
 BlockingCacheDpathRTL.py
=========================================================================
Parameterizable Pipelined Blocking Cache Datapath

Author : Xiaoyu Yan (xy97), Eric Tang (et396)
Date   : 20 February 2020
"""

from pymtl3                         import *
from pymtl3.stdlib.rtl.arithmetics  import Mux
from pymtl3.stdlib.rtl.RegisterFile import RegisterFile
from pymtl3.stdlib.rtl.registers    import RegEnRst, RegEn
from pymtl3.stdlib.connects.connect_bits2bitstruct import *

from constants.constants  import *
from sram.SramPRTL        import SramPRTL

from .constants                import *
from .units.DirtyLineDetector  import DirtyLineDetector
from .units.MSHR_v1            import MSHR
from .units.muxes              import *
from .units.arithmetics        import (
  Indexer, Comparator, CacheDataReplicator, OffsetLenSelector, 
  TagArrayRDataProcessUnit
  )
from .units.registers          import (
  DpathPipelineRegM0, DpathPipelineReg, ReplacementBitsReg
)
from .units.UpdateTagArrayUnit import UpdateTagArrayUnit
from .units.StallEngine        import StallEngine

class BlockingCacheDpathRTL (Component):

  def construct( s, p ):

    #--------------------------------------------------------------------
    # Interface
    #--------------------------------------------------------------------

    s.cachereq_Y   = InPort ( p.CacheReqType  )
    s.cacheresp_M2 = OutPort( p.CacheRespType )
    s.memresp_Y    = InPort ( p.MemRespType   )
    s.memreq_M2    = OutPort( p.MemReqType    )
    s.ctrl         = InPort ( p.StructCtrl    ) # Control signals from Ctrl unit
    s.status       = OutPort( p.StructStatus  ) # Status signals to Ctrl unit

    #--------------------------------------------------------------------
    # M0 Stage
    #--------------------------------------------------------------------

    # Pipeline Registers
    s.pipeline_reg_M0 = DpathPipelineRegM0( p )(
      in_ = s.memresp_Y,
      en  = s.ctrl.reg_en_M0,
    )

    # Forward declaration: output from MSHR
    s.MSHR_dealloc_out = Wire( p.MSHRMsg  )
    # Deallocating from MSHR
    s.MSHR_dealloc_mux_in_M0 = Wire( p.CacheReqType )
    # Set the CacheReqType by picking values from MSHR
    s.MSHR_dealloc_mux_in_M0 //= lambda: p.CacheReqType( s.MSHR_dealloc_out.type_, 
      s.MSHR_dealloc_out.opaque, s.MSHR_dealloc_out.addr, s.MSHR_dealloc_out.len, 
      s.MSHR_dealloc_out.data )
    s.status.amo_hit_M0             //= s.MSHR_dealloc_out.amo_hit

    # Chooses the cache request from proc or MSHR (memresp)
    s.cachereq_memresp_mux_M0 = Mux( p.CacheReqType, 2 )(
      in_ = {
        0: s.cachereq_Y,
        1: s.MSHR_dealloc_mux_in_M0
      },
      sel = s.ctrl.cachereq_memresp_mux_sel_M0,
    )

    s.cachereq_M0 = Wire( p.PipelineMsg )
    s.cachereq_M0.len    //= s.cachereq_memresp_mux_M0.out.len
    s.cachereq_M0.type_  //= s.cachereq_memresp_mux_M0.out.type_
    s.cachereq_M0.opaque //= s.cachereq_memresp_mux_M0.out.opaque

    # Chooses addr bypassed from L1 as a result of write hit clean
    s.cachereq_addr_M1_forward = Wire( p.BitsAddr )
    s.addr_mux_M0 = Mux( p.BitsAddr, 2 )(
      in_ = {
        0: s.cachereq_memresp_mux_M0.out.addr,
        1: s.cachereq_addr_M1_forward
      },
      sel = s.ctrl.addr_mux_sel_M0,
    )
    connect_bits2bitstruct( s.cachereq_M0.addr, s.addr_mux_M0.out )

    # Converts a 32-bit word to 128-bit line by replicated the word multiple times 
    s.replicator_M0 = CacheDataReplicator( p )(
      msg_len = s.cachereq_memresp_mux_M0.out.len,
      data    = s.cachereq_memresp_mux_M0.out.data,
      is_amo  = s.ctrl.is_amo_M0,
      offset  = s.cachereq_M0.addr.offset
    )

    # Selects between data from the memory resp or from the replicator 
    # Dependent on if we have a refill response
    s.write_data_mux_M0 = Mux( p.BitsCacheline, 2 )(
      in_ = {
        0: s.replicator_M0.out,
        1: s.pipeline_reg_M0.out.data
      },
      sel = s.ctrl.wdata_mux_sel_M0,
      out = s.cachereq_M0.data,
    )

    s.tag_entries_M1_bypass = [ Wire( p.StructTagArray ) for _ in range( p.associativity ) ]
    s.hit_way_M1_bypass = Wire( p.BitsAssoclog2 )

    # Update tag-array entry
    s.update_tag_way_mux_M0 = Mux( p.BitsAssoclog2, 2 )(
      in_ = {
        0: s.hit_way_M1_bypass,
        1: s.ctrl.update_tag_way_M0,
      },
      sel = s.ctrl.update_tag_sel_M0,
    )

    # Decides the bits that will be written into the sram depending on the state
    s.update_tag_unit = UpdateTagArrayUnit( p )(
      way        = s.update_tag_way_mux_M0.out,
      offset     = s.cachereq_M0.addr.offset,
      cmd        = s.ctrl.update_tag_cmd_M0,
      refill_dty = s.MSHR_dealloc_out.dirty_bits,
    )
    for i in range( p.associativity ):
      s.update_tag_unit.old_entries[i] //= s.tag_entries_M1_bypass[i]

    # Index select for the tag array as a result of cache initialization
    s.tag_array_idx_mux_M0 = Mux( p.BitsIdx, 2 )(
      in_ = {
        0: s.cachereq_M0.addr.index,
        1: s.ctrl.tag_array_init_idx_M0,
      },
      sel = s.ctrl.tag_array_idx_sel_M0,
    )

    # Select if we need to rewrite the tag from the tab unit
    s.tag_array_tag_mux_M0 = Mux( p.BitsTag, 2 )(
      in_ = {
        0: s.cachereq_M0.addr.tag,
        1: s.update_tag_unit.out.tag,
      },
      sel = s.ctrl.update_tag_sel_M0,
    )

    # Tag array inputs
    s.tag_array_struct_M0 = Wire( p.StructTagArray )
    s.tag_array_struct_M0.tag //= s.tag_array_tag_mux_M0.out
    s.tag_array_struct_M0.val //= s.update_tag_unit.out.val
    s.tag_array_struct_M0.dty //= s.update_tag_unit.out.dty

    if not p.full_sram:
      s.tag_array_struct_M0.tmp //= p.BitsTagArrayTmp( 0 )
    s.tag_array_wdata_M0 = Wire( p.BitsTagArray )
    connect_bits2bitstruct( s.tag_array_wdata_M0, s.tag_array_struct_M0 )

    # Send the M0 status signals to control
    s.status.memresp_type_M0   //= s.pipeline_reg_M0.out.type_
    s.status.cachereq_type_M0  //= s.cachereq_memresp_mux_M0.out.type_

    #--------------------------------------------------------------------
    # M1 Stage
    #--------------------------------------------------------------------

    # Pipeline registers
    s.cachereq_M1 = DpathPipelineReg( p )(
      in_ = s.cachereq_M0,
      en  = s.ctrl.reg_en_M1,
    )

    # Data array idx
    s.flush_idx_M1 = RegEnRst( p.BitsIdx )(
      in_ = s.ctrl.tag_array_init_idx_M0,
      en  = s.ctrl.flush_init_reg_en_M1,
    )

    # Send the dty bits to the M1 stage and use for wben mask into data array
    s.dty_bits_mask_M1 = RegEnRst( p.BitsDirty )(
      in_ = s.MSHR_dealloc_out.dirty_bits, # From M0 stage
      en  = s.ctrl.reg_en_M1,
      out = s.status.dty_bits_mask_M1,
    )

    # Foward the M1 addr to M0
    connect_bits2bitstruct( s.cachereq_addr_M1_forward, s.cachereq_M1.out.addr )

    # Register file to store the replacement info
    s.replacement_bits_M1 = ReplacementBitsReg( p )(
      raddr = s.cachereq_M1.out.addr.index,
      waddr = s.cachereq_M1.out.addr.index,
      wdata = s.ctrl.ctrl_bit_rep_wr_M0,
      wen   = s.ctrl.ctrl_bit_rep_en_M1
    )

    # Tag arrays
    tag_arrays_M1 = []
    for i in range( p.associativity ):
      tag_arrays_M1.append(
        SramPRTL( p.bitwidth_tag_array, p.nblocks_per_way )
        (
          port0_val   = s.ctrl.tag_array_val_M0[i],
          port0_type  = s.ctrl.tag_array_type_M0,
          port0_idx   = s.tag_array_idx_mux_M0.out,
          port0_wdata = s.tag_array_wdata_M0,
          port0_wben  = s.ctrl.tag_array_wben_M0,
        )
      )
    s.tag_arrays_M1 = tag_arrays_M1

    # Struct for the tag array output
    s.tag_array_out_M1 = [ Wire( p.StructTagArray ) for _ in range( p.associativity ) ]
    # Saves output of the SRAM during stall
    stall_engines_M1 = []
    for i in range( p.associativity ):
      # Connect the Bits object output of SRAM to a struct
      connect_bits2bitstruct( s.tag_arrays_M1[i].port0_rdata, s.tag_array_out_M1[i] )
      stall_engines_M1.append(
        StallEngine( p.StructTagArray )(
          in_ = s.tag_array_out_M1[i],
          en  = s.ctrl.stall_reg_en_M1
        )
      )
    s.tag_array_rdata_M1 = stall_engines_M1

    # Bypass the current tag-array entries to M0
    for i in range( p.associativity ):
      s.tag_entries_M1_bypass[i] //= s.tag_array_rdata_M1[i].out

    # An one-entry MSHR for holding the cache request during a miss
    s.MSHR_alloc_in = Wire( p.MSHRMsg )
    s.MSHR_alloc_in.type_   //= s.cachereq_M1.out.type_
    connect_bits2bitstruct( s.MSHR_alloc_in.addr, s.cachereq_M1.out.addr )
    s.MSHR_alloc_in.opaque  //= s.cachereq_M1.out.opaque
    # select only one word of data to store since the rest is replicated
    s.MSHR_alloc_in.data    //= s.cachereq_M1.out.data[0:p.bitwidth_data]
    s.MSHR_alloc_in.len     //= s.cachereq_M1.out.len
    s.MSHR_alloc_in.repl    //= s.ctrl.way_offset_M1
    s.MSHR_alloc_in_amo_hit_bypass = Wire( p.StructHit )
    s.MSHR_alloc_in.amo_hit //= s.MSHR_alloc_in_amo_hit_bypass.hit
    s.MSHR_alloc_in.dirty_bits //=  lambda: (s.tag_array_rdata_M1[s.ctrl.way_offset_M1].out.dty
     & s.ctrl.dirty_evict_mask_M1 )
    
    s.MSHR_alloc_id = Wire(p.BitsOpaque)

    s.mshr = MSHR( p, 1 )(
      alloc_en    = s.ctrl.MSHR_alloc_en,
      alloc_in    = s.MSHR_alloc_in,
      alloc_id    = s.MSHR_alloc_id,
      full        = s.status.MSHR_full,
      empty       = s.status.MSHR_empty,
      dealloc_id  = s.pipeline_reg_M0.out.opaque,
      dealloc_en  = s.ctrl.MSHR_dealloc_en,
      dealloc_out = s.MSHR_dealloc_out,
    )

    # Combined comparator set for both dirty line detection and hit detection 
    s.comparator_set = TagArrayRDataProcessUnit( p )(
      addr_tag   = s.cachereq_M1.out.addr.tag,
      is_init    = s.ctrl.is_init_M1,
      hit        = s.status.hit_M1,
      hit_way    = s.status.hit_way_M1,
      inval_hit  = s.status.inval_hit_M1,
      offset     = s.cachereq_M1.out.addr.offset,
      line_dirty = s.status.ctrl_bit_dty_rd_line_M1,
      word_dirty = s.status.ctrl_bit_dty_rd_word_M1,
    )
    for i in range( p.associativity ):
      s.comparator_set.tag_array[i] //= s.tag_array_rdata_M1[i].out

    # stall engine to save the hit bit into the MSHR for AMO operations only
    StructHit = p.StructHit
    s.hit_stall_engine = StallEngine( StructHit )
    s.hit_stall_engine.in_ //= lambda: StructHit( s.comparator_set.hit|s.comparator_set.inval_hit,
      s.comparator_set.hit_way )
    s.hit_stall_engine.en  //= s.ctrl.hit_stall_eng_en_M1
    s.hit_stall_engine.out //= s.MSHR_alloc_in_amo_hit_bypass

    s.hit_way_M1_bypass //= s.comparator_set.hit_way
    s.write_mask_M1 = Wire( p.BitsDirty )
    s.write_mask_M1 //= lambda: s.tag_array_rdata_M1[s.ctrl.way_offset_M1].out.dty

    # Mux for choosing which way to evict
    s.evict_way_mux_M1 = PMux( p.BitsTag, p.associativity )(
      sel = s.ctrl.way_offset_M1,
    )
    for i in range( p.associativity ):
      s.evict_way_mux_M1.in_[i] //= s.tag_array_rdata_M1[i].out.tag

    s.flush_idx_mux_M1 = Mux( p.BitsIdx, 2 )(
      in_ = {
        0: s.cachereq_M1.out.addr.index,
        1: s.flush_idx_M1.out,
      },
      sel = s.ctrl.flush_idx_mux_sel_M1,
    )

    s.evict_addr_M1 = Wire( p.StructAddr )
    s.evict_addr_M1.tag    //= s.evict_way_mux_M1.out
    s.evict_addr_M1.index  //= s.flush_idx_mux_M1.out # s.cachereq_M1.out.addr.index
    s.evict_addr_M1.offset //= p.BitsOffset(0) # Memreq offset doesn't matter

    s.cachereq_M1_2 = Wire( p.PipelineMsg )

    s.evict_mux_M1 = Mux( p.StructAddr, 2 )(
      in_ = {
        0: s.cachereq_M1.out.addr,
        1: s.evict_addr_M1
      },
      sel = s.ctrl.evict_mux_sel_M1,
      out = s.cachereq_M1_2.addr
    )

    # Data array inputs
    s.data_array_wdata_M1 = Wire( p.BitsCacheline )
    s.data_array_wdata_M1 //= s.cachereq_M1.out.data

    s.index_offset_M1 = Indexer( p )(
      index  = s.cachereq_M1_2.addr.index,
      offset = s.ctrl.way_offset_M1,
    )

    s.cachereq_M1_2.len    //= s.cachereq_M1.out.len
    s.cachereq_M1_2.data   //= s.cachereq_M1.out.data
    s.cachereq_M1_2.type_  //= s.cachereq_M1.out.type_
    s.cachereq_M1_2.opaque //= s.cachereq_M1.out.opaque

    # Send the M1 status signals to control
    s.status.ctrl_bit_rep_rd_M1 //= s.replacement_bits_M1.rdata
    s.status.cachereq_type_M1   //= s.cachereq_M1.out.type_
    s.status.len_M1             //= s.cachereq_M1.out.len
    s.status.offset_M1          //= s.cachereq_M1.out.addr.offset
    s.status.MSHR_ptr           //= s.MSHR_dealloc_out.repl
    s.status.MSHR_type          //= s.MSHR_dealloc_out.type_
    s.status.amo_hit_way_M1     //= s.MSHR_alloc_in_amo_hit_bypass.hit_way

    #--------------------------------------------------------------------
    # M2 Stage
    #--------------------------------------------------------------------

    # Pipeline registers
    s.cachereq_M2 = DpathPipelineReg( p )(
      in_ = s.cachereq_M1_2,
      en  = s.ctrl.reg_en_M2,
    )

    s.write_mask_M2 = RegEnRst( p.BitsDirty )(
      in_ = s.write_mask_M1,
      en  = s.ctrl.reg_en_M2
    )

    s.data_array_M2 = SramPRTL( p.bitwidth_cacheline, p.total_num_cachelines )(
      port0_val   = s.ctrl.data_array_val_M1,
      port0_type  = s.ctrl.data_array_type_M1,
      port0_idx   = s.index_offset_M1.out,
      port0_wdata = s.data_array_wdata_M1,
      port0_wben  = s.ctrl.data_array_wben_M1
    )

    s.stall_engine_M2 = StallEngine( p.BitsCacheline )(
      in_ = s.data_array_M2.port0_rdata,
      en  = s.ctrl.stall_reg_en_M2
    )

    s.read_data_mux_M2 = Mux( p.BitsCacheline, 2 )(
      in_ = {
        0: s.stall_engine_M2.out,
        1: s.cachereq_M2.out.data
      },
      sel = s.ctrl.read_data_mux_sel_M2
    )

    # Data size select mux for subword accesses
    s.data_size_mux_M2 = DataSizeMux( p )(
      data   = s.read_data_mux_M2.out,
      en     = s.ctrl.data_size_mux_en_M2,
      len_   = s.cachereq_M2.out.len,
      offset = s.cachereq_M2.out.addr.offset,
      is_amo = s.ctrl.is_amo_M2,
    )

    # selects the appropriate offset and len for memreq based on the type
    s.mem_req_off_len_M2 = OffsetLenSelector( p )(
      offset_i = s.cachereq_M2.out.addr.offset,
      is_amo   = s.ctrl.is_amo_M2,
    )

    # Send the M2 status signals to control
    s.status.cachereq_type_M2 //= s.cachereq_M2.out.type_

    # Construct the memreq signal
    # build a addr struct to zip the addr, idx, and tag together
    s.memreq_addr_out = Wire( p.StructAddr )
    s.memreq_addr_out.tag    //= s.cachereq_M2.out.addr.tag
    s.memreq_addr_out.index  //= s.cachereq_M2.out.addr.index
    s.memreq_addr_out.offset //= s.mem_req_off_len_M2.offset_o
    s.memreq_addr_bits = Wire( p.BitsAddr )
                            # Bits32            # StructAddr
    connect_bits2bitstruct( s.memreq_addr_bits, s.memreq_addr_out )
    s.memreq_M2.opaque  //= s.cachereq_M2.out.opaque
    s.memreq_M2.type_   //= s.ctrl.memreq_type
    s.memreq_M2.data    //= s.read_data_mux_M2.out
    s.memreq_M2.len     //= s.mem_req_off_len_M2.len
    s.memreq_M2.wr_mask //= s.write_mask_M2.out
    s.memreq_M2.addr    //= s.memreq_addr_bits

    # Construct the cacheresp signal
    s.cacheresp_M2.data   //= s.data_size_mux_M2.out
    s.cacheresp_M2.type_  //= s.cachereq_M2.out.type_
    s.cacheresp_M2.len    //= s.cachereq_M2.out.len
    s.cacheresp_M2.opaque //= s.cachereq_M2.out.opaque
    s.cacheresp_M2.test   //= s.ctrl.hit_M2

  def line_trace( s ):
    msg = ""
    # msg += f'en1:{s.ctrl.reg_en_M1}'
    return msg
