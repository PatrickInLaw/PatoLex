"""Probe the 5090 env for the page-type-classifier bake-off: Surya layout model + any local VLM route."""
import importlib, importlib.metadata as M

def ver(pkg):
    try:
        return M.version(pkg)
    except Exception:
        return "MISSING"

def can_import(mod):
    try:
        importlib.import_module(mod)
        return "OK"
    except Exception as e:
        return f"NO ({type(e).__name__}: {str(e)[:80]})"

print("surya-ocr        :", ver("surya-ocr"))
print("surya.layout     :", can_import("surya.layout"))
print("surya.detection  :", can_import("surya.detection"))
print("torch            :", ver("torch"))
try:
    import torch
    print("cuda.is_available:", torch.cuda.is_available())
    if torch.cuda.is_available():
        print("cuda device      :", torch.cuda.get_device_name(0))
except Exception as e:
    print("torch import     : NO", e)
print("transformers     :", ver("transformers"))
print("ollama(py)       :", ver("ollama"))
print("qwen-vl-utils    :", ver("qwen-vl-utils"))
