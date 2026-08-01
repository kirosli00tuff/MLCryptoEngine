"""Databento vendor adapter: GLBX.MDP3 (CME micro futures MES/MBT).

Raw DBN files are stored immutably under ``<data_root>/vendor/databento/``
(same convention as the recorder's raw tree: written once, never modified,
everything downstream regenerable from them). Canonical mapped rows carry
``source="databento"`` and Databento clocks — see :mod:`adapter` for the
clock provenance rules.
"""

from data.databento.adapter import SequenceAudit, map_mbp10, map_trade

__all__ = ["SequenceAudit", "map_mbp10", "map_trade"]
