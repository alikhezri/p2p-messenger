from abc import ABC, abstractmethod
import enum
import errno
import socket
import random
import string
import pickle
from threading import Thread
from time import sleep
from datetime import datetime
import traceback
from typing import Callable, Dict, List, Optional, Tuple, Type

TCP_PORT = 3434
UDP_PORT = 5151

TCP_HEADER = 64
UDP_HEADER = 64
UDP_BODY = 2048
ENCODING = 'utf-8'
UUID_LENGTH = 8

DEFAULT_TAIL_LENGTH = 20
DEFAULT_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
PRE_CONNECTION_CLOSE_SLEEP_TIME = 1.5
IP_MULTICAST_TTL = 1


class MessageType(enum.Enum):
    ABSTRACT_MESSAGE = 0
    CONNECT_MESSAGE = 10
    CHAT_MESSAGE = 11
    DISCONNNECT_MESSAGE = 12
    DISCOVER_QUESTION = 31
    DISCOVER_ANSWER = 32


class Message(ABC):
    # __slots__ = 'type', 'time'
    def __init__(self) -> None:
        self.type = MESSAGE_CLASS_TO_TYPE_MAPPING[self.__class__]
        self.time = datetime.now()

    def get_data(self) -> Dict:
        return {
            "type": self.type,
            "time": self.time,
        }

    @classmethod
    def _get_clean_data_func(cls, attributes: List[str] = []) -> Callable[[Dict], Optional[Dict]]:
        def _clean_data(data: Dict) -> Optional[Dict]:
            cleaned_data = {}
            print(f"attributes: {attributes}")
            print(f"data: {data}")
            for attr in attributes:
                if attr in data:
                    cleaned_data[attr] = data[attr]
                else:
                    return False
            print(f"cleaned_data {cleaned_data}")
            return cleaned_data
        return _clean_data

    @classmethod
    @abstractmethod
    def clean_data(cls, data: Dict) -> Optional[Dict]:
        return cls._get_clean_data_func(attributes=[])(data=data)


class ChatMessage(Message):
    # __slots__ = 'text', 'incoming'
    def __init__(self, text: str, incoming: bool = True) -> None:
        super().__init__()
        self.text = text
        self.incoming = incoming

    def get_data(self) -> Dict:
        return {
            "type": self.type,
            "time": self.time,
            "text": self.text,
        }

    @classmethod
    def clean_data(cls, data: Dict) -> Optional[Dict]:
        return cls._get_clean_data_func(attributes=['text', ])(data=data)


class DisconnectMessage(Message):
    def __init__(self) -> None:
        super().__init__()

    def get_data(self) -> Dict:
        return super().get_data()

    @classmethod
    def clean_data(cls, data: Dict) -> Optional[Dict]:
        return cls._get_clean_data_func(attributes=[])(data=data)


MESSAGE_CLASS_TO_TYPE_MAPPING = {
    Message: MessageType.ABSTRACT_MESSAGE,
    ChatMessage: MessageType.CHAT_MESSAGE,
    DisconnectMessage: MessageType.DISCONNNECT_MESSAGE,
}

MESSAGE_TYPE_TO_CLASS_MAPPING = {
    v: k for k, v in MESSAGE_CLASS_TO_TYPE_MAPPING.items()
}


class PeerConnection:
    def __init__(self, uuid: str, conn: socket.socket, host: str, port: int, active: bool = True) -> None:
        self.uuid = uuid
        self.active = active
        self.conn = conn
        self.host = host
        self.port = port
        self.messages: List[ChatMessage] = []

    def get_messages(self, tail: int = DEFAULT_TAIL_LENGTH, time_format: str = DEFAULT_TIME_FORMAT) -> List[str]:
        messages = self.messages[-tail:]
        formatted_messages = []
        for m in messages:
            if m.incoming:
                formatted_messages.append(
                    f"[{m.time.strftime(time_format)}] {self.uuid}: {m.text}")
            else:
                formatted_messages.append(
                    f"[{m.time.strftime(time_format)}] You: {m.text}")
        return formatted_messages


