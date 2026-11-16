#!/usr/bin/env python3
"""Edge Node: nhận mô hình toàn cục, "huấn luyện" bằng sleep, gửi bản cập nhật.

Ví dụ: python3 fl_client.py --server 10.0.0.100 --id 1 --size 10000000 --train 1.0
--size là kích thước bản cập nhật gửi lên (1000000 cho kịch bản nén 1/10).
"""
import argparse
import socket
import time

from flproto import ACK, BYE, GLOBAL, HELLO, UPDATE, recv_msg, send_msg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", required=True)
    ap.add_argument("--port", type=int, default=5000)
    ap.add_argument("--id", type=int, required=True)
    ap.add_argument("--size", type=int, default=10_000_000)
    ap.add_argument("--train", type=float, default=1.0)
    a = ap.parse_args()

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
        mtype, rnd, _, _ = recv_msg(s)
        if mtype == BYE:
            break
        if mtype == GLOBAL:
            send_msg(s, ACK, rnd, a.id)
            time.sleep(a.train)          # mô phỏng huấn luyện cục bộ
            send_msg(s, UPDATE, rnd, a.id, a.size)
        # ACK của server: kết thúc vòng, chờ vòng sau
    s.close()


if __name__ == "__main__":
    main()
