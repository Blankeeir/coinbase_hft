"""Bootstrap and run the trading loop."""
import argparse, time, threading, signal, sys
from data_handler import LimitOrderBook
from strategy import BreakoutWithOBI
from execution import ExecutionEngine
from fix_client import start_fix
from config import *

def run(symbol, window, threshold):
    book = LimitOrderBook(window=window)
    fix_initiator, app = start_fix(symbol, book)
    strategy = BreakoutWithOBI(book, window=window, obi_thr=threshold)
    exec_engine = ExecutionEngine(app, book, latency_ms=LATENCY_BUDGET_MS)

    try:
        while True:
            sig = strategy.on_tick(None)
            if sig == 'BUY':
                exec_engine.send_limit('BUY', 0.001)  # example size
            elif sig == 'SELL':
                exec_engine.send_limit('SELL', 0.001)
            exec_engine.monitor()
            time.sleep(0.05)
    except KeyboardInterrupt:
        print('Stopping...')
        fix_initiator.stop()
        sys.exit(0)

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument('--symbol', default=DEFAULT_SYMBOL)
    p.add_argument('--window', type=int, default=CHANNEL_WINDOW_SEC)
    p.add_argument('--threshold', type=float, default=OBI_THRESHOLD)
    args = p.parse_args()
    run(args.symbol, args.window, args.threshold)
