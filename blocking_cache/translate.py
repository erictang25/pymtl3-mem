"""
=========================================================================
translate.py
=========================================================================
Translates the Blocking Cache to System Verilog

Author : Xiaoyu Yan, Eric Tang
Date   : 23 December 2019
"""

import argparse
import os
import sys

# Import the translation pass from verilog backend
from pymtl3.passes.backends.verilog import TranslationConfigs, TranslationPass

# Import the Cache generator
from .BlockingCacheRTL import BlockingCacheRTL
from ifcs.MemMsg import MemMsgType, mk_mem_msg

#=========================================================================
# Command line processing
#=========================================================================

def parse_cmdline():
  p = argparse.ArgumentParser(description='Translate the cache with some params')
  # Additional commane line arguments for the translator
  p.add_argument( "--output-dir", default="", type=str )
  p.add_argument( "--size", default=4096, type=int )
  p.add_argument( "--clw", default=128, type=int )
  p.add_argument( "--dbw", default=32, type=int )
  p.add_argument( "--abw", default=32, type=int )
  p.add_argument( "--obw", default=8, type=int )
  p.add_argument( "--asso", default=2, type=int )
  opts = p.parse_args()
  return opts

#=========================================================================
# Runs the translation script
#=========================================================================

def main():
  opts = parse_cmdline()
  CacheReqType, CacheRespType = mk_mem_msg(opts.obw, opts.abw, opts.dbw)
  MemReqType, MemRespType = mk_mem_msg(opts.obw, opts.abw, opts.clw)
  # Instantiate the cache
  dut = BlockingCacheRTL( CacheReqType, CacheRespType, MemReqType,
                          MemRespType, opts.size, opts.asso )
  success = False
  dut.verilog_translate = True
  # dut.config_verilog_translate = TranslationConfigs(
  #     explicit_module_name = 'BlockingCache_{}_{}_{}_{}_{}'.format(opts.size,
  #     opts.clw, opts.abw, opts.dbw, opts.asso),
  #   )
  try:
    dut.elaborate()
    dut.apply( TranslationPass() )
    success = True
  finally:
    if success:
      # path = os.path.join(os.getcwd(), f"{dut.translated_top_module_name}.sv")
      print("\nTranslation finished successfully!")
      # print(f"You can find the generated SystemVerilog file at {path}.")
    else:
      print("\nTranslation failed!")

if __name__ == "__main__":
  main()