class Peer:
    def __init__(self, host: str, tcp_port: int, udp_port: int) -> None:
        self.host = host
        self.tcp_port = tcp_port
        self.udp_port = udp_port
        self._tcp_listen_socket: socket.socket = None
        self._udp_listen_socket: socket.socket = None
        self._connections: Dict[str, PeerConnection] = {}
        self._near_neighbors = set()

    @staticmethod
    def get_uuid(length=64) -> str:
        alphanumeric = string.ascii_letters + string.digits
        uuid = ''.join(random.choices(population=alphanumeric, k=length))
        return uuid

    @staticmethod
    def wrap_payload(payload: bytes, header_length: int = TCP_HEADER) -> bytes:
        payload_length_bytes = str(len(payload)).encode(ENCODING)
        header = payload_length_bytes + b' ' * \
            (header_length - len(payload_length_bytes))
        full_message = header + payload
        return full_message

    @staticmethod
    def tcp_get_payload(conn: socket, header_length: int = TCP_HEADER) -> bytes:
        payload_length_str = conn.recv(
            header_length).decode(ENCODING).strip()
        if payload_length_str:
            try:
                payload_length = int(payload_length_str)
                payload = conn.recv(payload_length)
                return payload
            except Exception as ex:
                print(f"Exception wehen getting TCP payload: {ex}")
                return False
        else:
            # TODO: DEBUG log
            raise Exception(f"No TCP payload_length_str: {payload_length_str}")

    @staticmethod
    def _udp_get_payload(conn: socket.socket, header_length: int = UDP_HEADER, body_length: int = UDP_BODY) -> Tuple[Optional[str], Optional[Tuple[str, int]]]:
        packet_bytes, addr = conn.recvfrom(header_length + body_length)
        payload_length_str = packet_bytes[:header_length].decode(
            ENCODING).strip()
        if payload_length_str:
            try:
                payload_length = int(payload_length_str)
                payload = packet_bytes[header_length:header_length +
                                       payload_length].decode(ENCODING)
                return payload, addr
            except Exception as ex:
                print(f"Exception wehen getting UDP payload: {ex}")
                return None, None
        else:
            print(f"No UDP payload_length_str: {payload_length_str}")
            return None, None

    @staticmethod
    def extract_payload(payload: bytes, encryption_key: Optional[str] = None) -> Optional[Dict]:
        if encryption_key:
            payload = Peer.decrypt(cipher=payload, key=encryption_key)
        try:
            data = pickle.loads(data=payload, encoding=ENCODING)
            if not type(data) == dict:
                raise Exception("Failed To Load Data")
            return data
        except Exception as ex:
            print(f"Exception when getting dict data: {ex}")
            return False

    @staticmethod
    def get_message(data: Dict) -> Message:
        MessageClass: Type[Message] = MESSAGE_TYPE_TO_CLASS_MAPPING[data['type']]
        print(MessageClass)
        clean_data = MessageClass.clean_data(data=data)
        if clean_data == False:
            print(f"Could not create message from received data: {data}")
            raise Exception(f"Message Parse Exception with data: {data}")
        else:
            return MessageClass(**clean_data)

    @staticmethod
    def receive_message(conn: socket.socket) -> Optional[Message]:
        payload = Peer.tcp_get_payload(conn=conn)
        if not payload:
            print("No Payload in receive_message")
            raise Exception("Payload receive Exception")
        print(f"payload in receive_message: {payload}")
        data = Peer.extract_payload(payload=payload)
        if not data:
            print("No data in receive_message")
            raise Exception("Data receive Exception")
        print(f"data in receive_message: {data}")
        message = Peer.get_message(data)
        return message

    def handle_connection(self, conn: socket.socket, uuid: str) -> None:
        with conn:
            while self._connections[uuid].active:
                try:
                    # msg = Peer._tcp_get_payload(conn=conn)
                    msg = Peer.receive_message(conn=conn)
                    # print(f"Var 'message' in 'handle_connection': {msg}")
                    if msg:
                        if msg.type == MessageType.DISCONNNECT_MESSAGE:
                            msg: DisconnectMessage
                            self._connections[uuid].active = False
                        elif msg.type == MessageType.CHAT_MESSAGE:
                            msg: ChatMessage
                            self._connections[uuid].messages.append(
                                ChatMessage(incoming=True, text=msg.text)
                            )
                        else:
                            pass
                    else:
                        continue
                except IOError as ex:
                    if ex.errno != errno.EAGAIN and ex.errno != errno.EWOULDBLOCK:
                        self.disconnect(uuid=uuid)
                    print(f"IOError handled: {ex}")
                    continue
                except Exception as ex:
                    if not self._connections[uuid].active:
                        # if know connection is closed
                        continue
                    print(f"Exception when handling connection {ex}")
                    print(traceback.format_exc())
                    self.disconnect(uuid=uuid)

    def _add_handler_thread(self, conn: socket.socket, addr: Tuple) -> Thread:
        uuid = Peer.get_uuid(length=UUID_LENGTH)
        connection_t = Thread(
            target=self.handle_connection,
            args=(conn, uuid),
            daemon=True,
        )
        self._connections[uuid] = PeerConnection(
            uuid=uuid,
            conn=conn,
            host=addr[0],
            port=addr[1],
        )
        connection_t.start()
        return connection_t

    def _tcp_listen(self, addr: Tuple) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            self._tcp_listen_socket = s
            s.bind(addr)
            s.listen()
            while True:
                try:
                    conn, addr = s.accept()
                    print('Connected by', addr)
                    print("command > ", end='', flush=True)
                    self._add_handler_thread(conn=conn, addr=addr)
                except IOError as ex:
                    if ex.errno != errno.EAGAIN and ex.errno != errno.EWOULDBLOCK:
                        return
                    print(f"IOError handled: {ex}")
                    continue
                except Exception as ex:
                    print(f"Couldn't listen: {ex}")

    def _udp_listen(self, addr: Tuple) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            self._udp_listen_socket = s
            s.bind(("0.0.0.0", self.udp_port))
            while True:
                try:
                    # TODO: use data which can be neighbors' neighbor and encryption etc.
                    data, addr = Peer._udp_get_payload(conn=s)
                    if data == MessageType.DISCOVER_QUESTION:
                        if addr[0] == self.host:
                            continue
                        print(f"Got discover question from {addr}")
                        s.sendto(
                            Peer.wrap_payload(
                                payload=MessageType.DISCOVER_ANSWER,
                                header_length=UDP_HEADER,
                            ),
                            (addr[0], UDP_PORT)
                        )
                        print("Discover answer sent")
                    elif data == MessageType.DISCOVER_ANSWER:
                        print(f"New neighbor found! {addr[0]}:{TCP_PORT}")
                        self._near_neighbors.add(f"{addr[0]}:{TCP_PORT}")
                    else:
                        print(f"Got unknown UDP message: {data}")
                except IOError as ex:
                    if ex.errno != errno.EAGAIN and ex.errno != errno.EWOULDBLOCK:
                        return
                    print(f"IOError handled: {ex}")
                    continue
                except Exception as ex:
                    print(f"Couldn't listen: {ex}")

    def start(self) -> bool:
        try:
            tcp_listen_thread = Thread(
                target=self._tcp_listen,
                args=((self.host, self.tcp_port),),
                daemon=True,
            )
            tcp_listen_thread.start()
            udp_listen_thread = Thread(
                target=self._udp_listen,
                args=((self.host, self.udp_port),),
                daemon=True
            )
            udp_listen_thread.start()
            return True
        except Exception as ex:
            print(f"Exception when in 'start': {ex}")
            return False

    def get_me(self):
        return f"{self.host}:{self.tcp_port}"

    def connect(self, addr: Tuple[str, int]) -> Optional[socket.socket]:
        try:
            conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            conn.connect(addr)
            self._add_handler_thread(conn=conn, addr=addr)
            return conn
        except Exception as ex:
            print(f"Exception when connecting to {addr}: {ex}")
            return False

    def disconnect(self, uuid: str) -> Optional[bool]:
        if uuid in self._connections:
            pcon = self._connections[uuid]
        else:
            print(f"Connection uuid does not exist: {uuid}")
            return False
        if not pcon.active:
            return True
        try:
            pcon.active = False
            message = DisconnectMessage()
            self.send_message(message=message, conn=pcon.conn)
        except IOError as ex:
            if ex.errno != errno.EAGAIN and ex.errno != errno.EWOULDBLOCK:
                pass
            else:
                print(f"IOError handled: {ex}")
        except Exception as ex:
            print(f"Exception when disconnecting connection {uuid}: {ex}")
            return None
        sleep(PRE_CONNECTION_CLOSE_SLEEP_TIME)
        try:
            pcon.conn.close()
        except IOError as ex:
            if ex.errno != errno.EAGAIN and ex.errno != errno.EWOULDBLOCK:
                pass
            else:
                print(f"IOError handled: {ex}")
        except Exception as ex:
            print(f"Exception when ending peer connection: {ex}")
            return None
        return True

    @staticmethod
    def decrypt(cipher: bytes, key: str) -> bytes:
        pass

    @staticmethod
    def encrypt(plain: bytes, key: str) -> bytes:
        pass

    @staticmethod
    def get_payload(data: Dict, encryption_key: Optional[str] = None) -> bytes:
        payload = pickle.dumps(obj=data, protocol=pickle.DEFAULT_PROTOCOL)
        if encryption_key:
            payload = Peer.encrypt(plain=payload, key=encryption_key)
        return payload

    @staticmethod
    def send_message(message: Message, conn: socket.socket) -> bool:
        data = message.get_data()
        print(f"data in send_message: {data}")
        payload = Peer.get_payload(data=data)
        print(f"payload in send_message: {payload}")
        prepared_message = Peer.wrap_payload(
            payload=payload)
        print(f"prepared_message in send_message: {prepared_message}")
        conn.sendall(prepared_message)
        return True

    def chat(self, uuid: str) -> bool:
        if uuid in self._connections:
            conn = self._connections[uuid].conn
            print(f"Chatting With {uuid}")
            CHAT_MODE = True
            while CHAT_MODE:
                try:
                    raw_message = input(f"You: > ")
                    splitted_raw_message = raw_message.split()
                    if raw_message:
                        if splitted_raw_message[0] == r"\b" or splitted_raw_message[0] == r"\back":
                            CHAT_MODE = False
                            continue
                        elif splitted_raw_message[0] == r"\t" or splitted_raw_message[0] == r"\tail":
                            if len(splitted_raw_message) == 2:
                                try:
                                    tail = int(splitted_raw_message[1])
                                    messages = self._connections[uuid].get_messages(
                                        tail=tail)
                                except Exception as ex:
                                    print(
                                        f"Tail's second parameter should be number: {splitted_raw_message[1]}")
                                    continue
                            else:
                                messages = self._connections[uuid].get_messages(
                                )
                            for m in messages:
                                print(m)
                        else:
                            if self._connections[uuid].active:
                                message = ChatMessage(
                                    incoming=False, text=raw_message)
                                if self.send_message(
                                    message=message,
                                    conn=conn,
                                ):
                                    self._connections[uuid].messages.append(
                                        message)
                            else:
                                print(
                                    "Connection is ended, only recent messages can be seen")
                    else:
                        continue
                except KeyboardInterrupt as ex:
                    print()
                    continue
                except Exception as ex:
                    print(f"Exception when chatting with {uuid}: {ex}")
            return True
        else:
            print(f"Connection with UUID does not exist: {uuid}")
            return None

    def list_actives(self) -> List:
        return [
            (
                uuid,
                f"{self._connections[uuid].host}:{self._connections[uuid].port}",
            ) for uuid in self._connections if self._connections[uuid].active
        ]

    def list_inactives(self) -> List:
        return [
            (
                uuid,
                f"{self._connections[uuid].host}:{self._connections[uuid].port}",
            ) for uuid in self._connections if not self._connections[uuid].active
        ]

    def get_discovered(self) -> List:
        return [nn for nn in self._near_neighbors]

    def discover(self) -> None:
        # TODO: all interfaces should be used
        # interfaces = socket.getaddrinfo(host=socket.gethostname(), port=None, family=socket.AF_INET)
        # allips = [ip[-1][0] for ip in interfaces]
        # for ip in allips:
        #     with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as s:
        #         s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, IP_MULTICAST_TTL)
        #         s.bind((ip,0))
        #         s.sendto(Peer.wrap_payload(payload=DISCOVER_QUESTION), ('255.255.255.255', self.udp_port))
        self._near_neighbors = set()
        print("Creating UDP socket for broadcast")
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as s:
            print("Setting options for UDP broadcast")
            s.setsockopt(socket.SOL_SOCKET,
                         socket.SO_BROADCAST, IP_MULTICAST_TTL)
            s.bind((self.host, 0))
            print("Sending UDP braodcast message")
            s.sendto(
                Peer.wrap_payload(
                    payload=MessageType.DISCOVER_QUESTION,
                    header_length=UDP_HEADER
                ),
                ('255.255.255.255', self.udp_port)
            )

    def end_gracefully(self) -> None:
        try:
            self._tcp_listen_socket.close()
        except IOError as ex:
            if ex.errno != errno.EAGAIN and ex.errno != errno.EWOULDBLOCK:
                pass
            else:
                print(f"IOError handled when closing TCP: {ex}")
        except Exception as ex:
            print(f"Exception when ending peer TCP connection: {ex}")
        try:
            self._udp_listen_socket.close()
        except IOError as ex:
            if ex.errno != errno.EAGAIN and ex.errno != errno.EWOULDBLOCK:
                pass
            else:
                print(f"IOError handled when closing UDP: {ex}")
        except Exception as ex:
            print(f"Exception when ending peer UDP connection: {ex}")
        for pcon in self._connections.values():
            if not pcon.active:
                continue
            try:
                pcon.active = False
                message = DisconnectMessage()
                self.send_message(message=message, conn=pcon.conn)
            except IOError as ex:
                if ex.errno != errno.EAGAIN and ex.errno != errno.EWOULDBLOCK:
                    pass
                else:
                    print(f"IOError handled: {ex}")
            except Exception as ex:
                print(f"Exception when ending peer connection: {ex}")
        sleep(PRE_CONNECTION_CLOSE_SLEEP_TIME)
        for pcon in self._connections.values():
            try:
                pcon.conn.close()
            except IOError as ex:
                if ex.errno != errno.EAGAIN and ex.errno != errno.EWOULDBLOCK:
                    pass
                else:
                    print(f"IOError handled: {ex}")
            except Exception as ex:
                print(f"Exception when ending peer connection: {ex}")

    def end_forcefully(self) -> None:
        try:
            self._tcp_listen_socket.close()
        except IOError as ex:
            if ex.errno != errno.EAGAIN and ex.errno != errno.EWOULDBLOCK:
                pass
            else:
                print(f"IOError handled when closing TCP: {ex}")
        except Exception as ex:
            print(f"Exception when ending peer TCP connection: {ex}")
        try:
            self._udp_listen_socket.close()
        except IOError as ex:
            if ex.errno != errno.EAGAIN and ex.errno != errno.EWOULDBLOCK:
                pass
            else:
                print(f"IOError handled when closing UDP: {ex}")
        except Exception as ex:
            print(f"Exception when ending peer UDP connection: {ex}")
        for pcon in self._connections.values():
            try:
                pcon.active = False
                pcon.conn.close()
            except IOError as ex:
                if ex.errno != errno.EAGAIN and ex.errno != errno.EWOULDBLOCK:
                    pass
                else:
                    print(f"IOError handled: {ex}")
            except Exception as ex:
                print(f"Exception when ending peer: {ex}")
