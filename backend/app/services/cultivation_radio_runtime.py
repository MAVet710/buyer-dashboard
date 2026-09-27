"""Explicit host lifecycle. Disabled by default; no scan starts on import."""
from threading import RLock
import ctypes
import os
from modules.cultivation.radio.config import load_config, RadioConfigError
from modules.cultivation.radio.runtime import RadioRuntime

_lock = RLock()
_runtime = None
_lease = None

class HostLease:
    def __init__(self):
        if os.name != 'nt':
            raise RadioConfigError('host_radio_platform_not_verified')
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        kernel.CreateMutexW.restype = ctypes.c_void_p
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel.CloseHandle.restype = ctypes.c_bool
        handle = kernel.CreateMutexW(None, False, r'Local\DoobieLogicCultivationRadio')
        error = ctypes.get_last_error()
        if not handle:
            raise RadioConfigError('radio_host_lock_unavailable')
        if error == 183:
            kernel.CloseHandle(handle)
            raise RadioConfigError('radio_host_already_running')
        self.kernel, self.handle = kernel, handle

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None

def get_radio_runtime():
    return _runtime

def start_host_radio(engine, config_path=None):
    global _runtime, _lease
    config = load_config(config_path)
    if config is None:
        return None
    with _lock:
        if _runtime is not None:
            if _runtime.engine is engine and _runtime.config == config and _runtime.thread.is_alive():
                return _runtime
            raise RadioConfigError('radio_runtime_already_owned')
        lease = HostLease()
        try:
            runtime = RadioRuntime(engine, config).start()
        except Exception:
            lease.close()
            raise
        _lease, _runtime = lease, runtime
        return runtime

def stop_host_radio():
    global _runtime, _lease
    with _lock:
        if _runtime is None:
            return True
        if not _runtime.stop():
            return False
        _runtime = None
        if _lease:
            _lease.close()
            _lease = None
        return True
