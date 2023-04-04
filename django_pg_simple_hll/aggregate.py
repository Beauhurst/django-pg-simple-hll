from django.db.models import Aggregate, IntegerField


class ApproxCardinality(Aggregate):
    function = "hll_approx_cardinality"
    allow_distinct = False
    output_field = IntegerField()
