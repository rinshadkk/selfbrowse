"""Selfbrowse — a small browser agent that gets cheaper the more you use it."""
from selfbrowse.types import RunResult, Step, Usage

__version__ = "0.4.0"

__all__ = ["BrowseAgent", "Browser", "RunResult", "Step", "Usage", "run_flow", "__version__"]


def __getattr__(name: str):             # lazy: importing `selfbrowse` must not import Playwright
    if name == "BrowseAgent":
        from selfbrowse.agent import BrowseAgent
        return BrowseAgent
    if name == "Browser":
        from selfbrowse.browser import Browser
        return Browser
    if name == "run_flow":
        from selfbrowse.flow import run_flow
        return run_flow
    raise AttributeError(name)
