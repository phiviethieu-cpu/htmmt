#!/usr/bin/env python3
"""Aggregation Server: phát mô hình toàn cục, chờ đủ N bản cập nhật, tổng hợp FedAvg, ghi log.

Hai chế độ:
  Đo mạng thuần : python3 fl_server.py --clients 4 --rounds 10 --size 10000000 --out log.csv
                  (payload là byte 0 kích thước --size, không huấn luyện thật)
  FedAvg thật   : python3 fl_server.py --clients 4 --rounds 20 --fedavg --out log.csv
                  (payload là trọng số MLP của model.py, đo thêm độ chính xác sau mỗi vòng)
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
    ap.add_argument("--fedavg", action="store_true", help="truyền trọng số thật và tổng hợp FedAvg")
    ap.add_argument("--out", default="server_log.csv")
    a = ap.parse_args()

    if a.fedavg:
        import model
        _, (x_test, y_test) = model.make_dataset()
        weights = model.init_params()

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", a.port))
    srv.listen(a.clients)

    conns = {}
    while len(conns) < a.clients:
        c, _ = srv.accept()
        c.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        mtype, _, node, _, _ = recv_msg(c)
        assert mtype == HELLO
        conns[node] = c
    print(f"[server] {len(conns)} clients joined", flush=True)

    with open(a.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["round", "n", "size", "t_down", "t_up", "t_round", "acc", "loss"])
        for r in range(1, a.rounds + 1):
            done_down, got_up, updates = {}, {}, {}
            payload = model.to_bytes(weights) if a.fedavg else None
            size = len(payload) if a.fedavg else a.size
            t0 = time.perf_counter()

            def serve(node, c):
                # sendall() trả về khi dữ liệu mới vào send buffer, nên t_down lấy
                # theo ACK nhỏ client gửi lại khi đã nhận đủ mô hình
                send_msg(c, GLOBAL, r, 0, size, payload)
                mtype, rnd, nid, _, _ = recv_msg(c)
                assert mtype == ACK and rnd == r and nid == node
                done_down[node] = time.perf_counter() - t0
                mtype, rnd, nid, _, data = recv_msg(c, keep=a.fedavg)
                assert mtype == UPDATE and rnd == r and nid == node
                got_up[node] = time.perf_counter() - t0
                updates[node] = data

            ths = [threading.Thread(target=serve, args=kv) for kv in conns.items()]
            for t in ths:
                t.start()
            for t in ths:
                t.join()
            acc = loss = ""
            if a.fedavg:
                # FedAvg: các node giữ số mẫu bằng nhau (model.partition) nên trọng số bằng nhau
                ups = [(model.from_bytes(updates[k]), 1) for k in sorted(updates)]
                weights = model.fedavg(ups)
            for c in conns.values():
                send_msg(c, ACK, r, 0)
            t_round = time.perf_counter() - t0
            if a.fedavg:
                # Đánh giá trên tập kiểm tra sau khi đã chốt t_round, không tính vào thời gian vòng
                acc, loss = model.evaluate(weights, x_test, y_test)
                acc, loss = f"{acc:.4f}", f"{loss:.4f}"
            t_down = max(done_down.values())
            # Pha upload: từ lúc client đầu tiên train xong tới khi bản cập nhật cuối tới
            t_up = max(got_up.values()) - min(done_down.values()) - a.train
            w.writerow([r, a.clients, size, f"{t_down:.4f}", f"{t_up:.4f}", f"{t_round:.4f}",
                        acc, loss])
            f.flush()
            print(f"[server] round {r}: {t_round:.3f} s {acc}", flush=True)

    for c in conns.values():
        send_msg(c, BYE, 0, 0)
        c.close()
    srv.close()


if __name__ == "__main__":
    main()
