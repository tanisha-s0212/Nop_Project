"""Validated generic calculations over prepared observations; no business formulas."""

from collections import defaultdict
from datetime import date
import json
import math
import re
import statistics


OPERATIONS = {"summary", "sum", "mean", "min", "max", "count_distinct", "series", "change", "compare", "rank", "anomaly"}
ANALYSIS_FIELDS = {"measure", "operation", "dimensions", "time_field", "time_range", "filters", "missing_policy", "direction", "anomaly_threshold"}


def period(value):
    if not isinstance(value, str):
        raise ValueError("period must be an explicit ISO string")
    if re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value):
        date.fromisoformat(value + "-01")
        return value
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        date.fromisoformat(value)
        return value
    raise ValueError("period must be canonical YYYY-MM or YYYY-MM-DD; ambiguous dates are unsupported")


def validate_analysis(asset, analysis):
    if not isinstance(analysis, dict) or set(analysis) - ANALYSIS_FIELDS:
        raise ValueError("analysis contains unsupported fields")
    measure = analysis.get("measure", asset["spec"].get("target_column"))
    operation = analysis.get("operation", "summary")
    if not isinstance(measure, str) or measure not in asset["fields"]:
        raise ValueError("supply an exact measure field present in the prepared dataset")
    if operation not in OPERATIONS:
        raise ValueError("unsupported analytical operation: " + str(operation))
    dimensions = analysis.get("dimensions", [])
    if not isinstance(dimensions, list) or any(not isinstance(d, str) or d not in asset["fields"] for d in dimensions) or len(set(dimensions)) != len(dimensions):
        raise ValueError("dimensions must name distinct fields in the dataset")
    if measure in dimensions:
        raise ValueError("the measure cannot also be a grouping dimension")
    if operation == "sum":
        semantics = asset["spec"].get("measure_semantics", {}).get(measure, {})
        if semantics.get("additive") is not True or not semantics.get("evidence"):
            raise ValueError("sum requires explicit additive measure semantics and evidence; repeated document totals cannot be assumed additive")
    time_field = analysis.get("time_field", asset["spec"].get("period_column"))
    if time_field is not None and time_field not in asset["fields"]:
        raise ValueError("time field is absent from the dataset")
    if operation in {"change", "series"} and not time_field:
        raise ValueError("this operation requires an explicit time field")
    if operation in {"compare", "rank"} and not dimensions:
        raise ValueError("comparison and ranking require explicit grouping dimensions")
    if analysis.get("missing_policy", "reject") not in {"reject", "exclude"}:
        raise ValueError("missing_policy must be reject or explicitly exclude")
    if analysis.get("direction", "descending") not in {"ascending", "descending"}:
        raise ValueError("direction must be ascending or descending")
    interval = analysis.get("time_range")
    if interval is not None:
        if not isinstance(interval, dict) or set(interval) - {"start", "end"} or not interval or not time_field:
            raise ValueError("time_range requires a time field and start and/or end")
        bounds = [period(value) for value in interval.values()]
        if len({len(value) for value in bounds}) != 1 or interval.get("start", "") > interval.get("end", "9999-12-31"):
            raise ValueError("time range has incompatible or reversed bounds")
    filters = analysis.get("filters", [])
    if not isinstance(filters, list):
        raise ValueError("filters must be an array")
    for item in filters:
        if not isinstance(item, dict) or set(item) != {"field", "operator", "value"} or item["field"] not in asset["fields"]:
            raise ValueError("each filter needs an exact field, operator and value")
        if item["operator"] not in {"eq", "in"}:
            raise ValueError("only explicit eq and in filters are supported")
        if item["operator"] == "in" and (not isinstance(item["value"], list) or not item["value"]):
            raise ValueError("in filters require a nonempty value array")
    threshold = analysis.get("anomaly_threshold", 3.0)
    if type(threshold) not in {int, float} or not math.isfinite(threshold) or threshold <= 0:
        raise ValueError("anomaly_threshold must be a positive finite number")
    return {**analysis, "measure": measure, "operation": operation, "dimensions": dimensions,
        "time_field": time_field, "missing_policy": analysis.get("missing_policy", "reject")}


