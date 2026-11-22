"""fast-anything: profile and record inside multiprocessing workers too.

While fast-anything profiles or records an app, it puts the folder with this file first on
PYTHONPATH, so every Python process the app starts loads it. Not meant to be used by hand.
Each multiprocessing worker (fork, spawn or forkserver; Pool and ProcessPoolExecutor included)
gets its own profiler or recorder and leaves its results in FAST_ANYTHING_CHILDREN. The app's own
sitecustomize, if it has one, still runs right after this.
"""

import os
import sys


def _fast_anything_watch_workers():
    import multiprocessing.process

    original = multiprocessing.process.BaseProcess._bootstrap
    if getattr(original, "_fast_anything", False):
        return

    def _bootstrap(self, *args, **kwargs):
        if os.name == "posix":
            # Pool.terminate() (and with Pool(...) as p) ends workers with SIGTERM: exit normally
            # instead, so the worker still leaves its results. Set first, before anything slow.
            import signal

            signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
        state = None
        try:
            state = sys.modules.get("_fast_anything_state")
            if state is None:  # a fresh interpreter (spawn, forkserver): load the runner
                import importlib.util

                spec = importlib.util.spec_from_file_location("_fast_anything_runner", os.environ["FAST_ANYTHING_RUNNER"])
                runner = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(runner)
                state = runner.child_state()
            state.start()
        except Exception as e:  # never break the app's workers
            sys.stderr.write("fast-anything: can't watch this worker: %r\n" % (e,))
            state = None
        try:
            return original(self, *args, **kwargs)
        finally:
            if state is not None:
                state.finish()

    _bootstrap._fast_anything = True
    multiprocessing.process.BaseProcess._bootstrap = _bootstrap


def _fast_anything_chain():
    """Run the sitecustomize this one hides, if there is one."""
    import importlib.util
    from importlib.machinery import PathFinder

    here = os.path.dirname(os.path.abspath(__file__))
    spec = PathFinder.find_spec("sitecustomize", [p for p in sys.path if os.path.abspath(p or ".") != here])
    if spec is not None and spec.loader is not None:
        spec.loader.exec_module(importlib.util.module_from_spec(spec))


if os.environ.get("FAST_ANYTHING_CHILDREN"):
    _fast_anything_watch_workers()
_fast_anything_chain()
