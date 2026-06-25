from paper_search.resolvers.crossref_tdm import CrossrefTdmResolver
from paper_search.resolvers.oa_index import oa_links_from_paper
from paper_search.resolvers.scihub import SciHubResolver, ScihubClient
from paper_search.resolvers.unpaywall import UnpaywallResolver

__all__ = [
    "CrossrefTdmResolver",
    "SciHubResolver",
    "ScihubClient",
    "UnpaywallResolver",
    "oa_links_from_paper",
]