def execute_analysis(asset, analysis):
    analysis = validate_analysis(asset, analysis)
    measure, operation, dimensions, time_field = (analysis[key] for key in ("measure", "operation", "dimensions", "time_field"))
    groups = defaultdict(list)
    excluded_missing, filtered = 0, 0
    for ordinal, row in enumerate(asset["rows"], 1):
        if any((row[item["field"]] != str(item["value"])) if item["operator"] == "eq" else
               (row[item["field"]] not in {str(value) for value in item["value"]}) for item in analysis.get("filters", [])):
            filtered += 1
            continue
        required = [measure, *dimensions, *([time_field] if time_field else [])]
        if any(row[field] == "" for field in required):
            if analysis["missing_policy"] == "reject":
                raise ValueError(f"missing required observation at data row {ordinal}; no zero was imputed")
            excluded_missing += 1
            continue
        timestamp = period(row[time_field]) if time_field else None
        interval = analysis.get("time_range", {})
        if interval and (any(len(bound) != len(timestamp) for bound in interval.values())):
            raise ValueError("time filter frequency differs from observed periods")
        if timestamp and ((interval.get("start") and timestamp < interval["start"]) or (interval.get("end") and timestamp > interval["end"])):
            filtered += 1
            continue
        if operation == "count_distinct":
            value = row[measure]
        else:
            try:
                value = float(row[measure])
            except (TypeError, ValueError):
                raise ValueError(f"nonnumeric measure at data row {ordinal}") from None
            if not math.isfinite(value):
                raise ValueError(f"nonfinite measure at data row {ordinal}")
        groups[tuple(row[d] for d in dimensions)].append((timestamp, value))
    if not groups:
        raise ValueError("no valid observations remain for this request")
    results = []
    for key, observations in sorted(groups.items()):
        if time_field:
            observations.sort(key=lambda item: item[0])
        times, values = zip(*observations)
        item = {"dimensions": dict(zip(dimensions, key)), "observations": len(values)}
        if time_field:
            item.update(period_start=times[0], period_end=times[-1])
        if operation in {"change", "series"} and len(set(times)) != len(times):
            raise ValueError("time series contains duplicate periods within its grouping grain")
        if operation == "count_distinct":
            item["value"] = len(set(values))
        elif operation == "summary":
            item.update(minimum=min(values), maximum=max(values), mean=statistics.fmean(values))
        elif operation in {"sum", "mean", "min", "max", "compare", "rank"}:
            function = {"sum": math.fsum, "mean": statistics.fmean, "min": min, "max": max,
                        "compare": statistics.fmean, "rank": statistics.fmean}[operation]
            item["value"] = function(values)
            if not math.isfinite(item["value"]):
                raise ValueError("analytical result is nonfinite")
        elif operation == "series":
            item["points"] = [{"period": timestamp, "value": value} for timestamp, value in observations]
        elif operation == "change":
            if len(values) < 2:
                raise ValueError("change analysis requires at least two observations")
            item.update(first_value=values[0], last_value=values[-1], change=values[-1] - values[0])
            item["percentage_change"] = 100 * item["change"] / abs(values[0]) if values[0] != 0 else None
        elif operation == "anomaly":
            if len(values) < 3:
                raise ValueError("anomaly analysis requires at least three observations")
            mean, std = statistics.fmean(values), statistics.pstdev(values)
            item.update(method="descriptive_population_z_score", threshold=analysis.get("anomaly_threshold", 3.0),
                        points=[{"period": timestamp, "value": value, "score": (value - mean) / std if std else 0.0}
                            for timestamp, value in observations if std and abs((value - mean) / std) >= analysis.get("anomaly_threshold", 3.0)])
        results.append(item)
    if operation in {"compare", "rank"}:
        results.sort(key=lambda item: item["value"], reverse=analysis.get("direction", "descending") == "descending")
        previous_value, previous_rank = None, 0
        for index, item in enumerate(results, 1):
            item["rank"] = previous_rank if index > 1 and item["value"] == previous_value else index
            item["difference_from_first"] = item["value"] - results[0]["value"]
            previous_value, previous_rank = item["value"], item["rank"]
    result = {"measure_field": measure, "method": operation, "groups": results,
        "input_rows": len(asset["rows"]), "used_rows": sum(len(values) for values in groups.values()),
        "filtered_rows": filtered, "excluded_missing_rows": excluded_missing,
        "method_limitations": ["Grouped comparison values are observation means."] if operation in {"compare", "rank"} else
            ["Descriptive unusualness is not evidence of a causal driver or a future anomaly."] if operation == "anomaly" else []}
    json.dumps(result, allow_nan=False)
    return result
