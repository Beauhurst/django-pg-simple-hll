from django.db.models import IntegerField
from django.db.models.lookups import Transform


class HLLHash(Transform):
    """
    Default hash function for HLL
    - it hashes and transforms any field to an unsigned int 32
    """

    function = "hll_hash"
    lookup_name = "hll_hash"
    output_field = IntegerField()
