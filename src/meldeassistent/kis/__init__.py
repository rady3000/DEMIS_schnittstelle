"""KIS-Adapter. Außerhalb dieses Pakets wird nur ``schnittstelle`` verwendet."""

from .schnittstelle import KisAdapter, KisAntwortFehler, KisDatenFehler, KisFehler, KisNichtErreichbar

__all__ = ["KisAdapter", "KisAntwortFehler", "KisDatenFehler", "KisFehler", "KisNichtErreichbar"]
