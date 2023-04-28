from django.db.models import Aggregate, IntegerField


class HLLCardinality(Aggregate):
    """
    Return an approximate distinct count based on the HyperLogLog algorithm
    as described in:
        http://algo.inria.fr/flajolet/Publications/FlMa85.pdf

    Despite being written in a combination of PL/pgSQL and SQL, it should
    outperform COUNT(DISTINCT ...) in many circumstances. It should also be
    more memory efficient. Notice, however that it will always be an approximate
    result rather than an exact count.
    """

    function = "hll_cardinality"
    name = "HLLCardinality"
    allow_distinct = False
    output_field = IntegerField()
    empty_result_set_value = 0
