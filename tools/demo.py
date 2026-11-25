#!/usr/bin/env python3
"""Demo quay video: dựng topo một lần, kiểm tra mạng, rồi chạy FedAvg dưới 4 điều kiện WAN.

  sudo python3 tools/demo.py            # dừng chờ Enter trước mỗi bước (để vừa nói vừa quay)
  sudo python3 tools/demo.py --auto     # chạy một mạch, không dừng
  sudo python3 tools/demo.py --pause 5  # chạy một mạch, mỗi bước dừng 5 giây để kịp nói (quay để trình chiếu)
  sudo python3 tools/demo.py --rounds 2 # bớt số vòng cho nhanh hơn
  sudo python3 tools/demo.py --pause 5 --web   # thêm sơ đồ trực quan tại http://localhost:8765

Điều kiện WAN được đổi bằng tc ngay trên link r1-s2 đang chạy. Giới hạn netem = 200 gói hàng đợi
+ số gói đang bay, vì netem đếm cả gói đang bị giữ để tạo trễ.
"""
import argparse
import http.server
import json
import math
import os
import re
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CODE = os.path.abspath(os.path.join(HERE, "..", "code"))
sys.path.insert(0, CODE)

from mininet.log import setLogLevel  # noqa: E402

from topo import make_net  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--auto", action="store_true", help="không dừng chờ Enter")
ap.add_argument("--rounds", type=int, default=3)
ap.add_argument("--pause", type=float, default=None, help="tự chạy, dừng số giây này trước mỗi bước")
ap.add_argument("--web", action="store_true", help="mở sơ đồ trực quan tại cổng 8765")
ap.add_argument("--hold", type=float, default=20, help="với --web: giữ trang thêm số giây này sau khi xong")
a = ap.parse_args()

STATE = {"step": "Đang chờ bắt đầu", "wan": None, "rate": {}, "pings": [], "probes": [], "drop": None,
         "case": None, "rounds": [], "nround": a.rounds, "results": [], "ncase": 4}
# Link -> (giao diện ở namespace gốc, True nếu gói server -> Edge Node đi RA khỏi giao diện đó)
PORTS = {**{f"h{i}": (f"s1-eth{i}", True) for i in range(1, 7)},
         "agg": ("s1-eth7", False), "gw": ("s1-eth8", False), "wan": ("s2-eth1", True), "cloud": ("s2-eth2", False)}


def counters():
    out = {}
    for name, (dev, down_is_tx) in PORTS.items():
        try:
            rx, tx = (int(open(f"/sys/class/net/{dev}/statistics/{k}_bytes").read()) for k in ("rx", "tx"))
        except OSError:
            continue
        out[name] = (tx, rx) if down_is_tx else (rx, tx)
    return out


def sampler():
    """Đo lưu lượng thật (Mbps) của từng link từ bộ đếm byte của nhân, mỗi 0,25 giây."""
    old, t_old = counters(), time.time()
    while True:
        time.sleep(0.25)
        new, t = counters(), time.time()
        STATE["rate"] = {k: [max(0, new[k][i] - old[k][i]) * 8e-6 / (t - t_old) for i in (0, 1)]
                         for k in new if k in old}
        old, t_old = new, t


