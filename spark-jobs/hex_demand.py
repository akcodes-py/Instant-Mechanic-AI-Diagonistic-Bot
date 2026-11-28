#!/usr/bin/env python3
"""Hex-level breakdown heatmap + ETA retraining input from Parquet trip archives.

PySpark is the production engine; a pandas/pyarrow fallback keeps the pipeline
demonstrable on an 8 GB laptop. No accuracy is claimed and no model is committed.
"""
from __future__ import annotations

import argparse
from pathlib import Path


def run_local(input_path: str, output_path: str) -> None:
    import pandas as pd

    trips = pd.read_parquet(input_path)
    required = {"h3_res7_index", "bucket_start", "required_skill"}
    missing = required - set(trips.columns)
    if missing:
        raise ValueError(f"Parquet archive is missing columns: {sorted(missing)}")

    heat = (
        trips.groupby(["h3_res7_index", "bucket_start", "required_skill"])
        .size()
        .reset_index(name="breakdowns")
        .sort_values("breakdowns", ascending=False)
    )
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    heat.to_parquet(output_path, index=False)
    print(f"Wrote {len(heat)} hex/bucket rows to {output_path} (pandas fallback)")


def run_spark(input_path: str, output_path: str) -> None:
    from pyspark.sql import SparkSession
    from pyspark.sql.functions import col, count

    spark = SparkSession.builder.appName("instant-mechanic-hex-demand").getOrCreate()
    try:
        trips = spark.read.parquet(input_path)
        heat = (
            trips.groupBy("h3_res7_index", "bucket_start", "required_skill")
            .agg(count("*").alias("breakdowns"))
            .orderBy(col("breakdowns").desc())
        )
        heat.write.mode("overwrite").parquet(output_path)
        print(f"Wrote hex demand to {output_path} (PySpark)")
    finally:
        spark.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Parquet trip archive (file or directory)")
    parser.add_argument("--output", required=True, help="Destination Parquet path")
    parser.add_argument("--local", action="store_true", help="Use pandas instead of PySpark")
    args = parser.parse_args()

    if args.local:
        run_local(args.input, args.output)
    else:
        run_spark(args.input, args.output)


if __name__ == "__main__":
    main()
