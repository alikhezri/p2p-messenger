from abc import ABC, abstractmethod
import enum
import errno
import socket
import random
import string
import pickle
import logging
from threading import Thread
from time import sleep
from datetime import datetime
import traceback
from typing import Callable, Dict, Iterable, List, Optional, Tuple, Type

from exceptions import (
    HandshakeException,
    ReceiveMessageException,
    ReceiveTCPMessageException,
    ReceiveUDPMessageException,
    TransceiveHandshakeAckException,
    TransceiveHandshakeKeyException,
)
import crypto

TCP_PORT = 3434
UDP_PORT = 5151

TCP_HEADER = 64
UDP_HEADER = 64
UDP_BODY = 2048
ENCODING = 'utf-8'
UUID_LENGTH = 8

DECRYPTION_BLOCK_SIZE = (crypto.RSA_LENGTH+7) // 8
HASH_LENGTH = 20
ENCRYPTION_BLOCK_SIZE = (crypto.RSA_LENGTH+7) // 8 - 2 - 2*HASH_LENGTH

DEFAULT_TAIL_LENGTH = 20
DEFAULT_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
PRE_CONNECTION_CLOSE_SLEEP_TIME = 1.5
IP_MULTICAST_TTL = 1

DISCOVER_REQUEST_SLEEP_TIME = 5

logger = logging.getLogger("p2p_messenger")


class MessageType(enum.Enum):
    ABSTRACT_MESSAGE = 0
    CHAT_MESSAGE = 11
    DISCONNNECT_MESSAGE = 12
    DISCOVER_QUESTION = 31
    DISCOVER_ANSWER = 32
    KEY_SEND_MESSAGE = 41
    KEY_ACK_MESSAGE = 42
    DISCOVER_REQUEST = 51
    DISCOVER_RESPONSE = 52


class Message(ABC):
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
            logger.debug(f"attributes: {attributes}")
            logger.debug(f"data: {data}")
            for attr in attributes:
                if attr in data:
                    cleaned_data[attr] = data[attr]
                else:
                    return False
            logger.debug(f"cleaned_data {cleaned_data}")
            return cleaned_data
        return _clean_data

    @classmethod
    @abstractmethod
    def clean_data(cls, data: Dict) -> Optional[Dict]:
        return cls._get_clean_data_func(attributes=[])(data=data)


class ChatMessage(Message):
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


class KeySendMessage(Message):
    def __init__(self, key: str) -> None:
        super().__init__()
        self.key = key

    def get_data(self) -> Dict:
        return {
            "type": self.type,
            "time": self.time,
            "key": self.key,
        }

    @classmethod
    def clean_data(cls, data: Dict) -> Optional[Dict]:
        return cls._get_clean_data_func(attributes=['key', ])(data=data)


class KeyAckMessage(Message):
    def __init__(self) -> None:
        super().__init__()

    def get_data(self) -> Dict:
        return super().get_data()

    @classmethod
    def clean_data(cls, data: Dict) -> Optional[Dict]:
        return cls._get_clean_data_func(attributes=[])(data=data)


class DisconnectMessage(Message):
    def __init__(self) -> None:
        super().__init__()

    def get_data(self) -> Dict:
        return super().get_data()

    @classmethod
    def clean_data(cls, data: Dict) -> Optional[Dict]:
        return cls._get_clean_data_func(attributes=[])(data=data)


class DiscoverQuestion(Message):
    def __init__(self) -> None:
        super().__init__()

    def get_data(self) -> Dict:
        return super().get_data()

    @classmethod
    def clean_data(cls, data: Dict) -> Optional[Dict]:
        return cls._get_clean_data_func(attributes=[])(data=data)


class DiscoverAnswer(Message):
    def __init__(self) -> None:
        super().__init__()

    def get_data(self) -> Dict:
        return super().get_data()

    @classmethod
    def clean_data(cls, data: Dict) -> Optional[Dict]:
        return cls._get_clean_data_func(attributes=[])(data=data)


