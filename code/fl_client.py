#!/usr/bin/env python3
"""Edge Node: nhận mô hình toàn cục, huấn luyện cục bộ, gửi bản cập nhật.

Hai chế độ:
  Đo mạng thuần : python3 fl_client.py --server 10.0.1.100 --id 1 --size 10000000 --train 1.0
                  ("huấn luyện" bằng sleep; --size là kích thước bản cập nhật, 1000000 khi nén 1/10)
  FedAvg thật   : python3 fl_client.py --server 10.0.2.200 --id 1 --clients 4 --fedavg
                  (SGD trên phần dữ liệu của node, rồi đệm cho đủ --train giây để T_train cố định)
"""
import argparse
import socket
import sys
import time

from flproto import ACK, BYE, GLOBAL, HELLO, UPDATE, recv_msg, send_msg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", required=True)
    ap.add_argument("--port", type=int, default=5000)
    ap.add_argument("--id", type=int, required=True)
    ap.add_argument("--size", type=int, default=10_000_000)
    ap.add_argument("--train", type=float, default=1.0)
    ap.add_argument("--clients", type=int, default=1, help="tổng số node, để chia dữ liệu")
    ap.add_argument("--fedavg", action="store_true")
    a = ap.parse_args()

    if a.fedavg:
        import model
        (x, y), _ = model.make_dataset()
        x, y = model.partition(x, y, a.clients, a.id)

    for _ in range(50):  # server có thể chưa listen kịp
        try:
            s = socket.create_connection((a.server, a.port))
            break
        except OSError:
            time.sleep(0.2)
    else:
        raise SystemExit("cannot connect")
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    send_msg(s, HELLO, 0, a.id)

    while True:
        mtype, rnd, _, _, data = recv_msg(s, keep=a.fedavg)
        if mtype == BYE:
            break
        if mtype == GLOBAL:
            send_msg(s, ACK, rnd, a.id)
            t0 = time.perf_counter()
            if a.fedavg:
                local = model.sgd_train(model.from_bytes(data), x, y, seed=rnd * 100 + a.id)
                payload = model.to_bytes(local)
            else:
                payload = None
            spent = time.perf_counter() - t0
            if spent > a.train:
                print(f"[client {a.id}] round {rnd}: train {spent:.2f} s > {a.train} s",
                      file=sys.stderr, flush=True)
            time.sleep(max(0.0, a.train - spent))   # cố định T_train cho mọi vòng
            send_msg(s, UPDATE, rnd, a.id, a.size, payload)
        # ACK của server: kết thúc vòng, chờ vòng sau
    s.close()


if __name__ == "__main__":
    main()
