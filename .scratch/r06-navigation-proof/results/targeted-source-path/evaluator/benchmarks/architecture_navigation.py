"""Gold-blind R0.6 scheduler entry points shared by acquisition and replay."""
from loci.path_navigation import choose_next_query, next_acquisition_query

__all__ = ["choose_next_query", "next_acquisition_query"]
