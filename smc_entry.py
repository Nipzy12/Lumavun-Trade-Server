"""Standalone, read-only SMC research executable entrypoint for Windows.

Never initializes live trading order routes. MT5 connections are used only
to read historical OHLC candles.
"""
from multiprocessing import freeze_support
from lumavun.smc_report import main

if __name__=="__main__":
    freeze_support()
    main()
