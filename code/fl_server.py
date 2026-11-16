#!/usr/bin/env python3
"""Aggregation Server: phát mô hình toàn cục, chờ đủ N bản cập nhật, ghi log thời gian.

Ví dụ: python3 fl_server.py --clients 4 --rounds 10 --size 10000000 --out log.csv
"""
import argparse
import csv
import socket
import threading
import time

from flproto import ACK, BYE, GLOBAL, HELLO, UPDATE, recv_msg, send_msg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5000)
    ap.add_argument("--clients", type=int, required=True)
    ap.add_argument("--rounds", type=int, default=10)
    ap.add_argument("--size", type=int, default=10_000_000, help="byte mô hình toàn cục")
    ap.add_argument("--train", type=float, default=1.0, help="thời gian train của client (s)")
    ap.add_argument("--out", default="server_log.csv")
    a = ap.parse_args()

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", a.port))
    srv.listen(a.clients)

    conns = {}
    while len(conns) < a.clients:
        c, _ = srv.accept()
        c.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        mtype, _, node, _ = recv_msg(c)
        assert mtype == HELLO
        conns[node] = c
    print(f"[server] {len(conns)} clients joined", flush=True)

    with open(a.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["round", "n", "size", "t_down", "t_up", "t_round"])
        for r in range(1, a.rounds + 1):
            done_down, got_up = {}, {}
            t0 = time.perf_counter()

            def serve(node, c):
                # sendall() trả về khi dữ liệu mới vào send buffer, nên t_down lấy
                # theo ACK nhỏ client gửi lại khi đã nhận đủ mô hình
                send_msg(c, GLOBAL, r, 0, a.size)
                mtype, rnd, nid, _ = recv_msg(c)
                assert mtype == ACK and rnd == r and nid == node
                done_down[node] = time.perf_counter() - t0
                mtype, rnd, nid, _ = recv_msg(c)
                assert mtype == UPDATE and rnd == r and nid == node
                got_up[node] = time.perf_counter() - t0

            ths = [threading.Thread(target=serve, args=kv) for kv in conns.items()]
            for t in ths:
                t.start()
            for t in ths:
                t.join()
            # Aggregation (FedAvg) không tính thật: chỉ là phép cộng có trọng số, chi phí ~0
            for c in conns.values():
                send_msg(c, ACK, r, 0)
            t_round = time.perf_counter() - t0
            t_down = max(done_down.values())
            # Pha upload: từ lúc client đầu tiên train xong tới khi bản cập nhật cuối tới
            t_up = max(got_up.values()) - min(done_down.values()) - a.train
            w.writerow([r, a.clients, a.size, f"{t_down:.4f}", f"{t_up:.4f}", f"{t_round:.4f}"])
            f.flush()
            print(f"[server] round {r}: {t_round:.3f} s", flush=True)

    for c in conns.values():
        send_msg(c, BYE, 0, 0)
        c.close()
    srv.close()


if __name__ == "__main__":
    main()
