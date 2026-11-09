"""
MQTT 3.1.1 Broker tích hợp sẵn bằng Python thuần (asyncio) - KHÔNG CẦN DOCKER HAY MOSQUITTO.
Hỗ trợ đầy đủ:
- ESP32 PubSubClient & Python Paho-MQTT
- CONNECT / CONNACK / PUBLISH / PUBACK / SUBSCRIBE / SUBACK / PINGREQ / PINGRESP / DISCONNECT
- Wildcard topics ('+' và '#'), QoS 0 & QoS 1, Retained messages và Last Will (LWT).

Chạy độc lập:
    python broker.py
(Hoặc tự động được bật khi chạy `uvicorn server_mqtt_sample:app` nếu cổng 1883 chưa có Mosquitto).
"""

from __future__ import annotations

import asyncio
import logging
import socket
import struct
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("mqtt_broker")


def topic_matches(sub_filter: str, topic: str) -> bool:
    """Kiểm tra topic có khớp với MQTT subscription filter (hỗ trợ '+' và '#') hay không."""
    if sub_filter == "#" or sub_filter == topic:
        return True
    f_parts = sub_filter.split("/")
    t_parts = topic.split("/")
    for i, fp in enumerate(f_parts):
        if fp == "#":
            return True
        if i >= len(t_parts):
            return False
        if fp != "+" and fp != t_parts[i]:
            return False
    return len(f_parts) == len(t_parts)


def encode_remaining_length(length: int) -> bytes:
    out = bytearray()
    while True:
        encoded = length % 128
        length //= 128
        if length > 0:
            encoded |= 0x80
        out.append(encoded)
        if length == 0:
            break
    return bytes(out)


async def read_remaining_length(reader: asyncio.StreamReader) -> int:
    multiplier = 1
    value = 0
    while True:
        b = await reader.readexactly(1)
        encoded = b[0]
        value += (encoded & 127) * multiplier
        if (encoded & 128) == 0:
            break
        multiplier *= 128
        if multiplier > 128 * 128 * 128:
            raise ValueError("Malformed Remaining Length")
    return value


def read_utf8_string(buf: bytes, offset: int) -> Tuple[str, int]:
    str_len = struct.unpack_from("!H", buf, offset)[0]
    offset += 2
    s = buf[offset : offset + str_len].decode("utf-8", errors="replace")
    return s, offset + str_len


def read_bytes_field(buf: bytes, offset: int) -> Tuple[bytes, int]:
    b_len = struct.unpack_from("!H", buf, offset)[0]
    offset += 2
    return buf[offset : offset + b_len], offset + b_len


def encode_utf8_string(s: str) -> bytes:
    raw = s.encode("utf-8")
    return struct.pack("!H", len(raw)) + raw


@dataclass
class ClientSession:
    client_id: str
    writer: asyncio.StreamWriter
    subscriptions: Dict[str, int] = field(default_factory=dict)
    will_topic: Optional[str] = None
    will_payload: bytes = b""
    will_qos: int = 0
    will_retain: bool = False
    clean_disconnect: bool = False
    next_packet_id: int = 1


