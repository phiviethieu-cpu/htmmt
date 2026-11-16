#!/usr/bin/env python3
"""Gom results/<kịch bản>_n<N>.csv thành data/measured_<kịch bản>.csv (trung bình, độ lệch chuẩn).

Bỏ vòng 1 (khởi động). Cột đầu ra khớp với file model_*.csv để pgfplots vẽ chồng lên nhau.
"""
import csv
import glob
import os
import re
import statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "..", "results")
OUT = os.path.join(HERE, "..", "data")

# Kích thước bản cập nhật chiều lên của từng kịch bản (khớp run_experiments.SCENARIOS)
UP_SIZE = {"K2_edge_comp": 10 ** 6, "K2_cloud_comp": 10 ** 6}

groups = {}
for path in glob.glob(os.path.join(RES, "*_n[0-9].csv")):
    m = re.match(r"(.+)_n(\d)\.csv$", os.path.basename(path))
    name, n = m.group(1), int(m.group(2))
    with open(path) as f:
        rows = [r for r in csv.DictReader(f) if int(r["round"]) > 1]
    if rows:
        groups.setdefault(name, []).append((n, rows))

for name, items in groups.items():
    with open(os.path.join(OUT, f"measured_{name}.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["n", "t_down", "t_up", "t_round", "t_round_sd", "thr_mbps"])
        for n, rows in sorted(items):
            col = lambda k: [float(r[k]) for r in rows]
            sd = st.stdev(col("t_round")) if len(rows) > 1 else 0.0
            # Thông lượng gộp pha upload: N bản cập nhật trong T_up
            size_up = UP_SIZE.get(name, 10 ** 7)
            thr = n * size_up * 8 / st.mean(col("t_up")) / 1e6
            w.writerow([n, f"{st.mean(col('t_down')):.3f}", f"{st.mean(col('t_up')):.3f}",
                        f"{st.mean(col('t_round')):.3f}", f"{sd:.3f}", f"{thr:.1f}"])
    print("wrote", name)