class View(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/state"):
            body, kind = json.dumps(STATE).encode(), "application/json"
        elif self.path in ("/", "/index.html"):
            body, kind = open(os.path.join(HERE, "demo_view.html"), "rb").read(), "text/html; charset=utf-8"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass

N = 4
B, C, G, Y, R, X = "\033[1m", "\033[36m", "\033[32m", "\033[33m", "\033[31m", "\033[0m"
T0 = time.time()

# (tên hiển thị, băng thông Mbps, trễ một chiều ms, mất gói %)
CASES = [
    ("Chuẩn:          100 Mbps, trễ 20 ms, mất gói 0%", 100, 20, 0),
    ("Băng thông hẹp:  10 Mbps, trễ 20 ms, mất gói 0%", 10, 20, 0),
    ("Mất gói:        100 Mbps, trễ 20 ms, mất gói 1%", 100, 20, 1),
    ("Đường xa:       100 Mbps, trễ 100 ms, mất gói 0%", 100, 100, 0),
]

SHORT = ["Chuẩn", "Băng thông 10 Mbps", "Mất gói 1%", "Trễ 100 ms"]


def title(text):
    STATE["step"] = text
    print(f"\n{B}{C}{'=' * 78}\n  {text}\n{'=' * 78}{X}", flush=True)
    if a.pause is not None:
        time.sleep(a.pause)
    elif not a.auto:
        input(f"{Y}  [Enter để chạy]{X} ")


def show(node, cmd):
    """In lệnh như gõ trong Mininet CLI, rồi in kết quả."""
    print(f"{B}mininet> {node.name} {cmd}{X}", flush=True)
    out = node.cmd(cmd).strip()
    print(out, flush=True)
    return out


def set_wan(net, bw, delay, loss):
    """Đổi băng thông, trễ, mất gói của chặng WAN r1-s2 trên cả hai đầu link."""
    STATE["wan"] = {"bw": bw, "delay": delay, "loss": loss}
    limit = 200 + math.ceil(bw * 1e6 * delay / 1000 / 8 / 1514)
    for link in net.links:
        i1, i2 = link.intf1, link.intf2
        if {i1.node.name, i2.node.name} != {"r1", "s2"}:
            continue
        for i in (i1, i2):
            netem = f"limit {limit} delay {delay}ms" + (f" loss {loss}%" if loss else "")
            err = i.node.cmd(f"tc class change dev {i.name} parent 5: classid 5:1 htb rate {bw}Mbit burst 15k; "
                             f"tc qdisc change dev {i.name} parent 5:1 handle 10: netem {netem}").strip()
            err = "\n".join(l for l in err.splitlines() if "quantum of class" not in l)   # cảnh báo vô hại của HTB
            if err:
                raise RuntimeError(f"tc lỗi trên {i.name}: {err}")


def run_fl(net, rounds):
    """Chạy fl_server trên cloud và N client, in log từng vòng; trả về thời gian các vòng."""
    cloud = net.get("cloud")
    env = {**os.environ, "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    srv = cloud.popen(["python3", "-u", "fl_server.py", "--clients", str(N), "--rounds", str(rounds),
                       "--fedavg", "--out", "/tmp/demo.csv"],
                      cwd=CODE, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    cls = [net.get(f"h{i}").popen(["python3", "fl_client.py", "--server", cloud.IP(), "--id", str(i),
                                   "--clients", str(N), "--fedavg"],
                                  cwd=CODE, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
           for i in range(1, N + 1)]
    times, acc = [], None
    for line in srv.stdout:
        m = re.search(r"round (\d+): ([\d.]+) s ([\d.]+)", line)
        if m:
            times.append(float(m.group(2)))
            acc = float(m.group(3))
            STATE["rounds"] = STATE["rounds"] + [{"t": times[-1], "acc": acc}]
            print(f"  {G}vòng {m.group(1)}{X}: {B}{times[-1]:6.2f} s{X}   độ chính xác {100 * acc:.1f}%", flush=True)
        else:
            print("  " + line.rstrip(), flush=True)
    srv.wait(timeout=30)
    for c in cls:
        try:
            c.wait(timeout=10)
        except subprocess.TimeoutExpired:
            c.kill()
    if len(times) != rounds:
        raise RuntimeError("server dừng sớm, xem thông báo phía trên")
    return times, acc


def main():
    if os.geteuid() != 0:
        sys.exit("Cần chạy bằng sudo")
    setLogLevel("critical")
    if a.web:
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8765), View)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        print(f"{Y}Sơ đồ trực quan: http://localhost:8765{X}", flush=True)
    title("BƯỚC 1. Dựng topo Edge-Cloud (6 Edge Node, Edge Aggregator, Gateway r1, Cloud)")
    net = make_net(n=6, bw_wan=100, wan_delay="20ms", loss=0)
    try:
        net.start()
        for node in net.hosts + net.switches:
            for intf in node.intfList():
                if intf.name != "lo":
                    node.cmd(f"ethtool -K {intf.name} tso off gso off gro off")
        set_wan(net, 100, 20, 0)
        if a.web:
            threading.Thread(target=sampler, daemon=True).start()
        for link in net.links:
            print(f"  {link.intf1.name:10s} <-> {link.intf2.name}")
        h1, r1, agg, cloud = net.get("h1", "r1", "agg", "cloud")
        h1.cmd("ping -c 1 -W 1 10.0.1.100; ping -c 1 -W 1 10.0.2.200")   # phân giải ARP trước

        title("BƯỚC 2. RTT: tới Edge Aggregator khoảng 4 ms, tới Cloud khoảng 44 ms")
        for to, ip, want in (("Edge Aggregator", "10.0.1.100", "4 ms"), ("Cloud", "10.0.2.200", "44 ms")):
            m = re.search(r"= [\d.]+/([\d.]+)/", show(h1, f"ping -c 4 -i 0.3 {ip} | tail -2"))
            if m:
                STATE["pings"] = STATE["pings"] + [{"to": to, "avg": float(m.group(1)), "want": want}]

        title("BƯỚC 3. Firewall trên r1: chỉ TCP/5000 tới Cloud được đi qua")
        cloud.cmd("python3 -m http.server 5000 >/dev/null 2>&1 & echo $! > /tmp/demo_5000.pid")
        cloud.cmd("python3 -m http.server 22 >/dev/null 2>&1 & echo $! > /tmp/demo_22.pid")
        time.sleep(1.5)
        for port, want in ((5000, "ĐƯỢC PHÉP"), (22, "BỊ CHẶN")):
            probe = f"timeout 2 bash -c '</dev/tcp/10.0.2.200/{port}' 2>/dev/null && echo mo || echo chan"
            res = h1.cmd(probe).strip().split()[-1]
            ok = (res == "mo") == (port == 5000)
            STATE["probes"] = STATE["probes"] + [{"port": port, "open": res == "mo"}]
            mark = f"{G}đúng mong đợi{X}" if ok else f"{R}SAI MONG ĐỢI{X}"
            print(f"  h1 -> cloud TCP/{port}: {B}{'kết nối được' if res == 'mo' else 'hết thời gian chờ'}{X} "
                  f"({want}, {mark})", flush=True)
        cloud.cmd("kill $(cat /tmp/demo_5000.pid /tmp/demo_22.pid) 2>/dev/null")
        time.sleep(0.5)
        m = re.search(r"policy DROP (\d+) packets", show(r1, "iptables -L FORWARD -v -n"))
        STATE["drop"] = int(m.group(1)) if m else None

        results = []
        for k, (name, bw, delay, loss) in enumerate(CASES, 1):
            title(f"BƯỚC 4.{k}. FedAvg 4 nút, {a.rounds} vòng. {name}")
            set_wan(net, bw, delay, loss)
            STATE["case"], STATE["rounds"] = " ".join(name.split()), []
            print(f"{B}tc trên r1-eth1:{X} " + r1.cmd("tc qdisc show dev r1-eth1 | grep netem").strip())
            times, acc = run_fl(net, a.rounds)
            body = times[1:] or times                     # bỏ vòng 1 như trong báo cáo
            results.append((name, sum(body) / len(body), acc))
            short = SHORT[k - 1]
            if k < len(CASES):
                STATE["results"] = STATE["results"] + [{"short": short, "t": results[-1][1], "acc": acc}]

        title("KẾT QUẢ: cùng mô hình, cùng số vòng, chỉ đổi điều kiện mạng")
        base = results[0][1]
        STATE["results"] = STATE["results"] + [{"short": SHORT[-1], "t": results[-1][1], "acc": results[-1][2]}]
        print(f"  {'Điều kiện WAN':50s} {'s/vòng':>8s} {'so với chuẩn':>13s} {'độ chính xác':>13s}")
        for name, t, acc in results:
            print(f"  {name:50s} {t:8.2f} {t / base:12.1f}x {100 * acc:12.1f}%")
        print(f"\n  Thời gian demo: {time.time() - T0:.0f} s")
        if a.web:
            time.sleep(a.hold)
    finally:
        net.stop()


if __name__ == "__main__":
    main()