class EmbeddedMqttBroker:
    """MQTT 3.1.1 Broker chạy trực tiếp trên Python asyncio."""

    def __init__(self, host: str = "0.0.0.0", port: int = 1883) -> None:
        self.host = host
        self.port = port
        self.clients: Dict[str, ClientSession] = {}
        self.retained_messages: Dict[str, Tuple[bytes, int]] = {}
        self._server: Optional[asyncio.AbstractServer] = None

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle_client, self.host, self.port)
        lan_ips = self._get_lan_ips()
        logger.info("==============================================================")
        logger.info("MQTT Broker (Python Built-in) đang lắng nghe tại %s:%d", self.host, self.port)
        logger.info("Địa chỉ IP LAN cho ESP32 (MQTT_HOST trong secrets.h): %s", ", ".join(lan_ips))
        logger.info("==============================================================")

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    @staticmethod
    def _get_lan_ips() -> List[str]:
        ips: Set[str] = {"127.0.0.1"}
        try:
            hostname = socket.gethostname()
            for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
                ip = info[4][0]
                if not ip.startswith("127."):
                    ips.add(ip)
        except Exception:
            pass
        return sorted(ips)

    async def _send_publish(
        self,
        session: ClientSession,
        topic: str,
        payload: bytes,
        qos: int = 0,
        retain: bool = False,
    ) -> None:
        flags = (1 if retain else 0) | ((qos & 0x03) << 1)
        header = bytes([0x30 | flags])
        var_header = encode_utf8_string(topic)
        if qos > 0:
            pkt_id = session.next_packet_id
            session.next_packet_id = (session.next_packet_id % 65535) + 1
            var_header += struct.pack("!H", pkt_id)
        body = var_header + payload
        packet = header + encode_remaining_length(len(body)) + body
        try:
            session.writer.write(packet)
            await session.writer.drain()
        except Exception:
            pass

    async def _route_message(self, topic: str, payload: bytes, qos: int, retain: bool) -> None:
        if retain:
            if payload:
                self.retained_messages[topic] = (payload, qos)
            else:
                self.retained_messages.pop(topic, None)

        for session in list(self.clients.values()):
            matched_qos: Optional[int] = None
            for sub_filter, sub_qos in session.subscriptions.items():
                if topic_matches(sub_filter, topic):
                    matched_qos = max(matched_qos or 0, min(qos, sub_qos))
            if matched_qos is not None:
                await self._send_publish(session, topic, payload, qos=matched_qos, retain=False)

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        peer = writer.get_extra_info("peername")
        session: Optional[ClientSession] = None

        try:
            while True:
                first_byte = await reader.read(1)
                if not first_byte:
                    break
                packet_type = (first_byte[0] & 0xF0) >> 4
                flags = first_byte[0] & 0x0F
                rem_len = await read_remaining_length(reader)
                body = await reader.readexactly(rem_len) if rem_len > 0 else b""

                # 1. CONNECT
                if packet_type == 1:
                    _, offset = read_utf8_string(body, 0)  # Protocol Name
                    _proto_level = body[offset]
                    conn_flags = body[offset + 1]
                    _keepalive = struct.unpack_from("!H", body, offset + 2)[0]
                    offset += 4

                    client_id, offset = read_utf8_string(body, offset)
                    if not client_id:
                        client_id = f"anon_{id(writer)}"

                    will_flag = bool(conn_flags & 0x04)
                    will_qos = (conn_flags >> 3) & 0x03
                    will_retain = bool(conn_flags & 0x20)
                    will_topic = None
                    will_payload = b""

                    if will_flag:
                        will_topic, offset = read_utf8_string(body, offset)
                        will_payload, offset = read_bytes_field(body, offset)

                    # Đóng phiên cũ nếu trùng client_id
                    old = self.clients.pop(client_id, None)
                    if old is not None and old.writer is not writer:
                        old.clean_disconnect = True
                        try:
                            old.writer.close()
                        except Exception:
                            pass

                    session = ClientSession(
                        client_id=client_id,
                        writer=writer,
                        will_topic=will_topic,
                        will_payload=will_payload,
                        will_qos=will_qos,
                        will_retain=will_retain,
                    )
                    self.clients[client_id] = session
                    logger.info("[Broker] Client connected: %s từ %s", client_id, peer)

                    # Gửi CONNACK (0x20 0x02 0x00 0x00)
                    writer.write(b"\x20\x02\x00\x00")
                    await writer.drain()

                # 3. PUBLISH
                elif packet_type == 3 and session is not None:
                    qos = (flags >> 1) & 0x03
                    retain = bool(flags & 0x01)
                    topic, offset = read_utf8_string(body, 0)
                    pkt_id = None
                    if qos > 0:
                        pkt_id = struct.unpack_from("!H", body, offset)[0]
                        offset += 2
                    payload = body[offset:]

                    if qos == 1 and pkt_id is not None:
                        writer.write(struct.pack("!BBH", 0x40, 2, pkt_id))
                        await writer.drain()

                    await self._route_message(topic, payload, qos=qos, retain=retain)

                # 4. PUBACK
                elif packet_type == 4:
                    pass

                # 8. SUBSCRIBE
                elif packet_type == 8 and session is not None:
                    pkt_id = struct.unpack_from("!H", body, 0)[0]
                    offset = 2
                    granted_qos = bytearray()
                    new_filters: List[Tuple[str, int]] = []

                    while offset < len(body):
                        sub_filter, offset = read_utf8_string(body, offset)
                        req_qos = body[offset] & 0x03
                        offset += 1
                        session.subscriptions[sub_filter] = min(req_qos, 1)
                        granted_qos.append(min(req_qos, 1))
                        new_filters.append((sub_filter, min(req_qos, 1)))

                    suback_body = struct.pack("!H", pkt_id) + bytes(granted_qos)
                    writer.write(b"\x90" + encode_remaining_length(len(suback_body)) + suback_body)
                    await writer.drain()

                    # Gửi các bản tin retained khớp với filter vừa subscribe
                    for sub_filter, sub_qos in new_filters:
                        for r_topic, (r_payload, r_qos) in list(self.retained_messages.items()):
                            if topic_matches(sub_filter, r_topic):
                                await self._send_publish(
                                    session,
                                    r_topic,
                                    r_payload,
                                    qos=min(sub_qos, r_qos),
                                    retain=True,
                                )

                # 10. UNSUBSCRIBE
                elif packet_type == 10 and session is not None:
                    pkt_id = struct.unpack_from("!H", body, 0)[0]
                    offset = 2
                    while offset < len(body):
                        sub_filter, offset = read_utf8_string(body, offset)
                        session.subscriptions.pop(sub_filter, None)
                    writer.write(struct.pack("!BBH", 0xB0, 2, pkt_id))
                    await writer.drain()

                # 12. PINGREQ -> 13. PINGRESP
                elif packet_type == 12:
                    writer.write(b"\xD0\x00")
                    await writer.drain()

                # 14. DISCONNECT
                elif packet_type == 14 and session is not None:
                    session.clean_disconnect = True
                    break

        except (asyncio.IncompleteReadError, ConnectionResetError):
            pass
        except Exception as exc:
            logger.debug("[Broker] Lỗi kết nối client %s: %s", peer, exc)
        finally:
            if session is not None:
                if self.clients.get(session.client_id) is session:
                    self.clients.pop(session.client_id, None)
                logger.info("[Broker] Client disconnected: %s", session.client_id)
                # Nếu ngắt kết nối đột ngột và có đăng ký Last Will (LWT) -> phát bản tin LWT
                if not session.clean_disconnect and session.will_topic:
                    await self._route_message(
                        session.will_topic,
                        session.will_payload,
                        qos=session.will_qos,
                        retain=session.will_retain,
                    )
            try:
                writer.close()
            except Exception:
                pass


async def _main() -> None:
    broker = EmbeddedMqttBroker(host="0.0.0.0", port=1883)
    await broker.start()
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass
    finally:
        await broker.stop()


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        print("\nĐã dừng MQTT Broker.")
