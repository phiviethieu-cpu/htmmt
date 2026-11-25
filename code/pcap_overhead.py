#!/usr/bin/env python3
"""Đo overhead giao thức và truyền lại từ file pcap của các lần chạy Q2 (không cần thư viện ngoài).

Với mỗi tag, lấy góc nhìn "phía gửi" của từng chiều để thấy cả gói bị mất rồi gửi lại:
  chiều xuống (server -> client): <tag>_srv.pcap, gói có cổng nguồn 5000
  chiều lên   (client -> server): <tag>_r1.pcap  (giao diện LAN của gateway), cổng đích 5000

  python3 pcap_overhead.py               # đọc $FL_RES hoặc results/, ghi data/q3_overhead.csv
"""
import csv
import glob
import os
import re
import struct

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.environ.get("FL_RES", os.path.join(HERE, "..", "results"))
OUT = os.path.join(HERE, "..", "data")
PORT = 5000
MODEL = 1204264            # byte trọng số mỗi bản (model.model_bytes())


def packets(path):
    """Duyệt file pcap (Ethernet): trả về (độ dài trên dây, luồng, sport, seq, flags, payload)."""
    with open(path, "rb") as f:
        magic = f.read(24)[:4]
        endian = "<" if magic in (b"\xd4\xc3\xb2\xa1", b"\x4d\x3c\xb2\xa1") else ">"
        rec = struct.Struct(endian + "IIII")
        while hdr := f.read(16):
            _, _, incl, orig = rec.unpack(hdr)
            data = f.read(incl)
            if len(data) < 34 or data[12:14] != b"\x08\x00":
                continue
            ihl = (data[14] & 0x0F) * 4
            total = struct.unpack("!H", data[16:18])[0]
            t = 14 + ihl
            sport, dport, seq = struct.unpack("!HHI", data[t:t + 8])
            thl = (data[t + 12] >> 4) * 4
            flags = data[t + 13]
            flow = (data[26:30], data[30:34], sport, dport)   # IP nguồn, IP đích, hai cổng
            yield orig, flow, sport, seq, flags, total - ihl - thl


def direction(path, want_sport):
    """Thống kê một chiều: tổng byte trên dây, byte payload TCP, gói ACK thuần, truyền lại."""
    s = dict(frames=0, wire=0, payload=0, ack_frames=0, ack_wire=0, retx_frames=0, retx_bytes=0,
             syn=0)
    # Thứ tự gói trong file bắt có thể bị đảo nhẹ, nên không xét từng gói. Mỗi luồng ghi seq
    # đầu tiên và seq cao nhất: byte duy nhất = cao nhất - đầu tiên; phần payload vượt quá là
    # byte gửi lại. Số gói gửi lại đếm theo seq bắt đầu đã gặp trước đó.
    first, high, seen = {}, {}, set()
    M = 0xFFFFFFFF
    for orig, key, sport, seq, flags, plen in packets(path):
        if (sport == PORT) != want_sport:
            continue
        s["frames"] += 1
        s["wire"] += orig
        s["syn"] += bool(flags & 0x02)
        if plen <= 0:
            s["ack_frames"] += 1
            s["ack_wire"] += orig
            continue
        s["payload"] += plen
        end = (seq + plen) & M
        if key not in first:
            first[key], high[key] = seq, end
        else:
            if ((first[key] - seq) & M) < 2 ** 31:        # seq trước mốc đầu (gói bị đảo)
                first[key] = seq
            if ((end - high[key]) & M) < 2 ** 31:
                high[key] = end
        if (key, seq) in seen:
            s["retx_frames"] += 1
        seen.add((key, seq))
    unique = sum((high[k] - first[k]) & M for k in first)
    s["retx_bytes"] = s["payload"] - unique
    return s


def main():
    rows = []
    for srv in sorted(glob.glob(os.path.join(RES, "Q2_*_srv.pcap"))):
        tag = os.path.basename(srv)[:-9]
        r1 = os.path.join(RES, f"{tag}_r1.pcap")
        log = os.path.join(RES, f"{tag}.csv")
        if not (os.path.exists(r1) and os.path.exists(log)):
            continue
        rounds = sum(1 for _ in open(log)) - 1
        n = int(next(csv.DictReader(open(log)))["n"])
        down, up = direction(srv, True), direction(r1, False)
        useful = 2 * n * rounds * MODEL            # trọng số GLOBAL + UPDATE thực sự cần chuyển
        wire = down["wire"] + up["wire"]
        m = re.match(r"Q2_(?:loss([\d.]+)|d(\d+)_l([\d.]+))$", tag)
        row = {
            "tag": tag,
            "loss": m.group(1) or m.group(3), "delay": m.group(2) or 20,
            "rounds": rounds, "useful_mb": f"{useful / 1e6:.1f}",
            "wire_mb": f"{wire / 1e6:.1f}",
            "efficiency": f"{useful / wire:.4f}",
            "hdr_pct": f"{100 * (wire - down['payload'] - up['payload']) / wire:.2f}",
            "ack_pct": f"{100 * (down['ack_wire'] + up['ack_wire']) / wire:.2f}",
            "retx_down_pct": f"{100 * down['retx_bytes'] / max(down['payload'], 1):.2f}",
            "retx_up_pct": f"{100 * up['retx_bytes'] / max(up['payload'], 1):.2f}",
            "retx_frames": down["retx_frames"] + up["retx_frames"],
            "syn": down["syn"] + up["syn"],
        }
        rows.append(row)
        print(row, flush=True)
    if rows:
        with open(os.path.join(OUT, "q3_overhead.csv"), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)


if __name__ == "__main__":
    main()
