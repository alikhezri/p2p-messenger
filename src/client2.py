import socket

HEADER = 64
PORT = 3434
SERVER = socket.gethostbyname(socket.gethostname())
ADDR = (SERVER, PORT)
ENCODING = 'utf-8'
DISCONNNECT_MESSAGE = '!!DISCONNECT!!'


def prepare_message(raw_message: str) -> bytes:
    message = raw_message.encode(ENCODING)
    message_length = str(len(message)).encode(ENCODING)
    header = message_length + b' ' * (HEADER - len(message_length))
    full_message = header + message
    return full_message


with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.connect(ADDR)
    CONNECTED = True
    while CONNECTED:
        try:
            raw_message = input("message:> ")
            if raw_message:
                prepared_message = prepare_message(
                    raw_message=raw_message)
                s.sendall(prepared_message)
                message_length_str = s.recv(HEADER).decode(ENCODING)
                if message_length_str:
                    message_length = int(message_length_str)
                    msg = s.recv(message_length).decode(ENCODING)
                    if msg == DISCONNNECT_MESSAGE:
                        CONNECTED = False
                    print("Recieved:", msg)
            else:
                continue
        except KeyboardInterrupt:
            s.sendall(prepare_message(DISCONNNECT_MESSAGE))
            break
