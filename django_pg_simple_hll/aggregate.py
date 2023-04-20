from django.db.models import Aggregate, IntegerField


class ApproxCardinality(Aggregate):
    function = "hll_approx_cardinality"
    name = "ApproxCardinality"
    allow_distinct = False
    output_field = IntegerField()
    empty_result_set_value = 0
