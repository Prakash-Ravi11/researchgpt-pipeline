"""Native process memory counters; no extra package or hardware requirement."""
import os
import sys

def process_memory():
    if os.name=="nt":
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_=[("cb",wintypes.DWORD),("PageFaultCount",wintypes.DWORD)]+[
                (name,ctypes.c_size_t) for name in ("PeakWorkingSetSize","WorkingSetSize",
                "QuotaPeakPagedPoolUsage","QuotaPagedPoolUsage","QuotaPeakNonPagedPoolUsage",
                "QuotaNonPagedPoolUsage","PagefileUsage","PeakPagefileUsage")]
        counters=Counters();counters.cb=ctypes.sizeof(counters)
        kernel=ctypes.WinDLL("kernel32",use_last_error=True)
        kernel.GetCurrentProcess.restype=wintypes.HANDLE
        api=ctypes.WinDLL("psapi",use_last_error=True)
        api.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
        if not api.GetProcessMemoryInfo(kernel.GetCurrentProcess(),ctypes.byref(counters),counters.cb):
            return {"rss_bytes":None,"peak_working_set_bytes":None,"reason":"native_counter_error"}
        return {"rss_bytes":counters.WorkingSetSize,"peak_working_set_bytes":counters.PeakWorkingSetSize}
    import resource
    peak=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {"rss_bytes":None,"peak_working_set_bytes":int(peak*(1 if sys.platform=="darwin" else 1024))}
