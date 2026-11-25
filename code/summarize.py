#!/usr/bin/env python3
"""Gom log thô trong results/ thành bảng số liệu trong data/ để vẽ biểu đồ.

  Nhóm K  : K*_n<N>.csv      -> data/measured_<kịch bản>.csv  (theo N)
  Nhóm Q1 : Q1_bw<B>.csv     -> data/q1_bw.csv                (theo băng thông WAN)
  Nhóm Q2 : Q2_loss<p>.csv   -> data/q2_loss.csv              (theo tỉ lệ mất gói)
            Q2_d<D>_l<p>.csv -> data/q2_delay.csv             (theo độ trễ WAN)
            mỗi lần chạy Q2  -> data/q2_curve_<tag>.csv       (độ chính xác theo thời gian)

Thời gian trung bình bỏ vòng 1 (khởi động). Thời gian tới độ chính xác mục tiêu (TTA)
cộng dồn T_round từ vòng 1 tới vòng đầu tiên đạt TARGET.
"""
import csv
import glob
import os
import re
import statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.environ.get("FL_RES", os.path.join(HERE, "..", "results"))
OUT = os.path.join(HERE, "..", "data")
TARGET = 0.90

# Kích thước bản cập nhật chiều lên của từng kịch bản nhóm K (khớp run_experiments.SCENARIOS)
UP_SIZE = {"K2_edge_comp": 10 ** 6, "K2_cloud_comp": 10 ** 6}


def load(path):
    with open(path) as f:
        return list(csv.DictReader(f))


def stats(rows, n, size_up):
    """Trung bình các pha (bỏ vòng 1), độ lệch chuẩn T_round, thông lượng gộp pha upload."""
    body = [r for r in rows if int(r["round"]) > 1]
    col = lambda k: [float(r[k]) for r in body]
    t_up = st.mean(col("t_up"))
    return {
        "t_down": f"{st.mean(col('t_down')):.3f}", "t_up": f"{t_up:.3f}",
        "t_round": f"{st.mean(col('t_round')):.3f}",
        "t_round_sd": f"{st.stdev(col('t_round')) if len(body) > 1 else 0:.3f}",
        "thr_mbps": f"{n * size_up * 8 / t_up / 1e6:.1f}",
    }


def tta(rows):
    """(số vòng, thời gian) để độ chính xác lần đầu đạt TARGET; None nếu không đạt."""
    t = 0.0
    for r in rows:
        t += float(r["t_round"])
        if r["acc"] and float(r["acc"]) >= TARGET:
            return int(r["round"]), t
    return None, None


def ping(tag):
    """RTT trung vị và lớn nhất (ms) đo bằng ping trong suốt lần chạy."""
    path = os.path.join(RES, f"{tag}_ping.txt")
    if not os.path.exists(path):
        return "", ""
    rtts = [float(x) for x in re.findall(r"time=([\d.]+)", open(path).read())]
    return (f"{st.median(rtts):.1f}", f"{max(rtts):.1f}") if rtts else ("", "")


def write(name, rows):
    if not rows:
        return
    with open(os.path.join(OUT, name), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("wrote", name)


def fl_row(tag, rows):
    n, size = int(rows[0]["n"]), int(rows[0]["size"])
    k, t = tta(rows)
    med, mx = ping(tag)
    row = stats(rows, n, size)
    row.update({"rounds_to_target": k or "", "tta_s": f"{t:.1f}" if t else "",
                "acc_final": rows[-1]["acc"], "rtt_med_ms": med, "rtt_max_ms": mx})
    # Đường cong độ chính xác theo thời gian thực cho biểu đồ hội tụ
    cum, curve = 0.0, [{"round": 0, "time": 0.0, "acc": ""}]
    for r in rows:
        cum += float(r["t_round"])
        curve.append({"round": r["round"], "time": f"{cum:.2f}", "acc": r["acc"]})
    curve[0]["acc"] = "0.092"     # độ chính xác của mô hình khởi tạo (model.py)
    if tag.startswith("Q2"):
        write(f"q2_curve_{tag}.csv", curve)
    return row


def main():
    groups, q1, q2l, q2d = {}, [], [], []
    for path in sorted(glob.glob(os.path.join(RES, "*.csv"))):
        tag = os.path.basename(path)[:-4]
        rows = load(path)
        if not rows:
            continue
        if m := re.match(r"(K.+)_n(\d)$", tag):
            name, n = m.group(1), int(m.group(2))
            r = {"n": n, **stats(rows, n, UP_SIZE.get(name, 10 ** 7))}
            groups.setdefault(name, []).append(r)
        elif m := re.match(r"Q1_bw([\d.]+)$", tag):
            q1.append({"bw": float(m.group(1)), **fl_row(tag, rows)})
        elif m := re.match(r"Q2_loss([\d.]+)$", tag):
            q2l.append({"loss": float(m.group(1)), **fl_row(tag, rows)})
        elif m := re.match(r"Q2_d(\d+)_l([\d.]+)$", tag):
            q2d.append({"delay": int(m.group(1)), "loss": float(m.group(2)), **fl_row(tag, rows)})
    for name, items in groups.items():
        write(f"measured_{name}.csv", sorted(items, key=lambda r: r["n"]))
    write("q1_bw.csv", sorted(q1, key=lambda r: r["bw"]))
    write("q2_loss.csv", sorted(q2l, key=lambda r: r["loss"]))
    write("q2_delay.csv", sorted(q2d, key=lambda r: (r["loss"], r["delay"])))


if __name__ == "__main__":
    main()
