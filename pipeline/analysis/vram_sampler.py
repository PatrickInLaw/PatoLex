"""Tight GPU VRAM peak sampler -- polls nvidia-smi memory.used at high frequency and reports the running max,
so we can verify a hard ceiling holds while stacking page-shape tracks (a >32GB spike could TDR-reset the 5090).
Run with ANY python (no venv needed):  python vram_sampler.py <seconds> [interval_s]"""
import sys, time, subprocess

dur = float(sys.argv[1]) if len(sys.argv) > 1 else 120.0
iv  = float(sys.argv[2]) if len(sys.argv) > 2 else 0.1
peak = 0; n = 0
t0 = time.time()
while time.time() - t0 < dur:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5)
        used = int(out.stdout.strip().splitlines()[0])
        n += 1
        if used > peak:
            peak = used
            print(f"  new peak {peak} MiB at t={time.time()-t0:.1f}s", flush=True)
    except Exception as e:
        print("sample error:", e, flush=True)
    time.sleep(iv)
print(f"\nVRAM PEAK over {dur:.0f}s ({n} samples): {peak} MiB = {peak/1024:.2f} GiB  (GPU total 32607 MiB)")