class DiscoverRequest(Message):
    def __init__(self) -> None:
        super().__init__()

    def get_data(self) -> Dict:
        return super().get_data()

    @classmethod
    def clean_data(cls, data: Dict) -> Optional[Dict]:
        return cls._get_clean_data_func(attributes=[])(data=data)


class DiscoverResponse(Message):
    def __init__(self, neighbors: List[Tuple[str, str]]) -> None:
        super().__init__()
        self.neighbors = neighbors

    def get_data(self) -> Dict:
        return {
            "type": self.type,
            "time": self.time,
            "neighbors": self.neighbors,
        }

    @classmethod
    def clean_data(cls, data: Dict) -> Optional[Dict]:
        return cls._get_clean_data_func(attributes=['neighbors', ])(data=data)


MESSAGE_CLASS_TO_TYPE_MAPPING = {
    Message: MessageType.ABSTRACT_MESSAGE,
    ChatMessage: MessageType.CHAT_MESSAGE,
    DisconnectMessage: MessageType.DISCONNNECT_MESSAGE,
    DiscoverQuestion: MessageType.DISCOVER_QUESTION,
    DiscoverAnswer: MessageType.DISCOVER_ANSWER,
    KeySendMessage: MessageType.KEY_SEND_MESSAGE,
    KeyAckMessage: MessageType.KEY_ACK_MESSAGE,
    DiscoverRequest: MessageType.DISCOVER_REQUEST,
    DiscoverResponse: MessageType.DISCOVER_RESPONSE,
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
        self.public_key: Optional[crypto.RSA.RsaKey] = None
        self._near_neighbors: List[Tuple[str, str]] = []

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


def batch(iterable: Iterable, n=1):
    l = len(iterable)
    for ndx in range(0, l, n):
        yield iterable[ndx:min(ndx + n, l)]


class Peer:
    def __init__(self, host: str, tcp_port: int, udp_port: int) -> None:
        self.host = host
        self.tcp_port = tcp_port
        self.udp_port = udp_port
        self._tcp_listen_socket: socket.socket = None
        self._udp_listen_socket: socket.socket = None
        self._connections: Dict[str, PeerConnection] = {}
        self._near_neighbors = set()
        self.public_key: crypto.RSA.RsaKey
        self.private_key: crypto.RSA.RsaKey
        self.public_key, self.private_key = crypto.generate_keys()

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
                logger.error(f"Exception wehen getting TCP payload: {ex}")
                return False
        else:
            raise Exception(
                f"No TCP payload_length_str: '{payload_length_str}'")

    @staticmethod
    def udp_get_payload(conn: socket.socket, header_length: int = UDP_HEADER, body_length: int = UDP_BODY) -> Tuple[Optional[bytes], Optional[Tuple[str, int]]]:
        packet_bytes, addr = conn.recvfrom(header_length + body_length)
        payload_length_str = packet_bytes[:header_length].decode(
            ENCODING).strip()
        if payload_length_str:
            try:
                payload_length = int(payload_length_str)
                payload = packet_bytes[header_length:header_length+payload_length]
                return payload, addr
            except Exception as ex:
                logger.error(f"Exception wehen getting UDP payload: {ex}")
                return None, None
        else:
            logger.warning(f"No UDP payload_length_str: {payload_length_str}")
            return None, None

    @staticmethod
    def extract_payload(payload: bytes, encryption_key: Optional[str] = None) -> Optional[Dict]:
        if encryption_key:
            payload = Peer.decrypt(cipher=payload, key=encryption_key)
            logger.debug(f"Unpickled Data After Decr: {payload}")
        try:
            data = pickle.loads(data=payload, encoding=ENCODING)
            if not type(data) == dict:
                raise Exception("Failed to get Dict data")
            return data
        except Exception as ex:
            logger.error(f"Exception when getting data: {ex}")
            logger.debug(traceback.format_exc())
            return False

    @staticmethod
    def get_message(data: Dict) -> Message:
        MessageClass: Type[Message] = MESSAGE_TYPE_TO_CLASS_MAPPING[data['type']]
        logger.debug(MessageClass)
        clean_data = MessageClass.clean_data(data=data)
        if clean_data == False:
            logger.debug(
                f"Could not create message from received data: {data}")
            raise ReceiveTCPMessageException(
                f"Message Parse Exception with data: {data}")
        else:
            return MessageClass(**clean_data)

    @staticmethod
    def receive_tcp_message(conn: socket.socket, key: Optional[crypto.RSA.RsaKey] = None) -> Optional[Message]:
        payload = Peer.tcp_get_payload(conn=conn)
        if not payload:
            logger.debug("No Payload in receive_message")
            raise ReceiveTCPMessageException("Payload receive Exception")
        logger.debug(f"payload in receive_message: {payload}")
        data = Peer.extract_payload(
            payload=payload,
            encryption_key=key
        )
        if not data:
            logger.debug("No data in receive_message")
            raise ReceiveTCPMessageException("Data receive Exception")
        logger.debug(f"data in receive_message: {data}")
        message = Peer.get_message(data)
        return message

    def handshake(self, conn: socket.socket, uuid: str) -> None:
        key_send_msg = KeySendMessage(
            key=crypto.serialize_key(self.public_key))
        Peer.send_tcp_message(message=key_send_msg, conn=conn)

        key_receive_msg: KeySendMessage = Peer.receive_tcp_message(conn=conn)
        if not key_receive_msg:
            raise TransceiveHandshakeKeyException("Get key failed")
        if key_receive_msg.type == MessageType.KEY_SEND_MESSAGE:
            key = crypto.load_key(key_receive_msg.key)
            self._connections[uuid].public_key = key
        else:
            raise TransceiveHandshakeKeyException("Excpected key")

        key_ack_send_msg = KeyAckMessage()
        Peer.send_tcp_message(message=key_ack_send_msg, conn=conn)

        key_ack_rcv_msg: KeyAckMessage = Peer.receive_tcp_message(conn=conn)
        if not key_ack_rcv_msg:
            raise TransceiveHandshakeAckException("Get ack failed")
        if key_ack_rcv_msg.type == MessageType.KEY_ACK_MESSAGE:
            pass
        else:
            raise TransceiveHandshakeAckException("Ack failed")

    def handle_connection(self, conn: socket.socket, uuid: str) -> None:
        with conn:
            try:
                self.handshake(
                    conn=conn,
                    uuid=uuid,
                )
            except HandshakeException as ex:
                logger.debug(f"Couldn't perform handshake: {ex}")
                raise Exception("Handshake failed")
            except Exception as ex:
                logger.debug(traceback.format_exc())
                self.disconnect(uuid=uuid)
            while self._connections[uuid].active:
                try:
                    msg = Peer.receive_tcp_message(
                        conn=conn,
                        key=self.private_key,
                    )
                    if msg:
                        if msg.type == MessageType.DISCONNNECT_MESSAGE:
                            dis_msg: DisconnectMessage = msg
                            self._connections[uuid].active = False
                        elif msg.type == MessageType.CHAT_MESSAGE:
                            chat_msg: ChatMessage = msg
                            self._connections[uuid].messages.append(
                                ChatMessage(incoming=True, text=chat_msg.text)
                            )
                        elif msg.type == MessageType.DISCOVER_REQUEST:
                            neighbors = self.list_actives()
                            dis_resp_msg = DiscoverResponse(
                                neighbors=neighbors)
                            self.send_tcp_message(
                                message=dis_resp_msg,
                                conn=conn,
                                key=self._connections[uuid].public_key,
                            )
                        elif msg.type == MessageType.DISCOVER_RESPONSE:
                            dis_resp_msg: DiscoverResponse = msg
                            self._connections[uuid]._near_neighbors = dis_resp_msg.neighbors
                        else:
                            pass
                    else:
                        continue
                except IOError as ex:
                    if ex.errno != errno.EAGAIN and ex.errno != errno.EWOULDBLOCK:
                        self.disconnect(uuid=uuid)
                    logger.warning(f"IOError handled: {ex}")
                    continue
                except ReceiveMessageException as ex:
                    logger.warning(
                        f"Exception when receiving TCP messge: {ex}")
                    continue
                except Exception as ex:
                    if not self._connections[uuid].active:
                        # if know connection is closed
                        continue
                    logger.error(f"Exception when handling connection {ex}")
                    logger.debug(traceback.format_exc())
                    self.disconnect(uuid=uuid)

    def _add_handler_thread(self, conn: socket.socket, addr: Tuple, uuid: str = None) -> Thread:
        if not uuid:
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
                    logger.warning(f"IOError handled: {ex}")
                    continue
                except Exception as ex:
                    logger.error(f"Couldn't listen: {ex}")

    @staticmethod
    def receive_udp_message(conn: socket.socket) -> Tuple[Optional[Message], Optional[Tuple[str, int]]]:
        payload, addr = Peer.udp_get_payload(conn=conn)
        if not payload:
            logger.debug("No Payload in receive_message")
            raise ReceiveUDPMessageException("Payload receive Exception")
        logger.debug(f"payload in receive_message: {payload}")
        data = Peer.extract_payload(payload=payload)
        if not data:
            logger.debug("No data in receive_message")
            raise ReceiveUDPMessageException("Data receive Exception")
        logger.debug(f"data in receive_message: {data}")
        message = Peer.get_message(data)
        return message, addr

    def _udp_listen(self, addr: Tuple) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            self._udp_listen_socket = s
            s.bind(("0.0.0.0", self.udp_port))
            while True:
                try:
                    # TODO: use data which can be neighbors' neighbor and encryption etc.
                    message, addr = Peer.receive_udp_message(conn=s)
                    if message.type == MessageType.DISCOVER_QUESTION:
                        if addr[0] == self.host:
                            continue
                        logger.debug(f"Got discover question from {addr}")
                        answer_msg = DiscoverAnswer()
                        self.send_udp_message(
                            message=answer_msg,
                            conn=s,
                            to=(addr[0], UDP_PORT),
                        )
                        logger.debug("Discover answer sent")
                    elif message.type == MessageType.DISCOVER_ANSWER:
                        logger.debug(
                            f"New neighbor found! {addr[0]}:{TCP_PORT}")
                        self._near_neighbors.add(f"{addr[0]}:{TCP_PORT}")
                    else:
                        logger.debug(f"Got unknown UDP message: {message}")
                except IOError as ex:
                    if ex.errno != errno.EAGAIN and ex.errno != errno.EWOULDBLOCK:
                        return
                    logger.warning(f"IOError handled: {ex}")
                    continue
                except ReceiveMessageException as ex:
                    logger.warning(
                        f"Exception when receiving UDP messge: {ex}")
                    continue
                except Exception as ex:
                    logger.error(f"Couldn't listen: {ex}")
                    continue

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
            logger.error(f"Exception when in 'start': {ex}")
            return False

    def get_me(self):
        return f"{self.host}:{self.tcp_port}"

    def connect(self, addr: Tuple[str, int], uuid: str = None) -> Optional[socket.socket]:
        try:
            conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            conn.connect(addr)
            self._add_handler_thread(conn=conn, addr=addr, uuid=uuid)
            return conn
        except Exception as ex:
            logger.error(f"Exception when connecting to {addr}: {ex}")
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
            self.send_tcp_message(
                message=message,
                conn=pcon.conn,
                key=pcon.public_key
            )
        except IOError as ex:
            if ex.errno != errno.EAGAIN and ex.errno != errno.EWOULDBLOCK:
                pass
            else:
                logger.warning(f"IOError handled: {ex}")
        except Exception as ex:
            logger.error(
                f"Exception when disconnecting connection {uuid}: {ex}")
            return None
        sleep(PRE_CONNECTION_CLOSE_SLEEP_TIME)
        try:
            pcon.conn.close()
        except IOError as ex:
            if ex.errno != errno.EAGAIN and ex.errno != errno.EWOULDBLOCK:
                pass
            else:
                logger.warning(f"IOError handled: {ex}")
        except Exception as ex:
            logger.error(f"Exception when ending peer connection: {ex}")
            return None
        return True

    @staticmethod
    def decrypt(cipher: bytes, key: str) -> bytes:
        logger.debug(f"Cipher Length: {len(cipher)}")
        decrypted_chunks: List[bytes] = [
            crypto.decrypt_bytes(
                enc_payload=chunk,
                key=key
            ) for chunk in batch(iterable=cipher, n=DECRYPTION_BLOCK_SIZE)
        ]
        return b''.join(decrypted_chunks)

    @staticmethod
    def encrypt(plain: bytes, key: str) -> bytes:
        logger.debug(f"Plain Length: {len(plain)}")
        encrypted_chunks: List[bytes] = [
            crypto.encrypt_bytes(
                payload=chunk,
                key=key,
            ) for chunk in batch(iterable=plain, n=ENCRYPTION_BLOCK_SIZE)
        ]
        return b''.join(encrypted_chunks)

    @staticmethod
    def get_payload(data: Dict, encryption_key: Optional[str] = None) -> bytes:
        payload = pickle.dumps(obj=data, protocol=pickle.DEFAULT_PROTOCOL)
        if encryption_key:
            logger.debug(f"Pickled Data Before Enc: {payload}")
            payload = Peer.encrypt(plain=payload, key=encryption_key)
        return payload

    @staticmethod
    def send_tcp_message(message: Message, conn: socket.socket, key: Optional[crypto.RSA.RsaKey] = None) -> bool:
        data = message.get_data()
        logger.debug(f"data in send_message: {data}")
        payload = Peer.get_payload(
            data=data,
            encryption_key=key
        )
        logger.debug(f"payload in send_message: {payload}")
        prepared_message = Peer.wrap_payload(
            payload=payload)
        logger.debug(f"prepared_message in send_message: {prepared_message}")
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
                        if raw_message[0] == "\\":
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
                                        logger.debug(
                                            f"Tail's second parameter should be number: {splitted_raw_message[1]}")
                                        logger.error(
                                            f"Exception for tail command in chat: {ex}")
                                        continue
                                else:
                                    messages = self._connections[uuid].get_messages(
                                    )
                                for m in messages:
                                    print(m)
                            else:
                                print(
                                    f"Command '{splitted_raw_message[0]}' does not exist")
                        else:
                            if self._connections[uuid].active:
                                message = ChatMessage(
                                    incoming=False, text=raw_message)
                                if self.send_tcp_message(
                                    message=message,
                                    conn=conn,
                                    key=self._connections[uuid].public_key,
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
                    logger.error(f"Exception when chatting with {uuid}: {ex}")
                    logger.debug(traceback.format_exc())
            return True
        else:
            logger.warning(f"Connection with UUID does not exist: {uuid}")
            return None

    def list_actives(self) -> List[Tuple[str, str]]:
        return [
            (
                uuid,
                f"{self._connections[uuid].host}:{self._connections[uuid].port}",
            ) for uuid in self._connections if self._connections[uuid].active
        ]

    def list_inactives(self) -> List[Tuple[str, str]]:
        return [
            (
                uuid,
                f"{self._connections[uuid].host}:{self._connections[uuid].port}",
            ) for uuid in self._connections if not self._connections[uuid].active
        ]

    def list_neighbor_actives(self, uuid: str) -> List[Tuple[str, str]]:
        if uuid not in self._connections:
            print("UUID does not exist")
            return []
        if not self._connections[uuid].active:
            print("Connection is not active")
            return []
        try:
            pcon = self._connections[uuid]
            req_msg = DiscoverRequest()
            Peer.send_tcp_message(
                message=req_msg,
                conn=pcon.conn,
                key=pcon.public_key,
            )
            sleep(DISCOVER_REQUEST_SLEEP_TIME)
            return pcon._near_neighbors
        except Exception as ex:
            logger.debug("Exception when requesting neighbor actives")
            logger.debug(traceback.format_exc())
            return[]

    def get_discovered(self) -> List[str]:
        return [nn for nn in self._near_neighbors]

    @staticmethod
    def send_udp_message(message: Message, conn: socket.socket, to: Tuple[str, int]) -> bool:
        data = message.get_data()
        logger.debug(f"data in send_message: {data}")
        payload = Peer.get_payload(data=data)
        logger.debug(f"payload in send_message: {payload}")
        prepared_message = Peer.wrap_payload(
            payload=payload, header_length=UDP_HEADER)
        logger.debug(f"prepared_message in send_message: {prepared_message}")
        conn.sendto(prepared_message, to)
        return True

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
        logger.debug("Creating UDP socket for broadcast")
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as s:
            logger.debug("Setting options for UDP broadcast")
            s.setsockopt(
                socket.SOL_SOCKET,
                socket.SO_BROADCAST,
                IP_MULTICAST_TTL
            )
            s.bind((self.host, 0))
            logger.debug("Sending UDP braodcast message")
            message = DiscoverQuestion()
            self.send_udp_message(
                message=message,
                conn=s,
                to=('255.255.255.255', self.udp_port),
            )

    def end_gracefully(self) -> None:
        try:
            self._tcp_listen_socket.close()
        except IOError as ex:
            if ex.errno != errno.EAGAIN and ex.errno != errno.EWOULDBLOCK:
                pass
            else:
                logger.warning(f"IOError handled when closing TCP: {ex}")
        except Exception as ex:
            logger.error(f"Exception when ending peer TCP connection: {ex}")
        try:
            self._udp_listen_socket.close()
        except IOError as ex:
            if ex.errno != errno.EAGAIN and ex.errno != errno.EWOULDBLOCK:
                pass
            else:
                logger.warning(f"IOError handled when closing UDP: {ex}")
        except Exception as ex:
            logger.error(f"Exception when ending peer UDP connection: {ex}")
        for pcon in self._connections.values():
            if not pcon.active:
                continue
            try:
                pcon.active = False
                message = DisconnectMessage()
                self.send_tcp_message(
                    message=message,
                    conn=pcon.conn,
                    key=pcon.public_key,
                )
            except IOError as ex:
                if ex.errno != errno.EAGAIN and ex.errno != errno.EWOULDBLOCK:
                    pass
                else:
                    logger.warning(f"IOError handled: {ex}")
            except Exception as ex:
                logger.error(f"Exception when ending peer connection: {ex}")
        sleep(PRE_CONNECTION_CLOSE_SLEEP_TIME)
        for pcon in self._connections.values():
            try:
                pcon.conn.close()
            except IOError as ex:
                if ex.errno != errno.EAGAIN and ex.errno != errno.EWOULDBLOCK:
                    pass
                else:
                    logger.warning(f"IOError handled: {ex}")
            except Exception as ex:
                logger.error(f"Exception when ending peer connection: {ex}")

    def end_forcefully(self) -> None:
        try:
            self._tcp_listen_socket.close()
        except IOError as ex:
            if ex.errno != errno.EAGAIN and ex.errno != errno.EWOULDBLOCK:
                pass
            else:
                logger.warning(f"IOError handled when closing TCP: {ex}")
        except Exception as ex:
            logger.error(f"Exception when ending peer TCP connection: {ex}")
        try:
            self._udp_listen_socket.close()
        except IOError as ex:
            if ex.errno != errno.EAGAIN and ex.errno != errno.EWOULDBLOCK:
                pass
            else:
                logger.warning(f"IOError handled when closing UDP: {ex}")
        except Exception as ex:
            logger.error(f"Exception when ending peer UDP connection: {ex}")
        for pcon in self._connections.values():
            try:
                pcon.active = False
                pcon.conn.close()
            except IOError as ex:
                if ex.errno != errno.EAGAIN and ex.errno != errno.EWOULDBLOCK:
                    pass
                else:
                    logger.warning(f"IOError handled: {ex}")
            except Exception as ex:
                logger.error(f"Exception when ending peer: {ex}")
